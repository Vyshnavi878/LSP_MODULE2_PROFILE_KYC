from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from core.database import get_db
from schemas.user_profile_schema import UserRegistrationRequest, UserRegistrationResponse, UserProfileUpdateRequest, UserProfileUpdateResponse
import logging
from services.registration_service import RegistrationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/user", tags=["User Profile"])

@router.get("/profile")
def get_user_profile(
    user_id: int = Query(..., description="User ID"),
    db: Session = Depends(get_db),
):
    try:
        user = RegistrationService.get_profile_by_user_id(db, user_id)
        return {
            "user_id": user.user_id,
            "email": user.email,
            "full_name": user.full_name,
            "dob": user.dob.isoformat(),
            "address": user.address,
            "employment_type": user.employment_type,
            "monthly_income": float(user.monthly_income),
            "aadhaar_number": user.aadhaar_number,
            "pan_number":user.pan_number,
            "pan_status": user.pan_status,
            "aadhaar_status": user.aadhaar_status,
            "bank_status": user.bank_status,
            "document_status": user.document_status,
            "identity_status": user.identity_status,
            "kyc_status":user.kyc_status,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get profile error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch user profile")


@router.post("/profile", response_model=UserRegistrationResponse, status_code=201)
def create_user_profile(
    request: UserRegistrationRequest,
    db: Session = Depends(get_db),
):
    result = RegistrationService.create_profile(db, request)
    return {
        "user_id":        result.user_id,
        "message":        "Profile created successfully. Proceed to PAN verification.",
        "pan_status":     result.pan_status,
        "aadhaar_status": result.aadhaar_status,
        "bank_status":    result.bank_status,
        "document_status": result.document_status,
        "kyc_status":     result.kyc_status,
        "next_step":      "Verify your PAN",
    }



@router.put("/profile")
def update_user_profile(
    user_id: int = Query(..., description="User ID"),
    request: UserProfileUpdateRequest = ...,
    db: Session = Depends(get_db),
):
    try:
        result = RegistrationService.update_profile_by_user_id(db, user_id, request)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update profile error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update profile")
