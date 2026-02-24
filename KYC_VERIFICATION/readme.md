# KYC Verification Module

A FastAPI-based Know Your Customer (KYC) verification backend for loan service platforms. Supports **dummy mode** (local DB, no external APIs) and **API mode** (real third-party integrations) via a single environment variable switch.

---

## Project Structure

```
KYC_VERIFICATION/
├── main.py                            # FastAPI app entry point
├── dummy_data.py                      # Seed script — run once for test data
├── requirements.txt
├── core/
│   ├── config.py                      # All env vars and constants
│   └── database.py                    # SQLAlchemy engine + session
├── models/                            # SQLAlchemy ORM models
│   ├── user_profile.py
│   ├── document_upload.py
│   ├── kyc_pan_verification.py
│   ├── kyc_aadhaar_verification.py
│   ├── kyc_bank_verification.py
│   ├── attempt_tracker.py
│   ├── dummy_pan.py
│   └── dummy_bank_account.py
├── providers/                         # Dummy vs real API logic
│   ├── pan_provider.py                # DummyPAN / Karza
│   ├── aadhaar_provider.py            # DummyAadhaar / DigiLocker
│   ├── bank_provider.py               # DummyBank / Cashfree
│   └── document_provider.py          # DummyDoc / HyperVerge OCR
├── repositories/                      # Database query layer
├── routers/                           # FastAPI route handlers
│   ├── profile_router.py
│   ├── pan_router.py
│   ├── aadhaar_router.py
│   ├── bank_router.py
│   ├── document_router.py
│   └── admin_router.py
├── schemas/                           # Pydantic request/response models
├── services/                          # Business logic
│   ├── registration_service.py
│   ├── pan_verification_service.py
│   ├── aadhaar_verification_service.py
│   ├── bank_verification_service.py
│   ├── document_upload_service.py
│   └── auto_cleanup.py                # Background cleanup thread
└── utils/
    └── name_matcher.py                # Fuzzy name comparison (SequenceMatcher)
```

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Create `.env`
```env
# Database (required)
DATABASE_URL=postgresql://user:password@localhost:5432/kyc_db

# Mode: "dummy" (default, no API keys needed) or "api" (real providers)
VERIFICATION_MODE=dummy

# Admin panel key (required)
ADMIN_API_KEY=your-secret-admin-key

# ── Only required when VERIFICATION_MODE=api ──────────────

# PAN → Karza
KARZA_API_KEY=
KARZA_PAN_URL=https://api.karza.in/v3/sync/pan-verification

# Aadhaar → DigiLocker
DIGILOCKER_CLIENT_ID=
DIGILOCKER_CLIENT_SECRET=
DIGILOCKER_REDIRECT_URI=
DIGILOCKER_AUTH_URL=https://api.digitallocker.gov.in/public/oauth2/1/authorize
DIGILOCKER_TOKEN_URL=https://api.digitallocker.gov.in/public/oauth2/1/token
DIGILOCKER_AADHAAR_URL=https://api.digitallocker.gov.in/public/oauth2/1/xml/eaadhaar

# Bank → Cashfree
CASHFREE_APP_ID=
CASHFREE_SECRET_KEY=
CASHFREE_BANK_URL=https://api.cashfree.com/verification/bank-account/sync

# Documents OCR → HyperVerge
HYPERVERGE_APP_ID=
HYPERVERGE_APP_KEY=
HYPERVERGE_API_URL=https://ind-docs.hyperverge.co/v2.0

# Auto-cleanup (optional, defaults shown)
RETENTION_DAYS=90
TRACKER_CLEANUP_HOURS=48
REJECTED_DOCS_RETENTION_DAYS=90
```

### 3. Seed dummy data (dummy mode only)
```bash
python dummy_data.py
```
Inserts 83 test records into `dummy_pans` and `dummy_bank_accounts` tables.

### 4. Start the server
```bash
uvicorn main:app --reload
```
API docs available at: **http://127.0.0.1:8000/docs**

---

## KYC Verification Flow

```
Step 1 → Register user profile
Step 2 → PAN verification (name match against dummy DB or Karza API)
Step 3 → Aadhaar verification (DOB match — 2 step: initiate token → verify)
Step 4 → Bank account verification (name + IFSC + account match)
Step 5 → Upload required documents (repeat for each document type)
Step 6 → Admin reviews documents → APPROVE or REJECT
         ↓
       KYC status = COMPLETED ✓
```

---

## API Reference

### User Profile

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/user/profile` | Register new user |
| GET | `/api/v1/user/profile?user_id=1` | Get profile and KYC status |
| PUT | `/api/v1/user/profile?user_id=1` | Update profile (locked fields blocked after verification) |

**Register body:**
```json
{
  "email": "user@example.com",
  "full_name": "Rahul Sharma",
  "dob": "1990-05-15",
  "address": "H.No 12/3, MG Road, Hyderabad, Telangana - 500001, India",
  "employment_type": "Salaried",
  "monthly_income": 50000,
  "aadhaar_number": "123456789012",
  "pan_number": "ABCDE1234F"
}
```

---

### PAN Verification

| Method | Endpoint | Body |
|---|---|---|
| POST | `/api/v1/kyc/pan-verify` | `{"user_id": 1}` |

Looks up PAN from `dummy_pans` table (dummy) or Karza API (api mode). Checks name fuzzy match ≥ 80%.

---

### Aadhaar Verification (2-step)

| Method | Endpoint | Body |
|---|---|---|
| POST | `/api/v1/kyc/aadhaar-initiate` | `{"user_id": 1}` |
| POST | `/api/v1/kyc/aadhaar-verify` | `{"user_id": 1, "initiate_token": "...", "auth_code": null}` |

- **Dummy mode:** `auth_code` = null. DOB checked against `dummy_pans` table.
- **API mode:** `auth_code` = DigiLocker OAuth code from redirect URL.
- Session token expires in **10 minutes**. Must re-initiate for each attempt.

---

### Bank Verification

| Method | Endpoint | Body |
|---|---|---|
| POST | `/api/v1/kyc/bank-verify` | See below |

```json
{
  "user_id": 1,
  "account_number": "1234567890",
  "account_holder_name": "Rahul Sharma",
  "bank_name": "HDFC Bank",
  "ifsc": "HDFC0001234"
}
```

---

### Document Upload & Verification

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/documents/upload` | Upload a document (multipart form) |
| GET | `/api/v1/documents/list?user_id=1` | List all documents + missing list |
| DELETE | `/api/v1/documents/{id}?user_id=1` | Delete UPLOADED or REJECTED doc |

**Upload form fields:** `user_id` (int) · `document_type` (string) · `file` (binary)

**Document types:**
| Type | Accepted Format | Description |
|---|---|---|
| `PAN_CARD` | JPG, PNG | PAN card photo |
| `AADHAAR_FRONT` | JPG, PNG | Aadhaar front side |
| `AADHAAR_BACK` | JPG, PNG | Aadhaar back side |
| `SALARY_SLIP` | PDF | Latest salary slip |
| `BANK_STATEMENT` | PDF | 3-month bank statement |

Max file size: **2MB**

**Document status flow:**

```
Dummy mode:   UPLOADED → (admin) → APPROVED ✓  or  REJECTED ✗
API mode:     UPLOADED → (OCR)   → VERIFIED  → (admin) → APPROVED ✓
                                 → REJECTED ✗  (user must re-upload)
```

---

### Admin Panel

All endpoints require header: `x-admin-key: your-secret-admin-key`

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/admin/documents/review` | Approve or reject a document |
| GET | `/api/admin/stats/documents` | Count documents by status |
| GET | `/api/admin/stats/kyc` | KYC completion stats |
| GET | `/api/admin/users` | List all users (filter by kyc_status) |
| GET | `/api/admin/users/{user_id}` | Full user detail + all documents |

**Review body:**
```json
{
  "document_id": 5,
  "action": "APPROVE",
  "admin_remarks": "All documents look valid",
  "reviewed_by": "admin@company.com"
}
```
> `admin_remarks` is **required** when action is `REJECT`.

---

## Dummy vs API Mode

### PAN
| | Dummy | API (Karza) |
|---|---|---|
| Data source | `dummy_pans` table | Karza PAN API |
| Match logic | SequenceMatcher fuzzy ≥ 80% | Same on API response |
| Needs keys | No | `KARZA_API_KEY` |

### Aadhaar
| | Dummy | API (DigiLocker) |
|---|---|---|
| Data source | `dummy_pans` table (DOB field) | DigiLocker OAuth |
| auth_code | Not needed | Required from redirect |
| Needs keys | No | DigiLocker app credentials |

### Bank
| | Dummy | API (Cashfree) |
|---|---|---|
| Data source | `dummy_bank_accounts` table | Cashfree API |
| Validates | Account · IFSC · bank name · name | Account · IFSC · name |
| Needs keys | No | `CASHFREE_APP_ID` + `CASHFREE_SECRET_KEY` |

### Documents
| | Dummy | API (HyperVerge) |
|---|---|---|
| On upload | Stays `UPLOADED` | OCR runs in background |
| OCR result | None | Extracts name, ID number, match % |
| Who approves | Admin only | Admin (OCR auto-verifies first) |
| Needs keys | No | `HYPERVERGE_APP_ID` + `HYPERVERGE_APP_KEY` |

---

## Security Features

| Feature | Detail |
|---|---|
| Attempt limits | Max 3 tries for PAN / Aadhaar / Bank |
| Cooldown | 24hr block after 3 failed attempts |
| Field locking | PAN, name, Aadhaar, DOB, bank locked after verification |
| Session token | Aadhaar initiate token valid for 10 minutes only |
| Admin key | All `/api/admin/*` routes require `x-admin-key` header |
| Auto cleanup | Background thread clears expired trackers and old rejected docs every 24h |

---

## Required Documents for KYC Completion

All 4 must reach **APPROVED** status:

1. `AADHAAR_FRONT`
2. `AADHAAR_BACK`
3. `PAN_CARD`
4. `SALARY_SLIP` **or** `BANK_STATEMENT` (at least one)

---

## Third-Party APIs (API mode)

| Provider | Purpose | Docs |
|---|---|---|
| [Karza](https://karza.in) | PAN number verification | https://docs.karza.in |
| [DigiLocker](https://digilocker.gov.in) | Aadhaar OAuth verification | https://partners.digitallocker.gov.in |
| [Cashfree](https://cashfree.com) | Bank account verification | https://docs.cashfree.com/docs/bank-account-verification |
| [HyperVerge](https://hyperverge.co) | Document OCR | https://docs.hyperverge.co |