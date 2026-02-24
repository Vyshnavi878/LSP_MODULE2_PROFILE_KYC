from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from services.pan_verification_service import PANVerificationService
import logging
from schemas.pan_schema import PANVerificationRequest, PANVerificationResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/kyc", tags=["PAN Verification"])

@router.post("/pan-verify", response_model=PANVerificationResponse)
def verify_pan(request: PANVerificationRequest, db: Session = Depends(get_db)):
    try:
        result = PANVerificationService.verify_pan(db=db, user_id=request.user_id)
        return PANVerificationResponse(
            message=result["message"],
            pan_status=result["pan_status"],
            verified_name=result.get("verified_name"),
            identity_status=result["identity_status"],
            next_step=result["next_step"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PAN verification error: {str(e)}")
        raise HTTPException(status_code=500, detail="PAN verification service temporarily unavailable")
