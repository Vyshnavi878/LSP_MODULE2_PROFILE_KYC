import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException
from models.attempt_tracker import VerificationType
from models.user_profile import UserProfile
from repositories.user_repository import UserRepository
from repositories.attempt_tracker_repository import AttemptTrackerRepository
from repositories.kyc_bank_verification_repository import KYCBankVerificationRepository
from providers.bank_provider import get_bank_provider
from core.config import BANK_MAX_ATTEMPTS, BANK_COOLDOWN_HOURS, VERIFICATION_MODE

logger = logging.getLogger(__name__)


class BankVerificationService:

    @staticmethod
    def verify_bank_account(
        db: Session,
        user: UserProfile,
        account_number: str,
        account_holder_name: str,
        bank_name: str,
        ifsc: str,
    ) -> dict:
        if user.bank_status == "VERIFIED":
            raise HTTPException(400, "Bank account already verified")
        existing = KYCBankVerificationRepository.get_verified_by_account_number(db, account_number)
        if existing and existing.user_id != user.user_id:
            raise HTTPException(409, "This bank account is already linked to another user")

        now = datetime.now(timezone.utc)
        tracker = AttemptTrackerRepository.get_or_create(db, user.email, VerificationType.BANK)

        if tracker.locked_until:
            locked_until = tracker.locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if locked_until > now:
                raise HTTPException(
                    423,
                    f"Bank verification blocked. Try after {BANK_COOLDOWN_HOURS} hours.",
                )
            AttemptTrackerRepository.reset_attempts(db, tracker)

        current_attempt = AttemptTrackerRepository.increment_attempt(db, tracker)

        if current_attempt > BANK_MAX_ATTEMPTS:
            AttemptTrackerRepository.lock_tracker(
                db, tracker, now + timedelta(hours=BANK_COOLDOWN_HOURS)
            )
            raise HTTPException(
                423,
                f"Maximum attempts ({BANK_MAX_ATTEMPTS}) exceeded. "
                f"Try after {BANK_COOLDOWN_HOURS} hours.",
            )

        provider = get_bank_provider()
        try:
            result = provider.verify(
                db=db,
                account_number=account_number,
                account_holder_name=account_holder_name,
                bank_name=bank_name,
                ifsc=ifsc,
            )
        except RuntimeError as e:
            AttemptTrackerRepository.decrement_attempt(db, tracker)
            raise HTTPException(503, str(e))

        verified_name = result.get("verified_name") or ""
        match_pct     = result.get("name_match_percentage", 0.0)
        if not result["success"]:
            if current_attempt >= BANK_MAX_ATTEMPTS:
                status = "BLOCKED"
                AttemptTrackerRepository.lock_tracker(
                    db, tracker, now + timedelta(hours=BANK_COOLDOWN_HOURS)
                )
                user.bank_status = "BLOCKED"
            else:
                status = "FAILED"
                user.bank_status = "FAILED"

            KYCBankVerificationRepository.create_verification_log(
                db=db,
                user_id=user.user_id,
                account_number=account_number,
                account_holder_name=account_holder_name,
                bank_name=bank_name,
                ifsc=ifsc,
                name_match_percentage=match_pct,
                status=status,
                failure_reason=result["failure_reason"],
                attempt_number=current_attempt,
            )
            UserRepository.save(db)

            remaining = BANK_MAX_ATTEMPTS - current_attempt
            http_code = 423 if status == "BLOCKED" else 400
            suffix = (f"{remaining} attempt(s) remaining."
                      if remaining > 0
                      else f"Blocked for {BANK_COOLDOWN_HOURS} hours.")
            raise HTTPException(http_code, f"{result['failure_reason']}. {suffix}")

        user.bank_status     = "VERIFIED"
        user.bank_locked     = True
        user.bank_verified_at = now

        KYCBankVerificationRepository.create_verification_log(
            db=db,
            user_id=user.user_id,
            account_number=account_number,
            account_holder_name=account_holder_name,
            bank_name=bank_name,
            ifsc=ifsc,
            name_match_percentage=match_pct,
            status="VERIFIED",
            failure_reason=None,
            attempt_number=current_attempt,
        )
        AttemptTrackerRepository.reset_attempts(db, tracker)
        UserRepository.update_user(db, user)

        logger.info(f"Bank verified for user {user.user_id} (mode={VERIFICATION_MODE})")

        return {
            "bank_status": "VERIFIED",
            "message":     "Bank account verified successfully",
        }
