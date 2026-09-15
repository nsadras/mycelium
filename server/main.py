from contextlib import asynccontextmanager
from server import runtime
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from mycelium.operations import RetrievalError

from server.api import sessions, memory, engram

load_dotenv()

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app):
    memory = runtime.get_mem()
    try:
        yield
    finally:
        memory.close()
        runtime._mem = None


app = FastAPI(title="Mycelium API", lifespan=lifespan)


@app.exception_handler(RetrievalError)
async def retrieval_error(request, exc):
    return JSONResponse({"detail": str(exc), "stage": exc.stage, "retryable": True}, status_code=503)

# Requests use the UI origin; explicitly list private-network hostnames.
allowed_hosts = [host.strip() for host in os.environ.get(
    "MYCELIUM_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]"
).split(",") if host.strip()]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)


@app.middleware("http")
async def same_origin(request, call_next):
    from urllib.parse import urlsplit

    origin = request.headers.get("origin")
    if origin:
        try:
            parsed = urlsplit(origin)
            matches = parsed.scheme == request.url.scheme and parsed.netloc == request.headers.get("host")
        except ValueError:
            matches = False
        if not matches:
            return JSONResponse({"detail": "Cross-origin requests are not allowed"}, status_code=403)
    return await call_next(request)

# Include routers
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
app.include_router(engram.router, prefix="/api/engram", tags=["engram"])


ui_dist = Path(__file__).resolve().parents[1] / "ui" / "dist"
if ui_dist.is_dir():
    app.mount("/", StaticFiles(directory=ui_dist, html=True), name="ui")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.environ.get("MYCELIUM_API_HOST", "127.0.0.1"), port=8000, workers=1)
