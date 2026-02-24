from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from models.kyc_aadhaar_verification import KYCAadhaarVerification

class KYCAadhaarVerificationRepository:

    @staticmethod
    def create_verification_log(db, user_id, aadhaar_number, dob_submitted,
                                verified_dob, dob_match, status, failure_reason, attempt_number):
        log = KYCAadhaarVerification(
            user_id=user_id,
            aadhaar_number=aadhaar_number,
            dob_submitted=dob_submitted,
            verified_dob=verified_dob,
            dob_match=dob_match,
            status=status,
            failure_reason=failure_reason,
            attempt_number=attempt_number,
            created_at=datetime.now(timezone.utc),
        )
        db.add(log)
        db.commit()
        return log

    @staticmethod
    def get_by_user_id(db: Session, user_id: int) -> List[KYCAadhaarVerification]:
        return (
            db.query(KYCAadhaarVerification)
            .filter(KYCAadhaarVerification.user_id == user_id)
            .order_by(KYCAadhaarVerification.created_at.desc())
            .all()
        )

    @staticmethod
    def get_latest_by_user_id(db: Session, user_id: int) -> Optional[KYCAadhaarVerification]:
        return (
            db.query(KYCAadhaarVerification)
            .filter(KYCAadhaarVerification.user_id == user_id)
            .order_by(KYCAadhaarVerification.created_at.desc())
            .first()
        )

    @staticmethod
    def get_verified_by_aadhaar(db: Session, aadhaar_number: str) -> Optional[KYCAadhaarVerification]:
        return (
            db.query(KYCAadhaarVerification)
            .filter(
                KYCAadhaarVerification.aadhaar_number == aadhaar_number,
                KYCAadhaarVerification.status == "VERIFIED",
            )
            .first()
        )

    @staticmethod
    def delete_failed_verifications(db: Session, cutoff_date: datetime) -> int:
        return (
            db.query(KYCAadhaarVerification)
            .filter(
                KYCAadhaarVerification.status.in_(["FAILED", "BLOCKED"]),
                KYCAadhaarVerification.created_at < cutoff_date,
            )
            .delete(synchronize_session=False)
        )
