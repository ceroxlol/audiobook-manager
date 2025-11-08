import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time

logger = logging.getLogger(__name__)

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            start_time = time.time()
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # Log slow requests
            if process_time > 5.0:  # 5 seconds
                logger.warning(
                    f"Slow request: {request.method} {request.url} "
                    f"took {process_time:.2f}s"
                )
            
            return response
            
        except HTTPException as http_exc:
            # FastAPI HTTP exceptions (like 404, 401, etc.)
            logger.warning(
                f"HTTPException: {http_exc.status_code} - {http_exc.detail} "
                f"for {request.method} {request.url}"
            )
            return JSONResponse(
                status_code=http_exc.status_code,
                content={"error": http_exc.detail}
            )
            
        except Exception as exc:
            # Unexpected exceptions
            logger.error(
                f"Unexpected error: {str(exc)} for {request.method} {request.url}",
                exc_info=True
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "detail": str(exc) if config.get('app.debug') else "An unexpected error occurred"
                }
            )