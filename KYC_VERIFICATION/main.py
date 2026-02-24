import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
import os
from core.database import Base, engine
from routers.profile_router import router as profile_router
from routers.pan_router import router as pan_router
from routers.aadhaar_router import router as aadhaar_router
from routers.bank_router import router as bank_router
from routers.document_router import router as document_router
from routers.admin_router import router as admin_router
from services.auto_cleanup import AutoCleanup
import models.module1_user

logging.basicConfig( level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

auto_cleanup = AutoCleanup(interval_hours=24)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting KYC backend...")
    Base.metadata.create_all(bind=engine, checkfirst=True)
    logger.info("Database tables created")

    upload_dirs = ["uploads","uploads/aadhaar","uploads/pan","uploads/salary_slips","uploads/bank_statements"]
    for dir_path in upload_dirs:
        os.makedirs(dir_path, exist_ok=True)
    logger.info("Upload directories ready")

    auto_cleanup.start()
    logger.info("Auto cleanup service started")

    yield

    auto_cleanup.stop()
    logger.info("Auto cleanup service stopped")
    logger.info("KYC backend stopped")

app = FastAPI(title="KYC Verification Module",lifespan=lifespan)

app.include_router(profile_router)
app.include_router(pan_router)
app.include_router(aadhaar_router)
app.include_router(bank_router)
app.include_router(document_router)
app.include_router(admin_router)

@app.get("/")
def root():
    return {
        "status":"Profile KYC Verification API is running"
    }