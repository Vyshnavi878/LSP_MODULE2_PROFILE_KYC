import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException
from models.attempt_tracker import VerificationType
from repositories.user_repository import UserRepository
from repositories.attempt_tracker_repository import AttemptTrackerRepository
from repositories.kyc_pan_verification_repository import KYCPANVerificationRepository
from providers.pan_provider import get_pan_provider
from core.config import PAN_MAX_ATTEMPTS, PAN_COOLDOWN_HOURS

logger = logging.getLogger(__name__)

class PANVerificationService:

    @staticmethod
    def verify_pan(db: Session, user_id: int) -> dict:
        user = UserRepository.get_by_user_id(db, user_id)
        if not user:
            raise HTTPException(404, "User not found")
        if user.pan_status == "VERIFIED":
            return {
                "message":         "PAN already verified",
                "pan_status":      "VERIFIED",
                "verified_name":   user.verified_name,
                "identity_status": user.identity_status,
                "next_step":       "Proceed to Aadhaar verification",
            }

        now = datetime.now(timezone.utc)
        tracker = AttemptTrackerRepository.get_or_create(db, user.email, VerificationType.PAN)

        if tracker.locked_until:
            locked_until = tracker.locked_until
            if locked_until.tzinfo is None:
                from datetime import timezone as tz
                locked_until = locked_until.replace(tzinfo=tz.utc)
            if locked_until > now:
                raise HTTPException(
                    423,
                    f"PAN verification blocked due to {PAN_MAX_ATTEMPTS} failed attempts. "
                    f"Try again after {PAN_COOLDOWN_HOURS} hours.",
                )

            AttemptTrackerRepository.reset_attempts(db, tracker)

        current_attempt = AttemptTrackerRepository.increment_attempt(db, tracker)
        logger.info(f"PAN verification attempt {current_attempt}/{PAN_MAX_ATTEMPTS} for user_id={user_id}")

        if current_attempt > PAN_MAX_ATTEMPTS:
            AttemptTrackerRepository.lock_tracker(
                db, tracker, now + timedelta(hours=PAN_COOLDOWN_HOURS)
            )
            raise HTTPException(
                423,
                f"Maximum attempts ({PAN_MAX_ATTEMPTS}) exceeded. "
                f"Account blocked for {PAN_COOLDOWN_HOURS} hours.",
            )
        provider = get_pan_provider()
        try:
            result = provider.verify(db=db, pan_number=user.pan_number, full_name=user.full_name)
        except RuntimeError as e:
            AttemptTrackerRepository.decrement_attempt(db, tracker)
            raise HTTPException(503, str(e))

        verified_name = result.get("verified_name") or ""
        match_pct     = result.get("match_percentage", 0.0)

        if not result["success"]:
            if current_attempt >= PAN_MAX_ATTEMPTS:
                status = "BLOCKED"
                AttemptTrackerRepository.lock_tracker(
                    db, tracker, now + timedelta(hours=PAN_COOLDOWN_HOURS)
                )
                user.pan_status = "BLOCKED"
                msg = f"Maximum attempts reached. Blocked for {PAN_COOLDOWN_HOURS} hours."
            else:
                status = "FAILED"
                user.pan_status = "FAILED"
                remaining = PAN_MAX_ATTEMPTS - current_attempt
                msg = f"{remaining} attempt(s) remaining."

            KYCPANVerificationRepository.create_verification_log(
                db=db,
                user_id=user.user_id,
                pan_number=user.pan_number,
                full_name_submitted=user.full_name,
                verified_name=verified_name,
                match_percentage=match_pct,
                name_match=False,
                status=status,
                failure_reason=result["failure_reason"],
                attempt_number=current_attempt,
            )
            UserRepository.save(db)

            http_code = 423 if status == "BLOCKED" else 400
            raise HTTPException(http_code, f"{result['failure_reason']}. {msg}")
        user.pan_status     = "VERIFIED"
        user.verified_name  = verified_name
        user.pan_locked     = True
        user.name_locked    = True
        user.pan_verified_at = now

        if user.aadhaar_status == "VERIFIED":
            user.identity_status = "VERIFIED"

        KYCPANVerificationRepository.create_verification_log(
            db=db,
            user_id=user.user_id,
            pan_number=user.pan_number,
            full_name_submitted=user.full_name,
            verified_name=verified_name,
            match_percentage=match_pct,
            name_match=True,
            status="VERIFIED",
            failure_reason=None,
            attempt_number=current_attempt,
        )
        AttemptTrackerRepository.reset_attempts(db, tracker)
        UserRepository.update_user(db, user)

        logger.info(f"PAN verified for user {user.user_id} (mode={__import__('core.config', fromlist=['VERIFICATION_MODE']).VERIFICATION_MODE})")

        return {
            "message":         "PAN verified successfully",
            "pan_status":      "VERIFIED",
            "verified_name":   user.verified_name,
            "identity_status": user.identity_status,
            "next_step":       "Proceed to Aadhaar verification",
        }
