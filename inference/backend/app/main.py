from fastapi import FastAPI
from app.api.routes import router as api_router
from fastapi.middleware.cors import CORSMiddleware
from app.methods.schwab_methods import schwab_data_backend_update, get_inf_config
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
import logging
from contextlib import asynccontextmanager
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("Realtime sync")
# print("==Python Path==")
# for path in sys.path:
#     print(path)

print("== File system check ==")
print("Exists", os.path.exists("/usr/local/lib/python3.10/site-packages/trading_functions"))



scheduler = AsyncIOScheduler()

origins = [
    "http://localhost:3002",
    "http://localhost:3000",
    "http://localhost:3001",
    "https://rahulpradeep.com",
    "http://localhost:6202",
    "http://localhost:8501",
    "http://streamlit:8501",
    "http://inf_frontend:6202"
]



def job_listener(event):
    if event.exception:
        logger.error(f"Job {event.job_id} failed with exception: {event.exception}")
    else:
        logger.info(f"Job {event.job_id} completed successfully.")

scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

@asynccontextmanager
async def lifespan(app: FastAPI):
    conf = get_inf_config()
    realtime_job_frequency = conf['inference']['schwab']['realtime_job_frequency']
    logger.info("Starting the scheduler...")

    scheduler.add_job(
        schwab_data_backend_update,
        'interval',
        seconds=int(realtime_job_frequency),
        id='realtime_sync_job',
        replace_existing=True,
        max_instances=1,
        kwargs={
            'symbol': 'SPY'
        }
    )
    scheduler.start()

    yield

    logger.info("Shutting down the scheduler...")
    scheduler.shutdown(wait=True)

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/health")
def health_check():
    jobs = scheduler.get_jobs()
    return {
        "scheduler_running": scheduler.running,
        "job_count": len(jobs),
        "jobs": [
            {
                "id": job.id,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in jobs
        ]
    }

@app.get("/")
def home():
    return {"message": "FastAPI with APScheduler is running!"}