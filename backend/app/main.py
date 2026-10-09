import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import next_request_id, router
from app.config import ENGINE_VERSION, ROOT
from app.data.repository import reload_repository
from app.errors import ApiError, CalculationError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    reload_repository()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Адаптивная логистика", version=ENGINE_VERSION, lifespan=lifespan)
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(CalculationError, _calculation_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unexpected)
    app.include_router(router, prefix="/api/v1")

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def unknown_api(path: str) -> JSONResponse:
        del path
        return _error_body(404, "NOT_FOUND", "Неизвестный адрес API.")

    dist = ROOT / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return app


def _error_body(status: int, code: str, message: str, fields: list | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "fields": fields or [],
                "request_id": next_request_id(),
            }
        },
    )


async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
    return _error_body(exc.status_code, exc.code, exc.message, exc.fields)


async def _calculation_error(_request: Request, _exc: CalculationError) -> JSONResponse:
    logger.exception("Расчёт не подтверждён проверкой")
    return _error_body(500, "INTERNAL", "Не удалось подтвердить план независимой проверкой.")


async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = []
    for item in exc.errors():
        loc = [str(part) for part in item.get("loc", []) if part != "body"]
        fields.append({"path": ".".join(loc), "message": item.get("msg", "Некорректное значение")})
    return _error_body(422, "INVALID_SCENARIO", "Некорректный запрос.", fields)


async def _unexpected(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Необработанная ошибка")
    return _error_body(500, "INTERNAL", "Внутренняя ошибка расчёта.")


app = create_app()
