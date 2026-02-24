import logging
import requests
from sqlalchemy.orm import Session
from core.config import VERIFICATION_MODE,NAME_MATCH_THRESHOLD, KARZA_API_KEY, KARZA_PAN_URL, PAN_MAX_ATTEMPTS, PAN_COOLDOWN_HOURS
from repositories.dummy_pan_repository import DummyPANRepository
from utils.name_matcher import name_match_percentage


logger = logging.getLogger(__name__)

class DummyPANProvider:
    @staticmethod
    def verify(db: Session, pan_number: str, full_name: str) -> dict:
        record = DummyPANRepository.get_by_pan_number(db, pan_number)

        if not record:
            return {
                "success": False,
                "verified_name": None,
                "failure_reason": "PAN not found in records",
            }

        match_pct = name_match_percentage(full_name, record.full_name)
        if match_pct < NAME_MATCH_THRESHOLD:
            return {
                "success": False,
                "verified_name": record.full_name,
                "match_percentage": match_pct,
                "failure_reason": "Name mismatch"
            }

        return {
            "success": True,
            "verified_name": record.full_name,
            "match_percentage": match_pct,
            "failure_reason": None,
        }

class KarzaPANProvider:

    @staticmethod
    def verify(db: Session, pan_number: str, full_name: str) -> dict:
        if not KARZA_API_KEY:
            raise ValueError("KARZA_API_KEY is not set. "
                "Add it to .env or switch VERIFICATION_MODE=dummy."
            )

        try:
            response = requests.post(
                KARZA_PAN_URL,
                headers={
                    "x-karza-key": KARZA_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"pan": pan_number, "consent": "Y"},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("statusCode") != 101:
                return {
                    "success": False,
                    "verified_name": None,
                    "failure_reason": data.get("error", "PAN verification failed"),
                }

            api_name = data["result"].get("name", "")
            match_pct = name_match_percentage(full_name, api_name)

            if match_pct < NAME_MATCH_THRESHOLD:
                return {
                    "success": False,
                    "verified_name": api_name,
                    "match_percentage": match_pct,
                    "failure_reason": "Name mismatch"
                }

            return {
                "success": True,
                "verified_name": api_name,
                "match_percentage": match_pct,
                "failure_reason": None,
            }

        except requests.RequestException as e:
            logger.error(f"Karza PAN API error: {e}")
            raise RuntimeError("PAN verification service temporarily unavailable") from e

def get_pan_provider():
    if VERIFICATION_MODE == "api":
        logger.info("PAN provider: Karza (real API)")
        return KarzaPANProvider
    logger.info("PAN provider: Dummy (local DB)")
    return DummyPANProvider
