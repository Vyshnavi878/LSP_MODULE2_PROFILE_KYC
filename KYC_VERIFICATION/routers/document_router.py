from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, BackgroundTasks
from sqlalchemy.orm import Session
from core.database import get_db
from core.config import VERIFICATION_MODE
from schemas.document_schema import DocumentUploadResponse, AllDocumentsResponse, DocumentListItem, DocumentVerifyResponse
from services.document_upload_service import DocumentUploadService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/documents", tags=["Document Upload & Verification"])

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    user_id: int = Form(..., description="User ID"),
    document_type: str = Form(
        ...,
        description="PAN_CARD, AADHAAR_FRONT, AADHAAR_BACK, SALARY_SLIP, or BANK_STATEMENT",
        example="PAN_CARD",
    ),
    file: UploadFile = File(..., description="JPG/PNG for ID docs, PDF for financial docs. Max 2MB"),
    db: Session = Depends(get_db),
):
    try:
        valid_types = ["PAN_CARD", "AADHAAR_FRONT", "AADHAAR_BACK", "SALARY_SLIP", "BANK_STATEMENT"]
        if document_type not in valid_types:
            raise HTTPException(
                400,
                {"error": "Invalid document type", "provided": document_type, "valid_types": valid_types},
            )

        if not file or not file.filename:
            raise HTTPException(400, "No file selected.")

        contents = await file.read()
        MAX_SIZE = 2 * 1024 * 1024
        if len(contents) > MAX_SIZE:
            raise HTTPException(400, f"File too large. Max 2MB. Got {round(len(contents)/1024/1024, 2)}MB")
        await file.seek(0)

        result = DocumentUploadService.upload_document(
            db=db,
            user_id=user_id,
            document_type=document_type,
            file=file,
        )
        if VERIFICATION_MODE == "api":
            background_tasks.add_task(
                DocumentUploadService.verify_document_background,
                result["id"],
            )

        return DocumentUploadResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        raise HTTPException(500, f"Upload failed: {str(e)}")


@router.get("/list", response_model=AllDocumentsResponse)
def list_documents(
    user_id: int = Query(..., description="User ID"),
    db: Session = Depends(get_db),
):
    try:
        result = DocumentUploadService.list_documents(db=db, user_id=user_id)
        documents = [DocumentListItem(**doc) for doc in result["documents"]]
        return AllDocumentsResponse(
            user_id=result["user_id"],
            email=result["email"],
            documents=documents,
            total_documents=result["total_documents"],
            required_documents=result["required_documents"],
            missing_documents=result["missing_documents"],
            all_approved=result["all_approved"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List error: {e}", exc_info=True)
        raise HTTPException(500, "Failed to retrieve documents")


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    user_id: int = Query(..., description="User ID for authorization"),
    db: Session = Depends(get_db),
):
    try:
        return DocumentUploadService.delete_document(db=db, document_id=document_id, user_id=user_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete error: {e}", exc_info=True)
        raise HTTPException(500, "Failed to delete document")