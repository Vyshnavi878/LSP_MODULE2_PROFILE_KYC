from pydantic import BaseModel

class PANVerificationRequest(BaseModel):
    user_id: int

class PANVerificationResponse(BaseModel):
    message: str
    pan_status: str
    verified_name: str | None = None
    identity_status: str
    next_step: str