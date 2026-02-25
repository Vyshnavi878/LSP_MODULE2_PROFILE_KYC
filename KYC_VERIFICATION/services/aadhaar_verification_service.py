import logging
import secrets
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException

from models.attempt_tracker import VerificationType
from repositories.user_repository import UserRepository
from repositories.attempt_tracker_repository import AttemptTrackerRepository
from repositories.kyc_aadhaar_verification_repository import KYCAadhaarVerificationRepository
from providers.aadhaar_provider import get_aadhaar_provider
from core.config import AADHAAR_MAX_ATTEMPTS, AADHAAR_COOLDOWN_HOURS, VERIFICATION_MODE

logger = logging.getLogger(__name__)

AADHAAR_TOKEN_EXPIRY_MINUTES = 10   # each token valid 10 mins


def _clear_aadhaar_session(user):
    user.aadhaar_initiate_token      = None
    user.aadhaar_token_created_at    = None
    user.aadhaar_token_attempt_count = 0


class AadhaarVerificationService:

    @staticmethod
    def initiate_aadhaar(user_id: int, db: Session) -> dict:
        """
        Every call generates a FRESH token.
        Each initiate counts as 1 attempt (max 3 total).
        After 3 initiates with failures → 24hr block.

        Flow:
            Initiate → Token-1 → wrong → attempt=1
            Initiate → Token-2 → wrong → attempt=2
            Initiate → Token-3 → wrong → attempt=3 → BLOCKED 24hrs
        """
        user = UserRepository.get_by_user_id(db, user_id)
        if not user:
            raise HTTPException(404, "User not found")

        if user.pan_status != "VERIFIED":
            raise HTTPException(400, "Please complete PAN verification before Aadhaar verification")

        if user.aadhaar_status == "VERIFIED":
            raise HTTPException(400, "Aadhaar is already verified")

        # ── Check global cooldown (24hr block active?) ────────────────────────
        now     = datetime.now(timezone.utc)
        tracker = AttemptTrackerRepository.get_or_create(db, user.email, VerificationType.AADHAAR)

        if tracker.locked_until:
            locked_until = tracker.locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if locked_until > now:
                remaining_hrs = round((locked_until - now).total_seconds() / 3600, 1)
                raise HTTPException(
                    423,
                    f"Aadhaar verification is blocked for {remaining_hrs} more hour(s) "
                    f"due to too many failed attempts."
                )
            # Block expired — reset
            AttemptTrackerRepository.reset_attempts(db, tracker)

        # ── Check how many initiates already done ─────────────────────────────
        current_initiates = AttemptTrackerRepository.increment_attempt(db, tracker)

        if current_initiates > AADHAAR_MAX_ATTEMPTS:
            # Should not reach here normally (blocked above), but safety net
            AttemptTrackerRepository.lock_tracker(
                db, tracker, now + timedelta(hours=AADHAAR_COOLDOWN_HOURS)
            )
            _clear_aadhaar_session(user)
            UserRepository.save(db)
            raise HTTPException(
                423,
                f"Maximum attempts ({AADHAAR_MAX_ATTEMPTS}) exceeded. "
                f"Aadhaar verification blocked for {AADHAAR_COOLDOWN_HOURS} hours."
            )

        # ── Generate fresh token (invalidates any previous token) ─────────────
        token = secrets.token_hex(32)
        user.aadhaar_initiate_token      = token
        user.aadhaar_token_created_at    = now
        user.aadhaar_token_attempt_count = 0
        UserRepository.save(db)

        attempts_used      = current_initiates
        attempts_remaining = AADHAAR_MAX_ATTEMPTS - attempts_used

        logger.info(
            f"Aadhaar initiate #{attempts_used}/{AADHAAR_MAX_ATTEMPTS} "
            f"for user_id={user_id} — token valid {AADHAAR_TOKEN_EXPIRY_MINUTES} min"
        )

        provider = get_aadhaar_provider()

        base_msg = (
            f"Aadhaar session started. "
            f"Token valid for {AADHAAR_TOKEN_EXPIRY_MINUTES} minutes. "
            f"Attempt {attempts_used}/{AADHAAR_MAX_ATTEMPTS}. "
            f"{attempts_remaining} attempt(s) remaining before 24hr block."
        )

        if VERIFICATION_MODE == "api":
            auth_url = provider.get_auth_url(state=str(user.user_id))
            return {
                "message":          base_msg + " Redirect user to auth_url.",
                "auth_url":         auth_url,
                "initiate_token":   token,
                "token_expires_in": f"{AADHAAR_TOKEN_EXPIRY_MINUTES} minutes",
                "attempt":          f"{attempts_used}/{AADHAAR_MAX_ATTEMPTS}",
                "mode":             "api",
            }
        else:
            return {
                "message":          base_msg,
                "auth_url":         None,
                "initiate_token":   token,
                "token_expires_in": f"{AADHAAR_TOKEN_EXPIRY_MINUTES} minutes",
                "attempt":          f"{attempts_used}/{AADHAAR_MAX_ATTEMPTS}",
                "mode":             "dummy",
            }

    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def verify_aadhaar(db: Session, user_id: int, initiate_token: str,
                       auth_code: str = None) -> dict:
        """
        Verify using the token from current initiate session.
        Token valid 10 minutes only.
        Wrong DOB/Aadhaar → failure logged, must re-initiate for next try.
        3rd failure → 24hr block.
        """
        # ── 1. Load user ──────────────────────────────────────────────────────
        user = UserRepository.get_by_user_id(db, user_id)
        if not user:
            raise HTTPException(404, "User not found")

        if user.pan_status != "VERIFIED":
            raise HTTPException(400, "Please complete PAN verification first")

        if user.aadhaar_status == "VERIFIED":
            return {
                "message":         "Aadhaar already verified",
                "aadhaar_status":  "VERIFIED",
                "identity_status": user.identity_status,
                "next_step":       "Proceed to bank account verification",
            }

        if user.aadhaar_locked:
            raise HTTPException(403, "Aadhaar is locked")

        # ── 2. Check global cooldown ──────────────────────────────────────────
        now     = datetime.now(timezone.utc)
        tracker = AttemptTrackerRepository.get_or_create(db, user.email, VerificationType.AADHAAR)

        if tracker.locked_until:
            locked_until = tracker.locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if locked_until > now:
                remaining_hrs = round((locked_until - now).total_seconds() / 3600, 1)
                raise HTTPException(
                    423,
                    f"Aadhaar verification is blocked for {remaining_hrs} more hour(s)."
                )

        # ── 3. Check token exists ─────────────────────────────────────────────
        if not user.aadhaar_initiate_token:
            raise HTTPException(
                400,
                "No active Aadhaar session. "
                "Please call POST /api/v1/kyc/aadhaar-initiate first."
            )

        # ── 4. Check token expiry ─────────────────────────────────────────────
        if user.aadhaar_token_created_at:
            created_at = user.aadhaar_token_created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)

            age_minutes = (now - created_at).total_seconds() / 60
            if age_minutes > AADHAAR_TOKEN_EXPIRY_MINUTES:
                _clear_aadhaar_session(user)
                UserRepository.save(db)
                raise HTTPException(
                    400,
                    f"Session token expired (valid {AADHAAR_TOKEN_EXPIRY_MINUTES} minutes). "
                    "Please call POST /api/v1/kyc/aadhaar-initiate to get a new token."
                )

        # ── 5. Validate token matches ─────────────────────────────────────────
        if user.aadhaar_initiate_token != initiate_token:
            raise HTTPException(
                400,
                "Invalid or expired token. "
                "Please call POST /api/v1/kyc/aadhaar-initiate to get a fresh token."
            )

        # ── 6. Validate Aadhaar number ────────────────────────────────────────
        aadhaar_number = user.aadhaar_number
        if not aadhaar_number or len(aadhaar_number) != 12:
            raise HTTPException(400, "Invalid Aadhaar number in profile")

        # ── 7. Uniqueness check ───────────────────────────────────────────────
        existing = KYCAadhaarVerificationRepository.get_verified_by_aadhaar(db, aadhaar_number)
        if existing and existing.user_id != user.user_id:
            raise HTTPException(409, "This Aadhaar number is already linked to another account")

        # ── 8. Get current attempt count from tracker ─────────────────────────
        current_attempt = tracker.attempts_count  # already incremented during initiate

        # ── 9. Call provider ──────────────────────────────────────────────────
        provider = get_aadhaar_provider()
        try:
            result = provider.verify(
                db=db,
                aadhaar_number=aadhaar_number,
                dob_submitted=user.dob,
                auth_code=auth_code,
            )
        except RuntimeError as e:
            raise HTTPException(503, str(e))

        verified_dob = result.get("verified_dob") or ""

        # ── 10. FAILURE ───────────────────────────────────────────────────────
        if not result["success"]:

            # Clear this session token — must re-initiate for next attempt
            _clear_aadhaar_session(user)

            if current_attempt >= AADHAAR_MAX_ATTEMPTS:
                # 3rd failure → BLOCK 24hrs
                status = "BLOCKED"
                user.aadhaar_status = "BLOCKED"
                AttemptTrackerRepository.lock_tracker(
                    db, tracker, now + timedelta(hours=AADHAAR_COOLDOWN_HOURS)
                )
                KYCAadhaarVerificationRepository.create_verification_log(
                    db=db, user_id=user.user_id,
                    aadhaar_number=aadhaar_number,
                    dob_submitted=str(user.dob), verified_dob=verified_dob,
                    dob_match=False, status=status,
                    failure_reason=result["failure_reason"],
                    attempt_number=current_attempt,
                )
                UserRepository.save(db)
                raise HTTPException(
                    423,
                    f"{result['failure_reason']}. "
                    f"Maximum attempts ({AADHAAR_MAX_ATTEMPTS}) reached. "
                    f"Aadhaar verification blocked for {AADHAAR_COOLDOWN_HOURS} hours."
                )
            else:
                # 1st or 2nd failure → allow re-initiate
                status = "FAILED"
                user.aadhaar_status = "FAILED"
                remaining = AADHAAR_MAX_ATTEMPTS - current_attempt
                KYCAadhaarVerificationRepository.create_verification_log(
                    db=db, user_id=user.user_id,
                    aadhaar_number=aadhaar_number,
                    dob_submitted=str(user.dob), verified_dob=verified_dob,
                    dob_match=False, status=status,
                    failure_reason=result["failure_reason"],
                    attempt_number=current_attempt,
                )
                UserRepository.save(db)
                raise HTTPException(
                    400,
                    f"{result['failure_reason']}. "
                    f"Attempt {current_attempt}/{AADHAAR_MAX_ATTEMPTS}. "
                    f"{remaining} attempt(s) remaining. "
                    "Please fix your details and call /aadhaar-initiate again for a new token."
                )

        # ── 11. SUCCESS ───────────────────────────────────────────────────────
        user.aadhaar_status      = "VERIFIED"
        user.aadhaar_locked      = True
        user.dob_locked          = True
        user.aadhaar_verified_at = now

        if user.pan_status == "VERIFIED":
            user.identity_status = "VERIFIED"

        _clear_aadhaar_session(user)

        KYCAadhaarVerificationRepository.create_verification_log(
            db=db, user_id=user.user_id,
            aadhaar_number=aadhaar_number,
            dob_submitted=str(user.dob), verified_dob=verified_dob,
            dob_match=True, status="VERIFIED",
            failure_reason=None, attempt_number=current_attempt,
        )
        AttemptTrackerRepository.reset_attempts(db, tracker)
        UserRepository.update_user(db, user)

        logger.info(f"Aadhaar VERIFIED for user {user.user_id} (mode={VERIFICATION_MODE})")

        return {
            "message":         "Aadhaar verified successfully",
            "aadhaar_status":  user.aadhaar_status,
            "identity_status": user.identity_status,
            "next_step":       "Proceed to bank account verification",
        }