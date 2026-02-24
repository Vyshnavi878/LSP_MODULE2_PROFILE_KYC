import os
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, UploadFile
from core.database import SessionLocal
from core.config import ALLOWED_IMAGE_EXTENSIONS, ALLOWED_DOCUMENT_EXTENSIONS, UPLOAD_BASE_PATH, VERIFICATION_MODE
from models.document_upload import DocumentUpload, DocumentType, DocumentStatus
from repositories.user_repository import UserRepository
from repositories.document_upload_repository import DocumentUploadRepository
from providers.document_provider import get_document_provider

logger = logging.getLogger(__name__)

REQUIRED_IDENTITY_DOCS = [
    DocumentType.AADHAAR_FRONT,
    DocumentType.AADHAAR_BACK,
    DocumentType.PAN_CARD,
]
INCOME_PROOF_DOCS = [
    DocumentType.SALARY_SLIP,
    DocumentType.BANK_STATEMENT,
]
MIN_REQUIRED_DOCS = len(REQUIRED_IDENTITY_DOCS) + 1

class DocumentUploadService:

    @staticmethod
    def upload_document(db: Session, user_id: int, document_type: str, file: UploadFile) -> dict:
        user = UserRepository.get_by_user_id(db, user_id)
        if not user:
            raise HTTPException(404, "User not found")

        if user.identity_status != "VERIFIED":
            raise HTTPException(400, "Please complete identity verification (PAN + Aadhaar) first")

        if user.bank_status != "VERIFIED":
            raise HTTPException(400, "Please complete bank verification first")

        try:
            doc_type_enum = DocumentType(document_type)
        except ValueError:
            valid = [t.value for t in DocumentType]
            raise HTTPException(400, {"error": "Invalid document type", "valid_types": valid})

        existing_doc = DocumentUploadRepository.get_by_user_and_type(db, user.user_id, doc_type_enum)
        if existing_doc and existing_doc.status in [DocumentStatus.VERIFIED, DocumentStatus.APPROVED]:
            raise HTTPException(400, f"{document_type} already {existing_doc.status.value.lower()}")

        DocumentUploadService._validate_file(file, doc_type_enum)
        file_path = DocumentUploadService._save_file(user.user_id, doc_type_enum, file)

        if existing_doc and existing_doc.status == DocumentStatus.REJECTED:
            doc = existing_doc
            doc.file_name              = file.filename
            doc.file_path              = file_path
            doc.file_size              = os.path.getsize(file_path)
            doc.mime_type              = file.content_type or "application/octet-stream"
            doc.status                 = DocumentStatus.UPLOADED
            doc.uploaded_at            = datetime.now(timezone.utc)
            doc.admin_remarks          = None
            doc.verified_at            = None
            doc.extracted_name         = None
            doc.extracted_id_number    = None
            doc.name_match_percentage  = None
            doc.verification_remarks   = None
        else:
            doc = DocumentUpload(
                user_id       = user.user_id,
                email         = user.email,
                document_type = doc_type_enum,
                file_name     = file.filename,
                file_path     = file_path,
                file_size     = os.path.getsize(file_path),
                mime_type     = file.content_type or "application/octet-stream",
                status        = DocumentStatus.UPLOADED,
                uploaded_at   = datetime.now(timezone.utc),
            )
            db.add(doc)

        db.commit()
        db.refresh(doc)
        logger.info(f"Document uploaded: {doc.document_type.value} for user_id={user_id}")

        return {
            "id":            doc.id,
            "document_type": doc.document_type.value,
            "file_name":     doc.file_name,
            "file_size":     doc.file_size,
            "status":        doc.status.value,
            "uploaded_at":   doc.uploaded_at.isoformat(),
            "message":       "Document uploaded successfully. Pending admin review.",
        }

    @staticmethod
    def verify_document_background(document_id: int):
        db = SessionLocal()
        try:
            doc = DocumentUploadRepository.get_by_id(db, document_id)
            if not doc:
                return

            if doc.status not in [DocumentStatus.UPLOADED, DocumentStatus.REJECTED]:
                return

            user = UserRepository.get_by_user_id(db, doc.user_id)
            if not user:
                return

            provider = get_document_provider()
            result = provider.verify(
                document_type   = doc.document_type,
                file_path       = doc.file_path,
                registered_name = user.full_name,
            )

            now = datetime.now(timezone.utc)

            if result["success"]:
                doc.status                = DocumentStatus.VERIFIED
                doc.verified_at           = now
                doc.extracted_name        = result.get("extracted_name")
                doc.extracted_id_number   = result.get("extracted_id_number")
                doc.name_match_percentage = result.get("name_match_percentage")
                doc.verification_remarks  = None
                logger.info(f"[BG VERIFY] Document {doc.id} VERIFIED (mode={VERIFICATION_MODE})")
            else:
                doc.status               = DocumentStatus.REJECTED
                doc.verification_remarks = result.get("verification_remarks", "Verification failed")
                doc.name_match_percentage = result.get("name_match_percentage")
                logger.warning(f"[BG VERIFY] Document {doc.id} REJECTED: {doc.verification_remarks}")

            db.commit()
            DocumentUploadService._update_user_document_status(db, doc.user_id)

        except Exception as e:
            db.rollback()
            logger.error(f"Background verification error for doc {document_id}: {e}", exc_info=True)
        finally:
            db.close()

    @staticmethod
    def list_documents(db: Session, user_id: int) -> dict:
        user = UserRepository.get_by_user_id(db, user_id)
        if not user:
            raise HTTPException(404, "User not found")

        documents      = DocumentUploadRepository.get_by_user_id(db, user.user_id)
        uploaded_types = {doc.document_type for doc in documents}

        required   = [d.value for d in REQUIRED_IDENTITY_DOCS]
        has_income = any(d.document_type in INCOME_PROOF_DOCS for d in documents)
        if not has_income:
            required += ["SALARY_SLIP or BANK_STATEMENT"]

        missing = [d.value for d in REQUIRED_IDENTITY_DOCS if d not in uploaded_types]
        if not has_income:
            missing.append("SALARY_SLIP or BANK_STATEMENT")

        verified_or_approved = {DocumentStatus.VERIFIED, DocumentStatus.APPROVED}
        all_approved = (
            len(documents) >= MIN_REQUIRED_DOCS and
            all(doc.status in verified_or_approved for doc in documents) and
            any(doc.document_type in INCOME_PROOF_DOCS for doc in documents) and
            all(
                any(doc.document_type == req and doc.status in verified_or_approved for doc in documents)
                for req in REQUIRED_IDENTITY_DOCS
            )
        )

        return {
            "user_id": user.user_id,
            "email":   user.email,
            "documents": [
                {
                    "id":                    doc.id,
                    "document_type":         doc.document_type.value,
                    "file_name":             doc.file_name,
                    "file_size":             doc.file_size,
                    "status":                doc.status.value,
                    "uploaded_at":           doc.uploaded_at.isoformat(),
                    "extracted_name":        doc.extracted_name,
                    "extracted_id_number":   doc.extracted_id_number,
                    "name_match_percentage": doc.name_match_percentage,
                    "verified_at":           doc.verified_at.isoformat() if doc.verified_at else None,
                    "reviewed_at":           doc.reviewed_at.isoformat() if doc.reviewed_at else None,
                    "admin_remarks":         doc.admin_remarks,
                }
                for doc in documents
            ],
            "total_documents":    len(documents),
            "required_documents": required,
            "missing_documents":  missing,
            "all_approved":       all_approved,
        }

    @staticmethod
    def delete_document(db: Session, document_id: int, user_id: int) -> dict:
        doc = DocumentUploadRepository.get_by_id(db, document_id)
        if not doc:
            raise HTTPException(404, "Document not found")

        if doc.user_id != user_id:
            raise HTTPException(403, "Unauthorized")

        if doc.status in [DocumentStatus.VERIFIED, DocumentStatus.APPROVED]:
            raise HTTPException(400, f"Cannot delete {doc.status.value.lower()} document")

        if os.path.exists(doc.file_path):
            try:
                os.remove(doc.file_path)
                logger.info(f"Deleted file from disk: {doc.file_path}")
            except Exception as e:
                logger.warning(f"Failed to delete file: {e}")

        DocumentUploadRepository.delete_document(db, doc)
        logger.info(f"Document {document_id} deleted for user_id={user_id}")

        return {
            "message":     "Document deleted successfully",
            "document_id": document_id,
        }

    @staticmethod
    def _update_user_document_status(db: Session, user_id: int):
        user = UserRepository.get_by_user_id(db, user_id)
        if not user:
            return

        docs = DocumentUploadRepository.get_by_user_id(db, user_id)
        verified_or_approved = {DocumentStatus.VERIFIED, DocumentStatus.APPROVED}

        identity_done = all(
            any(d.document_type == req and d.status in verified_or_approved for d in docs)
            for req in REQUIRED_IDENTITY_DOCS
        )
        income_done = any(
            d.document_type in INCOME_PROOF_DOCS and d.status in verified_or_approved
            for d in docs
        )

        if identity_done and income_done:
            user.document_status = "APPROVED"
            if (user.pan_status     == "VERIFIED" and
                    user.aadhaar_status == "VERIFIED" and
                    user.bank_status    == "VERIFIED"):
                user.kyc_status = "COMPLETED"
                logger.info(f"KYC COMPLETED for user_id={user_id}")
        elif docs:
            user.document_status = "UPLOADED"

        db.commit()

    @staticmethod
    def _validate_file(file: UploadFile, doc_type: DocumentType):
        if not file or not file.filename:
            raise HTTPException(400, "No file selected")

        file_ext = os.path.splitext(file.filename)[1].lower()

        if doc_type in [DocumentType.AADHAAR_FRONT, DocumentType.AADHAAR_BACK, DocumentType.PAN_CARD]:
            if file_ext not in ALLOWED_IMAGE_EXTENSIONS:
                raise HTTPException(400, f"Invalid image format. Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}")
        elif doc_type in [DocumentType.SALARY_SLIP, DocumentType.BANK_STATEMENT]:
            if file_ext not in ALLOWED_DOCUMENT_EXTENSIONS:
                raise HTTPException(400, f"Invalid document format. Allowed: {', '.join(ALLOWED_DOCUMENT_EXTENSIONS)}")

    @staticmethod
    def _save_file(user_id: int, doc_type: DocumentType, file: UploadFile) -> str:
        folder_map = {
            DocumentType.AADHAAR_FRONT:  "aadhaar",
            DocumentType.AADHAAR_BACK:   "aadhaar",
            DocumentType.PAN_CARD:       "pan",
            DocumentType.SALARY_SLIP:    "salary_slips",   
            DocumentType.BANK_STATEMENT: "bank_statements"
        }
        upload_dir = os.path.join(UPLOAD_BASE_PATH, folder_map[doc_type])
        os.makedirs(upload_dir, exist_ok=True)

        file_ext  = os.path.splitext(file.filename)[1]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        filename  = f"{user_id}_{doc_type.value}_{timestamp}{file_ext}"
        file_path = os.path.join(upload_dir, filename)

        with open(file_path, "wb") as f:
            f.write(file.file.read())

        return file_path
