import os
from dotenv import load_dotenv

load_dotenv()

VERIFICATION_MODE = os.getenv("VERIFICATION_MODE", "dummy").lower()

PAN_MAX_ATTEMPTS = 3
AADHAAR_MAX_ATTEMPTS = 3 
BANK_MAX_ATTEMPTS = 3
NAME_MATCH_THRESHOLD = 80.0
PAN_COOLDOWN_HOURS = 24
AADHAAR_COOLDOWN_HOURS = 24  
BANK_COOLDOWN_HOURS = 24

# File Upload Configuration
MAX_FILE_SIZE_MB = 2
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png']
ALLOWED_DOCUMENT_EXTENSIONS = ['.pdf']
UPLOAD_BASE_PATH = "uploads"

RETENTION_DAYS              = int(os.getenv("RETENTION_DAYS",              "90"))
TRACKER_CLEANUP_HOURS       = int(os.getenv("TRACKER_CLEANUP_HOURS",       "48"))
REJECTED_DOCS_RETENTION_DAYS = int(os.getenv("REJECTED_DOCS_RETENTION_DAYS", "90"))

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

KARZA_API_KEY = os.getenv("KARZA_API_KEY", "")
KARZA_PAN_URL = os.getenv("KARZA_PAN_URL", "https://api.karza.in/v3/sync/pan-verification")

DIGILOCKER_CLIENT_ID     = os.getenv("DIGILOCKER_CLIENT_ID", "")
DIGILOCKER_CLIENT_SECRET = os.getenv("DIGILOCKER_CLIENT_SECRET", "")
DIGILOCKER_REDIRECT_URI  = os.getenv("DIGILOCKER_REDIRECT_URI", "")
DIGILOCKER_AUTH_URL      = os.getenv("DIGILOCKER_AUTH_URL",  "https://api.digitallocker.gov.in/public/oauth2/1/authorize")
DIGILOCKER_TOKEN_URL     = os.getenv("DIGILOCKER_TOKEN_URL", "https://api.digitallocker.gov.in/public/oauth2/1/token")
DIGILOCKER_AADHAAR_URL   = os.getenv("DIGILOCKER_AADHAAR_URL", "https://api.digitallocker.gov.in/public/oauth2/1/xml/eaadhaar")

CASHFREE_APP_ID     = os.getenv("CASHFREE_APP_ID", "")
CASHFREE_SECRET_KEY = os.getenv("CASHFREE_SECRET_KEY", "")
CASHFREE_BANK_URL   = os.getenv("CASHFREE_BANK_URL", "https://api.cashfree.com/verification/bank-account/sync")

DOC_MAX_ATTEMPTS       = int(os.getenv("DOC_MAX_ATTEMPTS", "3"))
DOC_COOLDOWN_HOURS     = int(os.getenv("DOC_COOLDOWN_HOURS", "24"))
DOC_MATCH_THRESHOLD    = float(os.getenv("DOC_MATCH_THRESHOLD", "75.0"))

HYPERVERGE_APP_ID      = os.getenv("HYPERVERGE_APP_ID", "")
HYPERVERGE_APP_KEY     = os.getenv("HYPERVERGE_APP_KEY", "")
HYPERVERGE_API_URL     = os.getenv("HYPERVERGE_API_URL", "https://ind-docs.hyperverge.co/v2.0/readKYC")