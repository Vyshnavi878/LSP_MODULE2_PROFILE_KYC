from sqlalchemy import Column, BigInteger, String, Text
from core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    username = Column(String(50),  unique=True)
    mobile_number = Column(String(25),  unique=True)
    password_hash = Column(String)
    device_id = Column(Text, nullable=True)
    role = Column(String, default="USER")
