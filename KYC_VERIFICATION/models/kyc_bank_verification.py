from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Float, Integer, Index, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from core.database import Base

class KYCBankVerification(Base):
    __tablename__ = "kyc_bank_verifications"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("user_profiles.user_id"), nullable=False, index=True)
    account_number = Column(String(20),  nullable=False)
    account_holder_name = Column(String(150), nullable=False)
    bank_name = Column(String(100), nullable=False)
    ifsc = Column(String(11),  nullable=False)
    name_match_percentage = Column(Float, nullable=True)
    status = Column(String(20),  nullable=False)
    failure_reason = Column(String(200), nullable=True)
    attempt_number = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    verified_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # FIX: relationship INSIDE the class (was outside, caused crash)
    user = relationship("UserProfile", back_populates="bank_verifications")

    __table_args__ = (
        Index("idx_bank_status",    "status"),
        Index("idx_user_bank",      "user_id", "account_number"),
        Index("idx_account_lookup", "account_number"),
    )
