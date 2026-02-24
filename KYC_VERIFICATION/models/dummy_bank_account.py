from sqlalchemy import Column, String, Boolean
from core.database import Base

class DummyBankAccount(Base):
    __tablename__ = "dummy_bank_accounts"

    account_number = Column(String(20), primary_key=True)
    ifsc = Column(String(11), nullable=False)
    bank_name = Column(String(100), nullable=False)
    account_holder_name = Column(String(150), nullable=False)
    is_active = Column(Boolean, default=True)

