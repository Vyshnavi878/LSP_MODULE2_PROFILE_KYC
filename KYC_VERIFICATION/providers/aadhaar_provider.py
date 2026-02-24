import logging
import requests
from datetime import date
from sqlalchemy.orm import Session
from core.config import VERIFICATION_MODE, DIGILOCKER_CLIENT_ID, DIGILOCKER_CLIENT_SECRET, DIGILOCKER_REDIRECT_URI, DIGILOCKER_AUTH_URL, DIGILOCKER_TOKEN_URL, DIGILOCKER_AADHAAR_URL
from repositories.dummy_pan_repository import DummyPANRepository

logger = logging.getLogger(__name__)

class DummyAadhaarProvider:
    @staticmethod
    def get_auth_url(state: str = "") -> str:
        return "dummy://not-applicable"

    @staticmethod
    def verify(db: Session, aadhaar_number: str, dob_submitted: date,
               auth_code: str = None) -> dict:
        record = DummyPANRepository.get_by_aadhaar_number(db, aadhaar_number)

        if not record:
            return {
                "success": False,
                "verified_dob": None,
                "failure_reason": "Aadhaar number not found in records"
            }

        if record.dob != dob_submitted:
            return {
                "success": False,
                "verified_dob": str(record.dob),
                "failure_reason": "Date of birth does not match Aadhaar records"
            }

        return {
            "success": True,
            "verified_dob": str(record.dob),
            "failure_reason": None,
        }

    @staticmethod
    def check_uniqueness(db: Session, aadhaar_number: str) -> dict:
        return {"available": True}

class DigiLockerAadhaarProvider:
    @staticmethod
    def get_auth_url(state: str = "") -> str:
        if not DIGILOCKER_CLIENT_ID:
            raise ValueError(
                "DIGILOCKER_CLIENT_ID is not set. "
                "Add it to .env or switch VERIFICATION_MODE=dummy."
            )
        params = (
            f"?response_type=code"
            f"&client_id={DIGILOCKER_CLIENT_ID}"
            f"&redirect_uri={DIGILOCKER_REDIRECT_URI}"
            f"&state={state}"
            f"&scope=openid"
        )
        return DIGILOCKER_AUTH_URL + params

    @staticmethod
    def _exchange_code_for_token(auth_code: str) -> str:
        resp = requests.post(
            DIGILOCKER_TOKEN_URL,
            data={
                "code": auth_code,
                "grant_type": "authorization_code",
                "client_id": DIGILOCKER_CLIENT_ID,
                "client_secret": DIGILOCKER_CLIENT_SECRET,
                "redirect_uri": DIGILOCKER_REDIRECT_URI,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    @staticmethod
    def _fetch_aadhaar_xml(access_token: str) -> dict:
        resp = requests.get(
            DIGILOCKER_AADHAAR_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.text)
        uid_data = root.find(".//UidData/Poi")
        if uid_data is None:
            raise ValueError("Unexpected Aadhaar XML structure from DigiLocker")
        dob_str = uid_data.attrib.get("dob", "") 
        name = uid_data.attrib.get("name", "")
        if dob_str:
            parts = dob_str.split("-")
            dob_iso = f"{parts[2]}-{parts[1]}-{parts[0]}"
        else:
            dob_iso = ""
        return {"name": name, "dob": dob_iso}

    @staticmethod
    def verify(db: Session, aadhaar_number: str, dob_submitted: date,
               auth_code: str = None) -> dict:
        if not auth_code:
            return {
                "success": False,
                "verified_dob": None,
                "failure_reason": "DigiLocker auth_code is required for real Aadhaar verification",
            }
        if not DIGILOCKER_CLIENT_ID:
            raise ValueError(
                "DIGILOCKER_CLIENT_ID is not set. "
                "Add it to .env or switch VERIFICATION_MODE=dummy."
            )
        try:
            token = DigiLockerAadhaarProvider._exchange_code_for_token(auth_code)
            aadhaar_data = DigiLockerAadhaarProvider._fetch_aadhaar_xml(token)

            verified_dob_str = aadhaar_data.get("dob", "")
            if not verified_dob_str:
                return {
                    "success": False,
                    "verified_dob": None,
                    "failure_reason": "Could not extract DOB from DigiLocker Aadhaar data",
                }

            verified_dob = date.fromisoformat(verified_dob_str)
            if verified_dob != dob_submitted:
                return {
                    "success": False,
                    "verified_dob": verified_dob_str,
                    "failure_reason": "DOB mismatch — submitted"
                }

            return {
                "success": True,
                "verified_dob": verified_dob_str,
                "failure_reason": None,
            }

        except requests.RequestException as e:
            logger.error(f"DigiLocker API error: {e}")
            raise RuntimeError("Aadhaar verification service temporarily unavailable") from e
def get_aadhaar_provider():
    if VERIFICATION_MODE == "api":
        logger.info("Aadhaar provider: DigiLocker (real API)")
        return DigiLockerAadhaarProvider
    logger.info("Aadhaar provider: Dummy (local DB)")
    return DummyAadhaarProvider
