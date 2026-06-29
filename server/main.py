import logging

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from server.api import sessions, memory, settings
from server.runtime import flush_idle_episodes, get_mem, run_decay, run_dream

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Mycelium API")
scheduler = AsyncIOScheduler()

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
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])


@app.on_event("startup")
async def start_memory_scheduler():
    mem = get_mem()
    scheduler.add_job(
        flush_idle_episodes,
        "interval",
        minutes=5,
        kwargs={"idle_minutes": 20, "max_turns": 25, "force": False},
        id="flush_idle_episodes",
        replace_existing=True,
    )
    scheduler.add_job(
        run_dream,
        "interval",
        minutes=30,
        id="dream_process",
        replace_existing=True,
    )
    scheduler.add_job(
        run_decay,
        "interval",
        hours=mem.config.decay.interval_hours,
        id="decay_pass",
        replace_existing=True,
    )
    scheduler.start()


@app.on_event("shutdown")
async def stop_memory_scheduler():
    await flush_idle_episodes(force=True)
    if scheduler.running:
        scheduler.shutdown(wait=False)

@app.get("/")
async def root():
    return {"message": "Mycelium API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
