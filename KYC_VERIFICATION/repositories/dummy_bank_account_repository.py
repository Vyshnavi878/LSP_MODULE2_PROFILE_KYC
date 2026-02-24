from sqlalchemy.orm import Session
from models.dummy_bank_account import DummyBankAccount
from typing import Optional

class DummyBankAccountRepository:
    
    @staticmethod
    def get_by_account_number(db: Session, account_number: str) -> Optional[DummyBankAccount]:
        return db.query(DummyBankAccount).filter(DummyBankAccount.account_number == account_number).first()
    
    @staticmethod
    def create_dummy_account(db: Session, account: DummyBankAccount) -> DummyBankAccount:
        db.add(account)
        db.commit()
        db.refresh(account)
        return account