import logging
import requests
from sqlalchemy.orm import Session
from core.config import VERIFICATION_MODE, NAME_MATCH_THRESHOLD, CASHFREE_APP_ID, CASHFREE_SECRET_KEY, CASHFREE_BANK_URL, BANK_MAX_ATTEMPTS, BANK_COOLDOWN_HOURS
from repositories.dummy_bank_account_repository import DummyBankAccountRepository
from utils.name_matcher import name_match_percentage

logger = logging.getLogger(__name__)

class DummyBankProvider:
    @staticmethod
    def verify(db: Session, account_number: str, account_holder_name: str,
               bank_name: str, ifsc: str) -> dict:
        record = DummyBankAccountRepository.get_by_account_number(db, account_number)

        if not record:
            return {
                "success": False,
                "verified_name": None,
                "name_match_percentage": 0.0,
                "is_active": False,
                "failure_reason": "Bank account number not found in records",
            }

        if record.ifsc.upper() != ifsc.upper():
            return {
                "success": False,
                "verified_name": record.account_holder_name,
                "name_match_percentage": 0.0,
                "is_active": record.is_active,
                "failure_reason": "IFSC code mismatch"
            }

        if record.bank_name.upper().strip() != bank_name.upper().strip():
            return {
                "success": False,
                "verified_name": record.account_holder_name,
                "name_match_percentage": 0.0,
                "is_active": record.is_active,
                "failure_reason": "Bank name mismatch"
            }

        match_pct = name_match_percentage(account_holder_name, record.account_holder_name)
        if match_pct < NAME_MATCH_THRESHOLD:
            return {
                "success": False,
                "verified_name": record.account_holder_name,
                "name_match_percentage": match_pct,
                "is_active": record.is_active,
                "failure_reason": "Account holder name mismatch"
            }

        if not record.is_active:
            return {
                "success": False,
                "verified_name": record.account_holder_name,
                "name_match_percentage": match_pct,
                "is_active": False,
                "failure_reason": "Bank account is inactive or closed — please use an active account",
            }

        return {
            "success": True,
            "verified_name": record.account_holder_name,
            "name_match_percentage": match_pct,
            "is_active": True,
            "failure_reason": None,
        }

class CashfreeBankProvider:

    @staticmethod
    def verify(db: Session, account_number: str, account_holder_name: str,
               bank_name: str, ifsc: str) -> dict:
        if not CASHFREE_APP_ID or not CASHFREE_SECRET_KEY:
            raise ValueError(
                "CASHFREE_APP_ID or CASHFREE_SECRET_KEY is not set. "
                "Add them to .env or switch VERIFICATION_MODE=dummy."
            )

        try:
            response = requests.post(
                CASHFREE_BANK_URL,
                headers={
                    "x-client-id":     CASHFREE_APP_ID,
                    "x-client-secret": CASHFREE_SECRET_KEY,
                    "Content-Type":    "application/json",
                },
                json={
                    "bank_account": account_number,
                    "ifsc":         ifsc,
                    "name":         account_holder_name,
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            api_status = data.get("account_status", "")
            if api_status not in ("VALID",):
                return {
                    "success": False,
                    "verified_name": data.get("name_at_bank"),
                    "name_match_percentage": 0.0,
                    "is_active": False,
                    "failure_reason": data.get("account_status_code", "Bank account verification failed"),
                }

            api_name   = data.get("name_at_bank", "")
            match_pct  = name_match_percentage(account_holder_name, api_name)

            if match_pct < NAME_MATCH_THRESHOLD:
                return {
                    "success": False,
                    "verified_name": api_name,
                    "name_match_percentage": match_pct,
                    "is_active": True,
                    "failure_reason": "Account holder name mismatch"
                }

            return {
                "success": True,
                "verified_name": api_name,
                "name_match_percentage": match_pct,
                "is_active": True,
                "failure_reason": None,
            }

        except requests.RequestException as e:
            logger.error(f"Cashfree bank API error: {e}")
            raise RuntimeError("Bank verification service temporarily unavailable") from e
def get_bank_provider():
    if VERIFICATION_MODE == "api":
        logger.info("Bank provider: Cashfree (real API)")
        return CashfreeBankProvider
    logger.info("Bank provider: Dummy (local DB)")
    return DummyBankProvider
