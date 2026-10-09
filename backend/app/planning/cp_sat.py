import logging
from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.domain.models import Carrier, Order
from app.errors import CalculationError
from app.planning.types import Assignment, OutAssignment, OwnRoute, PricedOffer

logger = logging.getLogger(__name__)


@dataclass
class SolverOutcome:
    engine: str
    status: str
    assignment: Assignment | None
    elapsed_ms: int
    best_bound_kopecks: int | None
    objective_kopecks: int | None
    note: str | None


def solve_cp_sat(
    candidates: list[OwnRoute],
    offers: list[PricedOffer],
    orders: list[Order],
    carriers: list[Carrier],
    *,
    time_limit_s: float,
    elapsed_ms: int,
) -> SolverOutcome:
    if not orders:
        return SolverOutcome(
            engine="cp_sat_candidates",
            status="NOT_RUN",
            assignment=None,
            elapsed_ms=elapsed_ms,
            best_bound_kopecks=None,
            objective_kopecks=None,
            note="Нет заказов, поиск не запускался.",
        )
    model = cp_model.CpModel()
    route_vars = [model.new_bool_var(f"r{index}") for index in range(len(candidates))]
    offer_vars = [model.new_bool_var(f"q{index}") for index in range(len(offers))]
    for order in orders:
        terms = [route_vars[index] for index, route in enumerate(candidates) if order.id in route.order_ids]
        terms += [offer_vars[index] for index, offer in enumerate(offers) if offer.order_id == order.id]
        if not terms:
            return SolverOutcome(
                engine="cp_sat_candidates",
                status="INFEASIBLE",
                assignment=None,
                elapsed_ms=elapsed_ms,
                best_bound_kopecks=None,
                objective_kopecks=None,
                note="Для заказа нет ни собственного кандидата, ни предложения подрядчика.",
            )
        model.add(sum(terms) == 1)
    for vehicle_id in sorted({route.vehicle_id for route in candidates}):
        chosen = [route_vars[index] for index, route in enumerate(candidates) if route.vehicle_id == vehicle_id]
        if chosen:
            model.add(sum(chosen) <= 1)
    for carrier in carriers:
        chosen = [offer_vars[index] for index, offer in enumerate(offers) if offer.carrier_id == carrier.id]
        if chosen:
            model.add(sum(chosen) <= carrier.max_orders_per_horizon)
    objective_terms = [candidates[index].variable_cost_kopecks * route_vars[index] for index in range(len(candidates))]
    objective_terms += [offers[index].price_kopecks * offer_vars[index] for index in range(len(offers))]
    if objective_terms:
        model.minimize(sum(objective_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 1
    if hasattr(solver.parameters, "random_seed"):
        solver.parameters.random_seed = 1
    status_code = solver.solve(model)
    status = solver.status_name(status_code)
    if status not in {"OPTIMAL", "FEASIBLE"}:
        return SolverOutcome(
            engine="cp_sat_candidates",
            status=status,
            assignment=None,
            elapsed_ms=elapsed_ms,
            best_bound_kopecks=None,
            objective_kopecks=None,
            note=_status_note(status),
        )
    chosen_routes = [candidates[index] for index, var in enumerate(route_vars) if solver.boolean_value(var)]
    chosen_offers = [offers[index] for index, var in enumerate(offer_vars) if solver.boolean_value(var)]
    objective = sum(route.variable_cost_kopecks for route in chosen_routes) + sum(
        offer.price_kopecks for offer in chosen_offers
    )
    reported = int(round(_solver_number(solver.objective_value)))
    if reported != objective:
        logger.error("CP-SAT objective %s != recomputed %s", reported, objective)
        raise CalculationError("solver objective mismatch")
    bound = int(round(_solver_number(solver.best_objective_bound)))
    assignment = Assignment(
        routes=chosen_routes,
        outsourced=[
            OutAssignment(offer_id=offer.offer_id, carrier_id=offer.carrier_id, order_id=offer.order_id)
            for offer in chosen_offers
        ],
        unserved=[],
    )
    note = "Оптимально среди сгенерированных кандидатов, а не среди всех мыслимых маршрутов."
    if status == "FEASIBLE":
        note = "Найден допустимый план, оптимальность в лимите поиска не доказана."
    return SolverOutcome(
        engine="cp_sat_candidates",
        status=status,
        assignment=assignment,
        elapsed_ms=elapsed_ms,
        best_bound_kopecks=bound,
        objective_kopecks=objective,
        note=note,
    )


def _solver_number(value):
    return value() if callable(value) else value


def _status_note(status: str) -> str:
    if status == "UNKNOWN":
        return "За отведённый поиск новый полный план не найден."
    if status == "INFEASIBLE":
        return "В текущих ограничениях и вариантах маршрутов полный план не найден."
    return "Поиск завершился без допустимого полного плана."
