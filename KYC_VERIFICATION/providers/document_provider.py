import logging
import requests
from core.config import VERIFICATION_MODE, HYPERVERGE_APP_ID, HYPERVERGE_APP_KEY, HYPERVERGE_API_URL
from models.document_upload import DocumentType

logger = logging.getLogger(__name__)


class DummyDocumentProvider:
    """
    Dummy mode — no OCR, no mock data.
    Document is uploaded and stays UPLOADED until admin reviews it.
    Admin can APPROVE or REJECT via the admin panel.
    """

    @staticmethod
    def verify(document_type: DocumentType, file_path: str, registered_name: str) -> dict:
        return {
            "success":               True,
            "extracted_name":        None,
            "extracted_id_number":   None,
            "name_match_percentage": None,
            "verification_remarks":  None,
        }


class HyperVergeDocumentProvider:
    """
    Real OCR via HyperVerge API (https://docs.hyperverge.co/).
    Extracts name + ID number, calculates name_match_percentage vs registered name.
    Set VERIFICATION_MODE=api and provide HYPERVERGE_APP_ID + HYPERVERGE_APP_KEY in .env.
    """

    ENDPOINT_MAP = {
        DocumentType.PAN_CARD:       "/readPAN",
        DocumentType.AADHAAR_FRONT:  "/readAadhaarFront",
        DocumentType.AADHAAR_BACK:   "/readAadhaarBack",
        DocumentType.SALARY_SLIP:    "/readSalarySlip",
        DocumentType.BANK_STATEMENT: "/readBankStatement",
    }

    NAME_FIELD_MAP = {
        DocumentType.PAN_CARD:       "name",
        DocumentType.AADHAAR_FRONT:  "name",
        DocumentType.AADHAAR_BACK:   None,
        DocumentType.SALARY_SLIP:    "employeeName",
        DocumentType.BANK_STATEMENT: "accountName",
    }

    ID_FIELD_MAP = {
        DocumentType.PAN_CARD:       "idNumber",
        DocumentType.AADHAAR_FRONT:  "idNumber",
        DocumentType.AADHAAR_BACK:   "idNumber",
        DocumentType.SALARY_SLIP:    None,
        DocumentType.BANK_STATEMENT: None,
    }

    @staticmethod
    def _name_match(a: str, b: str) -> float:
        a, b = a.upper().strip(), b.upper().strip()
        if a == b:
            return 100.0
        longer = max(len(a), len(b))
        if longer == 0:
            return 100.0
        matches = sum(c1 == c2 for c1, c2 in zip(a, b))
        return round((matches / longer) * 100, 2)

    @staticmethod
    def verify(document_type: DocumentType, file_path: str, registered_name: str) -> dict:
        if not HYPERVERGE_APP_ID or not HYPERVERGE_APP_KEY:
            raise ValueError(
                "HYPERVERGE_APP_ID and HYPERVERGE_APP_KEY are required. "
                "Add them to .env or switch VERIFICATION_MODE=dummy."
            )

        endpoint = HyperVergeDocumentProvider.ENDPOINT_MAP.get(document_type)
        # FIX: was HYPERVERGE_URL (undefined) → correctly uses HYPERVERGE_API_URL from config
        url = HYPERVERGE_API_URL.rstrip("/") + endpoint

        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    url,
                    files={"file": (file_path.split("/")[-1], f)},
                    headers={"appId": HYPERVERGE_APP_ID, "appKey": HYPERVERGE_APP_KEY},
                    timeout=30,
                )
                resp.raise_for_status()

            data   = resp.json()
            status = data.get("status", "failure")

            if status != "success":
                return {
                    "success":               False,
                    "extracted_name":        None,
                    "extracted_id_number":   None,
                    "name_match_percentage": None,
                    "verification_remarks":  data.get("error", "Document verification failed"),
                }

            details = data.get("result", {}).get("details", [{}])[0]
            fields  = {k: v.get("value", "") for k, v in details.get("fieldsExtracted", {}).items()}

            name_key = HyperVergeDocumentProvider.NAME_FIELD_MAP.get(document_type)
            id_key   = HyperVergeDocumentProvider.ID_FIELD_MAP.get(document_type)

            extracted_name      = fields.get(name_key) if name_key else None
            extracted_id_number = fields.get(id_key)   if id_key   else None

            name_match = None
            if extracted_name and registered_name:
                name_match = HyperVergeDocumentProvider._name_match(extracted_name, registered_name)

            return {
                "success":               True,
                "extracted_name":        extracted_name,
                "extracted_id_number":   extracted_id_number,
                "name_match_percentage": name_match,
                "verification_remarks":  None,
            }

        except requests.RequestException as e:
            logger.error(f"HyperVerge API error for {document_type.value}: {e}")
            raise RuntimeError("Document verification service temporarily unavailable") from e


def get_document_provider():
    if VERIFICATION_MODE == "api":
        logger.info("Document provider: HyperVerge (real OCR API)")
        return HyperVergeDocumentProvider
    logger.info("Document provider: Dummy (admin manual review flow)")
    return DummyDocumentProvider
