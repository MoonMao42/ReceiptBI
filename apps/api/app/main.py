"""
QueryGPT API 主应用
"""

import traceback
import uuid
from asyncio import TimeoutError as AsyncioTimeoutError
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError

from app.api.v1 import api_router
from app.core.config import settings
from app.core.demo_db import fix_demo_db_path, init_demo_database
from app.db import AsyncSessionLocal, engine
from app.db.base import Base
from app.services.engine_diagnostics import categorize_sql_error

# 配置日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer()
        if settings.LOG_FORMAT == "console"
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# 速率限制器：使用配置中的限制值
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_REQUESTS}/{settings.RATE_LIMIT_WINDOW}second"],
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理"""
    # 启动时 - 记录启动信息
    logger.info(
        "Starting QueryGPT API",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        debug_mode=settings.DEBUG,
    )

    # 验证密钥配置 - 生产/预发布环境必须显式配置
    try:
        settings.validate_secrets()
        # 记录安全状态
        if settings.is_using_default_secrets:
            logger.warning(
                "Using default encryption key (development mode only)",
                environment=settings.ENVIRONMENT,
            )
        else:
            logger.info(
                "Using explicit encryption key",
                environment=settings.ENVIRONMENT,
                key_length=len(settings.ENCRYPTION_KEY),
            )
    except ValueError as e:
        # 生产/预发布环境密钥未正确配置 - 立即失败
        logger.critical(
            "Startup validation failed: invalid encryption key configuration",
            environment=settings.ENVIRONMENT,
            error=str(e),
        )
        raise

    # 创建数据库表（开发环境）
    if settings.is_development:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")

    # 确保 demo.db 存在（构建时已预生成，这里只是 fallback）
    demo_db_path = init_demo_database()

    # 修正预打包数据库中的占位符路径
    async with AsyncSessionLocal() as session:
        await fix_demo_db_path(session, demo_db_path)
        await session.commit()

    logger.info(
        "Application startup complete",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )

    yield

    # 关闭时
    logger.info("Shutting down QueryGPT API")
    await engine.dispose()


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Natural language database query assistant",
    docs_url="/api/docs" if settings.is_development else None,
    redoc_url="/api/redoc" if settings.is_development else None,
    openapi_url="/api/openapi.json" if settings.is_development else None,
    lifespan=lifespan,
)

# 速率限制中间件
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions with structured logging and safe error responses.

    Per D-03: Concise error message to client, detailed info to structlog.
    Per D-04: Specific exception types, not bare except.
    Per D-05: Never expose stack traces, paths, or config in response.
    """
    error_id = str(uuid.uuid4())[:8]  # For request tracing
    status_code = 500
    error_code = "INTERNAL_ERROR"
    error_message = "服务器内部错误"

    try:
        # Handle specific exception types (D-04)
        if isinstance(exc, OperationalError):
            status_code = 500
            error_code, category, _ = categorize_sql_error(str(exc))
            error_message = "数据库连接错误"
            logger.error(
                "Database connection error",
                error_id=error_id,
                error_code=error_code,
                exception_detail=str(exc),
            )

        elif isinstance(exc, ProgrammingError):
            status_code = 400
            error_code, category, _ = categorize_sql_error(str(exc))
            error_message = "数据库查询错误"
            logger.error(
                "SQL programming error",
                error_id=error_id,
                error_code=error_code,
                exception_detail=str(exc),
            )

        elif isinstance(exc, SQLAlchemyError):
            status_code = 500
            error_message = "数据库错误"
            logger.error(
                "SQLAlchemy error",
                error_id=error_id,
                exception_detail=str(exc),
            )

        elif isinstance(exc, AsyncioTimeoutError):
            status_code = 504
            error_code = "TIMEOUT"
            error_message = "请求超时"
            logger.warning(
                "Asyncio timeout",
                error_id=error_id,
            )

        elif isinstance(exc, ValueError):
            status_code = 400
            error_message = "输入参数错误"
            logger.warning(
                "Validation error",
                error_id=error_id,
                exception_detail=str(exc),
            )

        elif isinstance(exc, RuntimeError):
            status_code = 500
            error_message = "服务器内部错误"
            logger.error(
                "Runtime error",
                error_id=error_id,
                exception_detail=str(exc),
            )

        else:
            # Unexpected exception type
            status_code = 500
            error_message = "服务器内部错误"
            logger.error(
                "Unexpected exception",
                error_id=error_id,
                error_type=type(exc).__name__,
                exception_detail=str(exc),
            )

    except Exception as logging_exc:
        # Error during error handling (don't crash)
        logger.error(
            "Error during exception handling",
            error_id=error_id,
            exception_detail=str(logging_exc),
        )

    # Per D-03 & D-05: Concise response, no stack trace or internal info
    response_data = {
        "success": False,
        "error": {
            "code": error_code,
            "message": error_message,
            "error_id": error_id,  # For client to reference when reporting
        },
    }

    # Per D-05: DEBUG mode check (don't expose stack traces in production)
    if settings.DEBUG:
        # In debug mode: include request path but NOT full stack trace
        response_data["debug_detail"] = str(exc)
        logger.debug(
            "Debug error details",
            request_path=str(request.url.path),
            full_exception=traceback.format_exc(),
        )

    return JSONResponse(
        status_code=status_code,
        content=response_data,
    )


# 注册路由
app.include_router(api_router, prefix="/api/v1")


# 健康检查
@app.get("/health")
async def health_check() -> dict[str, Any]:
    """健康检查"""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


# 根路由
@app.get("/")
async def root() -> dict[str, Any]:
    """根路由"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/api/docs" if settings.is_development else None,
    }


def run() -> None:
    """运行服务器"""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.is_development,
        workers=settings.WORKERS if not settings.is_development else 1,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    run()
