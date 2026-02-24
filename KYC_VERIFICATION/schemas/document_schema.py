from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

class DocumentTypeEnum(str, Enum):
    AADHAAR_FRONT  = "AADHAAR_FRONT"
    AADHAAR_BACK   = "AADHAAR_BACK"
    PAN_CARD       = "PAN_CARD"
    SALARY_SLIP    = "SALARY_SLIP"
    BANK_STATEMENT = "BANK_STATEMENT"

class DocumentStatusEnum(str, Enum):
    UPLOADED     = "UPLOADED"
    UNDER_REVIEW = "UNDER_REVIEW"
    VERIFIED     = "VERIFIED"
    APPROVED     = "APPROVED"
    REJECTED     = "REJECTED"

class DocumentUploadResponse(BaseModel):
    id: int
    document_type: str
    file_name: str
    file_size: int
    status: str
    uploaded_at: str
    message: str

class DocumentVerifyResponse(BaseModel):
    id: int
    document_type: str
    status: str                                    
    extracted_name: Optional[str] = None           
    extracted_id_number: Optional[str] = None      
    name_match_percentage: Optional[float] = None  
    verification_remarks: Optional[str] = None    
    verified_at: Optional[str] = None
    message: str

class DocumentListItem(BaseModel):
    id: int
    document_type: str
    file_name: str
    file_size: int
    status: str
    uploaded_at: str
    extracted_name: Optional[str] = None
    extracted_id_number: Optional[str] = None
    name_match_percentage: Optional[float] = None
    verified_at: Optional[str] = None
    reviewed_at: Optional[str] = None
    admin_remarks: Optional[str] = None

class AllDocumentsResponse(BaseModel):
    user_id: int
    email: str
    documents: List[DocumentListItem]
    total_documents: int
    required_documents: List[str]
    missing_documents: List[str]
    all_approved: bool

class DocumentReviewRequest(BaseModel):
    document_id: int
    action: str          # "APPROVE" or "REJECT"
    admin_remarks: Optional[str] = None
    reviewed_by: str

class DocumentReviewResponse(BaseModel):
    document_id: int
    document_type: str
    user_email: str
    status: str
    message: str
    kyc_completed: bool = False

class UserKYCDetails(BaseModel):
    user_id: int
    email: str
    full_name: str
    pan_number: str
    aadhaar_number: str
    pan_status: str
    aadhaar_status: str
    bank_status: str
    identity_status: str
    document_status: str
    kyc_status: str
    created_at: str
    pan_verified_at: Optional[str]
    aadhaar_verified_at: Optional[str]
    bank_verified_at: Optional[str]