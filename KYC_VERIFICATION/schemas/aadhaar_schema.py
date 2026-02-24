from pydantic import BaseModel
from typing import Optional

class AadhaarInitiateRequest(BaseModel):
    user_id: int

class AadhaarInitiateResponse(BaseModel):
    message: str
    auth_url: Optional[str] = None
    initiate_token: str
    token_expires_in: str
    attempt: str
    mode: str

class AadhaarVerificationRequest(BaseModel):
    user_id: int
    initiate_token: str
    auth_code: Optional[str] = None

class AadhaarVerificationResponse(BaseModel):
    message: str
    aadhaar_status: str
    identity_status: str
    next_step: str
