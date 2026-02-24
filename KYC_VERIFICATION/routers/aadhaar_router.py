from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from services.aadhaar_verification_service import AadhaarVerificationService
import logging
from schemas.aadhaar_schema import AadhaarInitiateRequest, AadhaarInitiateResponse, AadhaarVerificationRequest, AadhaarVerificationResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/kyc", tags=["Aadhaar Verification"])

@router.post("/aadhaar-initiate", response_model=AadhaarInitiateResponse)
def initiate_aadhaar(request: AadhaarInitiateRequest, db: Session = Depends(get_db)):
    try:
        result = AadhaarVerificationService.initiate_aadhaar(user_id=request.user_id, db=db)
        return AadhaarInitiateResponse(**result)
    except HTTPException:
        raise
    except Exception:
        logger.error("Aadhaar initiate error", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to initiate Aadhaar verification")

@router.post("/aadhaar-verify", response_model=AadhaarVerificationResponse)
def verify_aadhaar(request: AadhaarVerificationRequest, db: Session = Depends(get_db)):
    try:
        result = AadhaarVerificationService.verify_aadhaar(
            db=db,
            user_id=request.user_id,
            initiate_token=request.initiate_token,
            auth_code=request.auth_code,
        )
        return AadhaarVerificationResponse(**result)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Aadhaar verification error")
        raise HTTPException(status_code=500, detail="Aadhaar verification service temporarily unavailable")
