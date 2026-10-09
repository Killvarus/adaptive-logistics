import logging
import time
import uuid

from app.config import ENGINE_VERSION, SCHEMA_VERSION, SOLVER_TIME_LIMIT_S
from app.data.catalog import Catalog
from app.domain.hashing import canonical_hash, scenario_payload
from app.domain.models import (
    ComputationMetadata,
    Diagnostic,
    EffectiveParameters,
    EvaluationResponse,
    MarketImpact,
    OptimizationResponse,
    Plan,
    ProvenanceSummary,
    ScenarioInput,
    SolverInfo,
    ValidationReport,
    WarningItem,
)
from app.domain.money import round_half_up
from app.economics.comparison import compare_plans
from app.economics.ledger import compute_plan
from app.errors import CalculationError
from app.explanations import explain
from app.planning.baseline import reprice_assignment, run_baseline
from app.planning.candidates import generate_candidates, priced_offers
from app.planning.cp_sat import SolverOutcome, solve_cp_sat
from app.planning.fallback import fallback_search
from app.planning.types import Assignment
from app.simulation.scenarios import ScenarioSnapshot, build_snapshot, zero_scenario
from app.validation import validate_plan

logger = logging.getLogger(__name__)


def evaluate(catalog: Catalog, scenario_input: ScenarioInput) -> EvaluationResponse:
    started = time.perf_counter()
    prepared = _prepare(catalog, scenario_input, include_candidates=False)
    return _evaluation_response(prepared, started)


def optimize(catalog: Catalog, scenario_input: ScenarioInput) -> OptimizationResponse:
    started = time.perf_counter()
    prepared = _prepare(catalog, scenario_input, include_candidates=True)
    outcome = _search_prepared(prepared)
    plan_c, quality, business, diagnostics = _choose_adapted_plan(prepared, outcome)
    changes = explain(prepared.baseline, plan_c, prepared.notes)
    comparison = compare_plans(prepared.baseline, plan_c) if plan_c is not None else None
    if business == "infeasible":
        diagnostics.insert(
            0,
            Diagnostic(
                code="no_complete_plan",
                message="В текущих ограничениях и вариантах маршрутов полный план не найден.",
                order_ids=[item.order_id for item in prepared.baseline.unserved_orders],
            ),
        )
    if business == "unresolved":
        diagnostics.insert(
            0,
            Diagnostic(
                code="search_timeout",
                message="За отведённый поиск новый полный план не найден.",
            ),
        )
    response = _evaluation_response(prepared, started)
    return OptimizationResponse(
        **response.model_dump(),
        business_status=business,
        optimized=plan_c,
        comparison=comparison,
        changes=changes,
        diagnostics=diagnostics,
        solver=SolverInfo(
            engine=outcome.engine,  # type: ignore[arg-type]
            solver_status=outcome.status,
            solution_quality=quality,  # type: ignore[arg-type]
            candidate_count=len(prepared.candidates),
            generated_max_chain_length=3,
            elapsed_ms=outcome.elapsed_ms,
            best_bound_kopecks=outcome.best_bound_kopecks,
            note=outcome.note,
        ),
    )


class _Prepared:
    def __init__(
        self,
        scenario_input: ScenarioInput,
        user: ScenarioSnapshot,
        original: Plan,
        baseline: Plan,
        warnings: list[WarningItem],
        scenario_hash: str,
        candidates,
        notes,
    ) -> None:
        self.scenario_input = scenario_input
        self.user = user
        self.original = original
        self.baseline = baseline
        self.warnings = warnings
        self.scenario_hash = scenario_hash
        self.candidates = candidates
        self.notes = notes


def _prepare(catalog: Catalog, scenario_input: ScenarioInput, *, include_candidates: bool) -> _Prepared:
    user = build_snapshot(catalog, scenario_input)
    meta = catalog.dataset.metadata
    base = build_snapshot(catalog, zero_scenario(meta.dataset_id, meta.dataset_version))
    scenario_hash = _hash_input(scenario_input)
    base_hash = _hash_input(zero_scenario(meta.dataset_id, meta.dataset_version))
    assignment_a = run_baseline(base)
    original = _finish("A", assignment_a, base, base_hash, None, "Исходная политика на базовых условиях.")
    if user.structural_change:
        assignment_b = run_baseline(user)
        mode = "replay_policy"
        reason = _replay_reason(user)
    else:
        repriced = reprice_assignment(assignment_a, user)
        if repriced is None:
            assignment_b = run_baseline(user)
            mode = "replay_policy"
            reason = "Исходные назначения не переносятся; исходная политика применена повторно."
        else:
            assignment_b = repriced
            mode = "reprice_existing"
            reason = _reprice_reason(user)
    baseline = _finish("B", assignment_b, user, scenario_hash, mode, reason)
    warnings: list[WarningItem] = []
    if baseline.service_status == "partial":
        warnings.append(
            WarningItem(
                code="partial_baseline",
                message="Исходная политика не назначила все активные заказы.",
            )
        )
    if include_candidates:
        candidates, notes = generate_candidates(user, assignment_b)
    else:
        candidates, notes = [], []
    return _Prepared(scenario_input, user, original, baseline, warnings, scenario_hash, candidates, notes)


def _finish(plan_id, assignment: Assignment, snapshot, scenario_hash, mode, reason) -> Plan:
    plan = compute_plan(
        plan_id=plan_id,
        kind=plan_id,
        assignment=assignment,
        snapshot=snapshot,
        scenario_hash=scenario_hash,
        baseline_mode=mode,
        baseline_mode_reason=reason,
        validation=ValidationReport(ok=True, checks=[]),
    )
    report = validate_plan(plan, snapshot)
    if not report.ok:
        failed = [f"{check.id}: {check.message}" for check in report.checks if check.status == "fail"]
        logger.error("Проверка плана %s не пройдена: %s", plan_id, "; ".join(failed))
        raise CalculationError("plan validation failed")
    return plan.model_copy(update={"validation": report})


def _search_prepared(prepared: _Prepared) -> SolverOutcome:
    offers = priced_offers(prepared.user)
    started = time.perf_counter()
    try:
        outcome = solve_cp_sat(
            prepared.candidates,
            offers,
            prepared.user.active_orders,
            list(prepared.user.catalog.carriers.values()),
            time_limit_s=SOLVER_TIME_LIMIT_S,
            elapsed_ms=0,
        )
    except CalculationError:
        raise
    except Exception:
        logger.exception("CP-SAT завершился ошибкой, включён локальный поиск")
        outcome = None
    elapsed_ms = int(round((time.perf_counter() - started) * 1000))
    if outcome is not None and outcome.status in {"OPTIMAL", "FEASIBLE", "INFEASIBLE", "NOT_RUN"}:
        outcome.elapsed_ms = elapsed_ms
        return outcome
    fallback_started = time.perf_counter()
    assignment = fallback_search(
        prepared.user,
        run_baseline(prepared.user),
        prepared.candidates,
        time_limit_s=SOLVER_TIME_LIMIT_S,
    )
    fallback_ms = int(round((time.perf_counter() - fallback_started) * 1000))
    status = "UNKNOWN" if outcome is None or outcome.status == "UNKNOWN" else outcome.status
    return SolverOutcome(
        engine="fallback_local_search",
        status=status if assignment is None else "FEASIBLE",
        assignment=assignment,
        elapsed_ms=elapsed_ms + fallback_ms,
        best_bound_kopecks=None,
        objective_kopecks=None,
        note="Эвристический поиск; оптимальность не доказана.",
    )


def _choose_adapted_plan(prepared: _Prepared, outcome: SolverOutcome):
    diagnostics = [
        Diagnostic(code=item.reason_code, message=item.message, order_ids=[item.order_id])
        for item in prepared.baseline.unserved_orders
    ]
    for note in prepared.notes:
        diagnostics.append(Diagnostic(code="constraint", message=note.message, vehicle_ids=[note.vehicle_id]))
    baseline_complete = prepared.baseline.service_status == "complete"
    solver_plan = None
    if outcome.assignment is not None:
        solver_plan = _finish(
            "C",
            outcome.assignment,
            prepared.user,
            prepared.scenario_hash,
            None,
            None,
        )
        if outcome.objective_kopecks is not None:
            variable = sum(route.variable_cost_kopecks for route in solver_plan.routes)
            variable += sum(item.price_kopecks for item in solver_plan.outsourced_assignments)
            if variable != outcome.objective_kopecks:
                logger.error("Цель solver %s, переменные затраты плана %s", outcome.objective_kopecks, variable)
                raise CalculationError("objective mismatch")
    use_solver = solver_plan is not None and solver_plan.service_status == "complete" and (
        not baseline_complete or solver_plan.metrics.total_cost_kopecks < prepared.baseline.metrics.total_cost_kopecks
    )
    if use_solver and solver_plan is not None:
        if outcome.engine == "cp_sat_candidates" and outcome.status == "OPTIMAL":
            quality = "optimal_within_candidates"
        elif outcome.engine == "fallback_local_search":
            quality = "heuristic"
        else:
            quality = "feasible"
        return solver_plan, quality, "complete", diagnostics
    if baseline_complete:
        retained = prepared.baseline.model_copy(
            update={"id": "C", "kind": "C", "baseline_mode": None, "baseline_mode_reason": None}
        )
        if outcome.note and outcome.status == "UNKNOWN":
            outcome.note = "За отведённый поиск новый полный план не найден. Оставлен проверенный исходный план."
        elif outcome.status in {"OPTIMAL", "FEASIBLE"}:
            outcome.note = "Среди проверенных вариантов более дешёвого полного плана нет. Оставлен исходный план."
        return retained, "baseline_retained", "complete", diagnostics
    if outcome.status == "UNKNOWN":
        return None, "none", "unresolved", diagnostics
    return None, "none", "infeasible", diagnostics


def _evaluation_response(prepared: _Prepared, started: float) -> EvaluationResponse:
    snapshot = prepared.user
    catalog = snapshot.catalog
    meta = catalog.dataset.metadata
    elapsed_ms = int(round((time.perf_counter() - started) * 1000))
    resources_changed = bool(
        snapshot.disabled_vehicles or snapshot.disabled_drivers or snapshot.maintenance_overrides
    )
    notes = [
        "Изменились заказы или доступность ресурсов. Разница B−A не является чистым эффектом цен."
        if snapshot.structural_change
        else "Назначения совпадают с исходным планом. Пересчитаны только ставки."
    ]
    mode = prepared.baseline.baseline_mode or "reprice_existing"
    return EvaluationResponse(
        schema_version=SCHEMA_VERSION,  # type: ignore[arg-type]
        run_id=uuid.uuid4().hex,
        scenario_hash=prepared.scenario_hash,
        dataset_hash=catalog.dataset_hash,
        input=prepared.scenario_input,
        effective_parameters=EffectiveParameters(
            fuel_price_kopecks_per_liter=round_half_up(snapshot.fuel_price),
            fuel_change_pct=snapshot.scenario.fuel_change_pct,
            wage_change_pct=snapshot.scenario.wage_change_pct,
            carrier_rate_change_pct=snapshot.scenario.carrier_rate_change_pct,
            customer_rate_change_pct=snapshot.scenario.customer_rate_change_pct,
            demand_change_pct=snapshot.scenario.demand_change_pct,
            active_order_count=len(snapshot.active_orders),
            base_active_order_count=catalog.dataset.base_active_count,
            disabled_vehicle_ids=sorted(snapshot.disabled_vehicles),
            disabled_driver_ids=sorted(snapshot.disabled_drivers),
            maintenance_remaining_overrides_m=dict(sorted(snapshot.maintenance_overrides.items())),
        ),
        active_order_ids=[order.id for order in snapshot.active_orders],
        original=prepared.original,
        baseline=prepared.baseline,
        market_impact=MarketImpact(
            operating_result_delta_kopecks=(
                prepared.baseline.metrics.operating_result_kopecks
                - prepared.original.metrics.operating_result_kopecks
            ),
            cost_delta_kopecks=prepared.baseline.metrics.total_cost_kopecks
            - prepared.original.metrics.total_cost_kopecks,
            revenue_delta_kopecks=prepared.baseline.metrics.recognized_revenue_kopecks
            - prepared.original.metrics.recognized_revenue_kopecks,
            active_orders_changed=snapshot.scenario.demand_change_pct != 0,
            resources_changed=resources_changed,
            baseline_mode=mode,
            notes=notes,
        ),
        warnings=prepared.warnings,
        provenance=ProvenanceSummary(
            dataset_kind=meta.dataset_kind,
            disclaimer=meta.disclaimer,
            cards=list(catalog.dataset.provenance),
        ),
        computation=ComputationMetadata(
            engine_version=ENGINE_VERSION,
            elapsed_ms=elapsed_ms,
            dataset_id=meta.dataset_id,
            dataset_version=meta.dataset_version,
            dataset_hash=catalog.dataset_hash,
        ),
    )


def _hash_input(scenario_input: ScenarioInput) -> str:
    payload = scenario_payload(
        scenario_input.dataset_id,
        scenario_input.dataset_version,
        scenario_input.objective,
        scenario_input.scenario,
    )
    return canonical_hash(payload)


def _replay_reason(snapshot: ScenarioSnapshot) -> str:
    orders_changed = snapshot.scenario.demand_change_pct != 0
    resources_changed = bool(
        snapshot.disabled_vehicles or snapshot.disabled_drivers or snapshot.maintenance_overrides
    )
    if orders_changed and resources_changed:
        return "Набор заказов и ресурсов изменился; исходная политика применена повторно."
    if resources_changed:
        return "Набор ресурсов изменился; исходная политика применена повторно."
    return "Набор заказов изменился; исходная политика применена повторно."


def _reprice_reason(snapshot: ScenarioSnapshot) -> str:
    scenario = snapshot.scenario
    unchanged = (
        scenario.fuel_change_pct == 0
        and scenario.wage_change_pct == 0
        and scenario.carrier_rate_change_pct == 0
        and scenario.customer_rate_change_pct == 0
    )
    if unchanged:
        return "Параметры совпадают с исходными условиями; назначения переоценены без смены маршрутов."
    return "Денежные ставки изменены; назначения исходного плана переоценены без смены маршрутов."


def ortools_available() -> bool:
    try:
        import ortools.sat.python.cp_model  # noqa: F401

        return True
    except ImportError:
        return False
