import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from sqlalchemy import and_
from core.database import SessionLocal
from models.attempt_tracker import AttemptTracker
from models.document_upload import DocumentStatus
from repositories.document_upload_repository import DocumentUploadRepository
from repositories.kyc_pan_verification_repository import KYCPANVerificationRepository
from repositories.kyc_aadhaar_verification_repository import KYCAadhaarVerificationRepository
from repositories.kyc_bank_verification_repository import KYCBankVerificationRepository
from core.config import RETENTION_DAYS, TRACKER_CLEANUP_HOURS, REJECTED_DOCS_RETENTION_DAYS
import os

logger = logging.getLogger(__name__)

class AutoCleanup:
    
    def __init__(self, interval_hours: int = 24):
        self.interval_hours = interval_hours
        self._running = False
        self._thread = None
        logger.info(f"AutoCleanup initialized with interval: {interval_hours}h")
    
    def start(self):
        if self._running:
            logger.warning("Auto cleanup already running")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"Auto cleanup started (runs every {self.interval_hours}h)")
    
    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Auto cleanup stopped")
    
    def is_running(self):
        return self._running
    
    def _run(self):
        while self._running:
            try:
                self._cleanup()
            except Exception as e:
                logger.error(f"Cleanup error: {str(e)}", exc_info=True)
            
            time.sleep(self.interval_hours * 3600)
    
    def _cleanup(self):
        db = SessionLocal()
        try:
            logger.info("Starting cleanup...")
            
            expired_trackers = self._cleanup_expired_trackers(db)
            failed_verifications = self._cleanup_failed_verifications(db)
            rejected_docs = self._cleanup_rejected_documents(db)
            
            logger.info(
                f"Cleanup completed: "
                f"{expired_trackers} trackers, "
                f"{failed_verifications} verifications, "
                f"{rejected_docs} documents removed"
            )
        
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}", exc_info=True)
        
        finally:
            db.close()
    
    def _cleanup_expired_trackers(self, db):
        try:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(hours=TRACKER_CLEANUP_HOURS)
            
            old_trackers = db.query(AttemptTracker).filter(and_(AttemptTracker.locked_until.isnot(None),AttemptTracker.locked_until < cutoff)).all()
            
            useless_trackers = db.query(AttemptTracker).filter(and_(AttemptTracker.locked_until.is_(None),AttemptTracker.attempts_count == 0)).all()
            
            total_count = len(old_trackers) + len(useless_trackers)
            
            for tracker in old_trackers:
                logger.debug(
                    f"Deleting old tracker: {tracker.email}, "
                    f"type: {tracker.verification_type}, "
                    f"was locked until: {tracker.locked_until}"
                )
                db.delete(tracker)
            
            for tracker in useless_trackers:
                logger.debug(
                    f"Deleting useless tracker: {tracker.email},"
                    f"type: {tracker.verification_type},"
                    f"attempts_count=0, locked_until=null"
                )
                db.delete(tracker)
            
            if total_count > 0:
                db.commit()
                logger.info(
                    f"Deleted {total_count} trackers "
                    f"(old: {len(old_trackers)}, useless: {len(useless_trackers)})"
                )
            
            return total_count
        except Exception as e:
            db.rollback()
            logger.error(f"Tracker cleanup error: {str(e)}")
            return 0
    
    def _cleanup_failed_verifications(self, db):
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
            
            pan_deleted = KYCPANVerificationRepository.delete_failed_verifications(db, cutoff)
            aadhaar_deleted = KYCAadhaarVerificationRepository.delete_failed_verifications(db, cutoff)
            bank_deleted = KYCBankVerificationRepository.delete_failed_verifications(db, cutoff)
            
            total_deleted = pan_deleted + aadhaar_deleted + bank_deleted
            
            if total_deleted > 0:
                db.commit()
                logger.info(
                    f"Deleted {total_deleted} failed verifications "
                    f"(PAN: {pan_deleted}, Aadhaar: {aadhaar_deleted}, Bank: {bank_deleted}) "
                    f"older than {RETENTION_DAYS} days"
                )
            
            return total_deleted
            
        except Exception as e:
            db.rollback()
            logger.error(f"Verification cleanup error: {str(e)}")
            return 0
    
    def _cleanup_rejected_documents(self, db):
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=REJECTED_DOCS_RETENTION_DAYS)
            
            rejected_docs = DocumentUploadRepository.get_rejected_documents_before_date(db, cutoff)
            
            count = len(rejected_docs)
            
            for doc in rejected_docs:
                if os.path.exists(doc.file_path):
                    try:
                        os.remove(doc.file_path)
                        logger.debug(f"Deleted file: {doc.file_path}")
                    except Exception as e:
                        logger.error(f"Failed to delete file {doc.file_path}: {str(e)}")
                
                db.delete(doc)
            
            if count > 0:
                db.commit()
                logger.info(
                    f"Deleted {count} rejected documents "
                    f"older than {REJECTED_DOCS_RETENTION_DAYS} days"
                )
            return count 
        except Exception as e:
            db.rollback()
            logger.error(f"Document cleanup error: {str(e)}")
            return 0