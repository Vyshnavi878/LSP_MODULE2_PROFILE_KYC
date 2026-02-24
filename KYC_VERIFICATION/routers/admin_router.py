from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timezone
from core.database import get_db
from core.config import ADMIN_API_KEY
from models.document_upload import DocumentStatus
from repositories.user_repository import UserRepository
from repositories.document_upload_repository import DocumentUploadRepository
import logging
from schemas.document_schema import DocumentReviewRequest, DocumentReviewResponse, UserKYCDetails

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin Panel"])

def verify_admin_key(x_admin_key: str = Header(..., description="Admin API key")):
    if x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin API key")
    return x_admin_key

@router.post("/documents/review", response_model=DocumentReviewResponse)
def review_document(
    request: DocumentReviewRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    try:
        document = DocumentUploadRepository.get_by_id(db, request.document_id)
        if not document:
            raise HTTPException(404, f"Document {request.document_id} not found")

        if document.status == DocumentStatus.APPROVED:
            raise HTTPException(400, "Document is already approved")
        if document.status == DocumentStatus.REJECTED:
            raise HTTPException(400, "Document is already rejected. User must re-upload first.")

        if request.action not in ["APPROVE", "REJECT"]:
            raise HTTPException(400, "Invalid action. Must be 'APPROVE' or 'REJECT'")

        if request.action == "REJECT":
            if not request.admin_remarks or not request.admin_remarks.strip():
                raise HTTPException(400, "Admin remarks are required when rejecting a document")
            document.status = DocumentStatus.REJECTED
            message = f"Document rejected: {request.admin_remarks}"
        else:
            document.status = DocumentStatus.APPROVED
            message = "Document approved successfully"

        document.admin_remarks = request.admin_remarks
        document.reviewed_at   = datetime.now(timezone.utc)
        document.reviewed_by   = request.reviewed_by

        user = UserRepository.get_by_user_id(db, document.user_id)
        kyc_completed = False

        if user:
            all_docs = DocumentUploadRepository.get_by_user_id(db, user.user_id)
            verified_or_approved = {DocumentStatus.VERIFIED, DocumentStatus.APPROVED}
            required_identity = ["AADHAAR_FRONT", "AADHAAR_BACK", "PAN_CARD"]
            income_docs       = ["SALARY_SLIP", "BANK_STATEMENT"]

            identity_done = all(
                any(d.document_type.value == req and d.status in verified_or_approved for d in all_docs)
                for req in required_identity
            )
            income_done = any(
                d.document_type.value in income_docs and d.status in verified_or_approved
                for d in all_docs
            )

            if identity_done and income_done:
                user.document_status = "APPROVED"
                if (user.pan_status     == "VERIFIED" and
                        user.aadhaar_status == "VERIFIED" and
                        user.bank_status    == "VERIFIED"):
                    user.kyc_status = "COMPLETED"
                    kyc_completed   = True
                    logger.info(f"KYC COMPLETED for user {user.user_id} ({user.email})")
            else:
                user.document_status = "UPLOADED"

        DocumentUploadRepository.update_document(db, document)
        if user:
            UserRepository.save(db)

        logger.info(f"Document {document.id} {request.action.lower()}ed by {request.reviewed_by}")

        return DocumentReviewResponse(
            document_id   = document.id,
            document_type = document.document_type.value,
            user_email    = document.email,
            status        = document.status.value,
            message       = message,
            kyc_completed = kyc_completed,
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error reviewing document: {str(e)}", exc_info=True)
        raise HTTPException(500, "Failed to review document")

@router.get("/stats/documents")
def get_document_stats(db: Session = Depends(get_db), _: str = Depends(verify_admin_key)):
    try:
        total_docs = DocumentUploadRepository.count_all(db)
        uploaded   = DocumentUploadRepository.count_by_status(db, DocumentStatus.UPLOADED)
        verified   = DocumentUploadRepository.count_by_status(db, DocumentStatus.VERIFIED)
        approved   = DocumentUploadRepository.count_by_status(db, DocumentStatus.APPROVED)
        rejected   = DocumentUploadRepository.count_by_status(db, DocumentStatus.REJECTED)
        return {
            "total_documents": total_docs,
            "uploaded":        uploaded,
            "verified":        verified,
            "approved":        approved,
            "rejected":        rejected,
            "pending_review":  uploaded + verified,
        }
    except Exception as e:
        logger.error(f"Error fetching stats: {str(e)}", exc_info=True)
        raise HTTPException(500, "Failed to fetch statistics")

@router.get("/stats/kyc")
def get_kyc_stats(db: Session = Depends(get_db), _: str = Depends(verify_admin_key)):
    try:
        total_users = UserRepository.count_all_users(db)
        completed   = UserRepository.count_by_kyc_status(db, "COMPLETED")
        incomplete  = UserRepository.count_by_kyc_status(db, "INCOMPLETE")
        blocked     = UserRepository.count_by_kyc_status(db, "BLOCKED")
        return {
            "total_users":     total_users,
            "kyc_completed":   completed,
            "kyc_incomplete":  incomplete,
            "kyc_blocked":     blocked,
            "completion_rate": f"{(completed / total_users * 100):.1f}%" if total_users > 0 else "0%",
        }
    except Exception as e:
        logger.error(f"Error fetching KYC stats: {str(e)}", exc_info=True)
        raise HTTPException(500, "Failed to fetch KYC statistics")

@router.get("/users", response_model=List[UserKYCDetails])
def get_all_users(
    kyc_status: Optional[str] = Query(None, description="COMPLETED, INCOMPLETE, BLOCKED"),
    limit: int  = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    try:
        if kyc_status:
            if kyc_status not in ["COMPLETED", "INCOMPLETE", "BLOCKED"]:
                raise HTTPException(400, "Invalid kyc_status filter")
            users = UserRepository.get_users_by_kyc_status(db, kyc_status, limit, offset)
        else:
            users = UserRepository.get_all_users(db, limit, offset)

        return [
            UserKYCDetails(
                user_id             = user.user_id,
                email               = user.email,
                full_name           = user.full_name,
                pan_number          = user.pan_number,
                aadhaar_number      = user.aadhaar_number,
                pan_status          = user.pan_status,
                aadhaar_status      = user.aadhaar_status,
                bank_status         = user.bank_status,
                identity_status     = user.identity_status,
                document_status     = user.document_status,
                kyc_status          = user.kyc_status,
                created_at          = user.created_at.isoformat(),
                pan_verified_at     = user.pan_verified_at.isoformat()     if user.pan_verified_at     else None,
                aadhaar_verified_at = user.aadhaar_verified_at.isoformat() if user.aadhaar_verified_at else None,
                bank_verified_at    = user.bank_verified_at.isoformat()    if user.bank_verified_at    else None,
            )
            for user in users
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching users: {str(e)}", exc_info=True)
        raise HTTPException(500, "Failed to fetch users")

@router.get("/users/{user_id}")
def get_user_details(
    user_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    try:
        user = UserRepository.get_by_user_id(db, user_id)
        if not user:
            raise HTTPException(404, f"User {user_id} not found")

        documents = DocumentUploadRepository.get_by_user_id(db, user_id)

        return {
            "user": {
                "user_id":         user.user_id,
                "email":           user.email,
                "full_name":       user.full_name,
                "pan_number":      user.pan_number,
                "aadhaar_number":  user.aadhaar_number,
                "pan_status":      user.pan_status,
                "aadhaar_status":  user.aadhaar_status,
                "bank_status":     user.bank_status,
                "identity_status": user.identity_status,
                "document_status": user.document_status,
                "kyc_status":      user.kyc_status,
                "created_at":      user.created_at.isoformat(),
            },
            "documents": [
                {
                    "id":            doc.id,
                    "document_type": doc.document_type.value,
                    "file_name":     doc.file_name,
                    "file_path":     doc.file_path,
                    "file_size":     doc.file_size,
                    "status":        doc.status.value,
                    "uploaded_at":   doc.uploaded_at.isoformat(),
                    "verified_at":   doc.verified_at.isoformat() if doc.verified_at else None,
                    "reviewed_at":   doc.reviewed_at.isoformat() if doc.reviewed_at else None,
                    "reviewed_by":   doc.reviewed_by,
                    "admin_remarks": doc.admin_remarks,
                }
                for doc in documents
            ],
            "total_documents": len(documents),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user details: {str(e)}", exc_info=True)
        raise HTTPException(500, "Failed to fetch user details")
