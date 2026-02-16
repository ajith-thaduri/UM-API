"""Main FastAPI application entry point"""

import logging
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.security import validate_secret_key
from app.core.exceptions import (
    BaseAppException,
    NotFoundException,
    ValidationException,
    ConflictException,
)
from contextlib import asynccontextmanager
from app.api.v1 import api_router
from app.middleware.rate_limit import rate_limit_middleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    # Set exception handler to suppress harmless httpx cleanup errors
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(handle_task_exception)
    logger.info("Application startup complete")
    
    # Init Models
    try:
        from app.db.session import SessionLocal
        from app.repositories.llm_model_repository import LLMModelRepository
        db = SessionLocal()
        LLMModelRepository().seed_defaults(db)
        db.close()
        logger.info("LLM Models seeded successfully")
    except Exception as e:
        logger.warning(f"Failed to seed LLM models: {e}")
    
    yield
    
    # Cleanup on application shutdown
    try:
        from app.services.llm.llm_factory import close_all_llm_services
        await close_all_llm_services()
        logger.info("Application shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)

# Validate security settings on startup
validate_secret_key()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Suppress harmless httpx/AsyncAnthropic background task exceptions
def handle_task_exception(loop, context):
    """Handle unretrieved task exceptions, suppressing harmless httpx cleanup errors"""
    exception = context.get('exception')
    task = context.get('task')
    
    if exception:
        error_str = str(exception).lower()
        # Suppress harmless httpx connection cleanup errors
        if any(phrase in error_str for phrase in [
            "unable to perform operation",
            "handler is closed",
            "tcp transport closed",
            "transport closed"
        ]):
            # This is a harmless error - connection is already closed
            logger.debug(f"Suppressed harmless background task exception: {type(exception).__name__}")
            return  # Suppress the error
    
    # For other exceptions, use default handling (log them)
    if exception:
        logger.error(f"Unretrieved task exception: {exception}", exc_info=exception)
    elif 'message' in context:
        logger.error(f"Unretrieved task error: {context['message']}")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered medical record summarization for Utilization Management",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Apply middleware in reverse order of addition (last added is outermost)
# 1. Custom Rate Limiting (Inner)
@app.middleware("http")
async def rate_limit(request, call_next):
    return await rate_limit_middleware(request, call_next)

# 2. CORS (Outer - handles preflight before anything else)
allowed_origins = [str(origin).rstrip("/") for origin in settings.CORS_ORIGINS]
logger.info(f"Setting up CORS with allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.get("/")
async def root():
    """Health check endpoint"""
    return JSONResponse(
        content={
            "message": "Brightcone UM Shield API",
            "version": settings.APP_VERSION,
            "status": "running",
        }
    )


@app.get("/health")
async def health_check():
    """Detailed health check"""
    return JSONResponse(
        content={
            "status": "healthy",
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }
    )


# Global exception handlers
@app.exception_handler(BaseAppException)
async def app_exception_handler(request: Request, exc: BaseAppException):
    """Handle custom application exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent format"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    logger = logging.getLogger(__name__)
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "status_code": 500,
        },
    )


# Include API routes
app.include_router(api_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )

