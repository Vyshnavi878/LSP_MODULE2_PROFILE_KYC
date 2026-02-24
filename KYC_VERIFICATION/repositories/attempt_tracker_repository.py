from sqlalchemy.orm import Session
from models.attempt_tracker import AttemptTracker, VerificationType
from datetime import datetime, timezone
from typing import Optional

class AttemptTrackerRepository:
    
    @staticmethod
    def get_by_email_and_type(db: Session, email: str, verification_type: VerificationType) -> Optional[AttemptTracker]:
        return db.query(AttemptTracker).filter(AttemptTracker.email == email, AttemptTracker.verification_type == verification_type).first()
    
    @staticmethod
    def create_tracker(db: Session, email: str, verification_type: VerificationType) -> AttemptTracker:
        tracker = AttemptTrackerRepository.get_by_email_and_type(db, email, verification_type)
        if not tracker:
            now = datetime.now(timezone.utc)
            tracker = AttemptTracker(
                email=email,
                verification_type=verification_type,
                attempts_count=0,
                first_attempt_at=now,
                last_attempt_at=now,
                created_at=now,
            )
            db.add(tracker)
            db.flush()
        return tracker

    
    @staticmethod
    def update_tracker(db: Session, tracker: AttemptTracker) -> None:
        db.commit()
        db.refresh(tracker)
    
    @staticmethod
    def reset_attempts(db: Session, tracker: AttemptTracker) -> None:
        tracker.attempts_count = 0
        tracker.locked_until = None
        db.commit()
    
    @staticmethod
    def increment_attempt(db: Session, tracker: AttemptTracker) -> int:
        tracker.attempts_count += 1
        tracker.last_attempt_at = datetime.now(timezone.utc)
        db.commit()
        return tracker.attempts_count
    
    @staticmethod
    def decrement_attempt(db: Session, tracker: AttemptTracker) -> int:
        if tracker.attempts_count > 0:
            tracker.attempts_count -= 1
        db.commit()
        return tracker.attempts_count
    
    @staticmethod
    def lock_tracker(db: Session, tracker: AttemptTracker, locked_until: datetime) -> None:
        tracker.locked_until = locked_until
        db.commit()
    
    @staticmethod
    def get_or_create(db: Session, email: str, verification_type: VerificationType) -> AttemptTracker:
        tracker = AttemptTrackerRepository.get_by_email_and_type(db, email, verification_type)

        if not tracker:
            tracker = AttemptTrackerRepository.create_tracker(db, email, verification_type)
            db.commit()
            db.refresh(tracker)

        return tracker