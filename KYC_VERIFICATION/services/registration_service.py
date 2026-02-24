import logging
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session
from repositories.user_repository import UserRepository
from models.user_profile import UserProfile

logger = logging.getLogger(__name__)

class RegistrationService:

    @staticmethod
    def create_profile(db: Session, request) -> UserProfile:
        m1_user = UserRepository.get_module1_user_by_id(db, request.user_id)
        if not m1_user:
            raise HTTPException(
                status_code=404,
                detail=f"User ID {request.user_id} not found. "
                       "Please register through the main app first."
            )
        if UserRepository.get_by_user_id(db, request.user_id):
            raise HTTPException(
                status_code=409,
                detail=f"KYC profile already exists for user ID {request.user_id}. "
                       "Use GET /api/v1/user/profile to check your status."
            )
        if UserRepository.get_by_email(db, request.email):
            raise HTTPException(status_code=409, detail="Email already registered")

        if UserRepository.get_by_pan_number(db, request.pan_number):
            raise HTTPException(status_code=409, detail="PAN number already registered")

        now = datetime.now(timezone.utc)
        new_user = UserProfile(
            user_id         = request.user_id, 
            email           = request.email,
            full_name       = request.full_name,
            pan_number      = request.pan_number,
            aadhaar_number  = request.aadhaar_number,
            dob             = request.dob,
            address         = request.address,
            employment_type = request.employment_type,
            monthly_income  = request.monthly_income,
            pan_status      = "PENDING",
            created_at      = now,
            updated_at      = now,
        )
        profile = UserRepository.create_user(db, new_user)
        logger.info(f"KYC profile created for user_id={request.user_id}")
        return profile

    @staticmethod
    def get_profile_by_user_id(db: Session, user_id: int) -> UserProfile:
        user = UserRepository.get_by_user_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="KYC profile not found for this user")
        return user

    @staticmethod
    def update_profile_by_user_id(db: Session, user_id: int, update_data) -> dict:
        user = UserRepository.get_by_user_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="KYC profile not found for this user")

        updated_fields = []

        if update_data.full_name is not None:
            if user.name_locked:
                raise HTTPException(403, "Name cannot be changed after PAN verification")
            user.full_name = update_data.full_name
            updated_fields.append("full_name")

        if update_data.pan_number is not None:
            if user.pan_locked:
                raise HTTPException(403, "PAN cannot be changed after verification")
            if UserRepository.get_by_pan_number(db, update_data.pan_number):
                raise HTTPException(409, "PAN number already in use by another account")
            user.pan_number = update_data.pan_number
            updated_fields.append("pan_number")

        if update_data.aadhaar_number is not None:
            if user.aadhaar_locked:
                raise HTTPException(403, "Aadhaar cannot be changed after verification")
            user.aadhaar_number = update_data.aadhaar_number
            updated_fields.append("aadhaar_number")

        if update_data.dob is not None:
            if user.dob_locked:
                raise HTTPException(403, "Date of birth cannot be changed after verification")
            user.dob = update_data.dob
            updated_fields.append("dob")

        if update_data.address is not None:
            user.address = update_data.address
            updated_fields.append("address")

        if update_data.employment_type is not None:
            user.employment_type = update_data.employment_type
            updated_fields.append("employment_type")

        if update_data.monthly_income is not None:
            user.monthly_income = update_data.monthly_income
            updated_fields.append("monthly_income")

        if not updated_fields:
            raise HTTPException(400, "No fields provided for update")

        user.updated_at = datetime.now(timezone.utc)
        UserRepository.update_user(db, user)
        logger.info(f"Profile updated for user_id={user_id}: {updated_fields}")

        return {
            "success": True,
            "message": "Profile updated successfully",
            "data": {
                "user_id":        user.user_id,
                "email":          user.email,
                "updated_fields": updated_fields,
            },
        }