from contextlib import asynccontextmanager
from server import runtime
import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

# Configure CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the actual frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
app.include_router(engram.router, prefix="/api/engram", tags=["engram"])


@app.get("/")
async def root():
    return {"message": "Mycelium API is running"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, workers=1)
