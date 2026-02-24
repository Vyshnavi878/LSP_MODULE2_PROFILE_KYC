from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from repositories.user_repository import UserRepository
from schemas.bank_schema import BankVerificationRequest, BankVerificationResponse
from services.bank_verification_service import BankVerificationService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/kyc", tags=["Bank Verification"])

@router.post("/bank-verify", response_model=BankVerificationResponse)
def verify_bank(request: BankVerificationRequest, db: Session = Depends(get_db)):
    try:
        user = UserRepository.get_by_user_id(db, request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user.identity_status != "VERIFIED":
            raise HTTPException(400, "Please complete identity verification (PAN + Aadhaar) before bank verification")

        if user.bank_status == "VERIFIED":
            return BankVerificationResponse(
                message="Bank already verified",
                next="Upload required documents"
            )

        BankVerificationService.verify_bank_account(
            db=db,
            user=user,
            account_number=request.account_number,
            account_holder_name=request.account_holder_name,
            bank_name=request.bank_name,
            ifsc=request.ifsc,
        )
        return BankVerificationResponse(
            message="Bank account verified successfully",
            next="Upload required documents for final KYC approval"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bank verification error: {str(e)}")
        raise HTTPException(status_code=500, detail="Verification service temporarily unavailable")