from faker import Faker
import random
import string
import hashlib
from sqlalchemy import delete
from core.database import SessionLocal, Base, engine
from models.module1_user import User
from models.dummy_pan import DummyPAN
from models.dummy_bank_account import DummyBankAccount

Base.metadata.create_all(bind=engine, checkfirst=True)

MIN_AGE = 18
MAX_AGE = 60

fake = Faker("en_IN")
db = SessionLocal()

BANKS = [
    ("State Bank of India", "SBIN"),
    ("HDFC Bank", "HDFC"),
    ("ICICI Bank", "ICIC"),
    ("Axis Bank", "UTIB"),
    ("Punjab National Bank", "PUNB"),
    ("Canara Bank", "CNRB"),
]

AP_DISTRICTS = [
    "Kurnool", "Anantapur", "Kadapa", "Chittoor", "Visakhapatnam",
    "Vizianagaram", "Srikakulam", "East Godavari", "West Godavari", "Krishna",
]

TG_DISTRICTS = [
    "Hyderabad", "Warangal", "Nizamabad", "Khammam", "Karimnagar",
    "Adilabad", "Mahabubnagar", "Ranga Reddy", "Medak", "Nalgonda",
]

DISTRICTS = AP_DISTRICTS + TG_DISTRICTS

MALE_NAMES = [
    "Venkatesh Reddy", "Ramesh Naidu", "Srinivas Rao", "Krishna Goud", "Mohan Yadav",
    "Ravi Kumar", "Suresh Babu", "Prasad Murthy", "Nagesh Chowdary", "Mahesh Shaik",
    "Chandu Shetty", "Rajesh Palli", "Kishore Kamma", "Bhaskar Dora", "Sathish Reddy",
    "Anil Naidu", "Vijay Rao", "Kiran Goud", "Lakshman Yadav", "Narasimha Kumar",
    "Phani Babu", "Sai Murthy", "Teja Chowdary", "Karthik Shaik", "Harish Shetty",
    "Prasanth Palli", "Bhargav Kamma", "Sravan Dora", "Chaitanya Reddy", "Aditya Naidu",
    "Vivek Rao", "Guna Goud", "Anirudh Yadav", "Sathwik Kumar", "Hitesh Babu",
    "Akhil Murthy", "Ramachandra Chowdary", "Karthikeya Shaik", "Balakrishna Shetty",
    "Giridhar Palli", "Govind Kamma", "Narayana Dora", "Raghunath Reddy", "Rajendra Naidu"
]

FEMALE_NAMES = [
    "Lakshmi Devi", "Sridevi Naidu", "Padma Rao", "Sunitha Goud", "Anuradha Yadav",
    "Radhika Kumar", "Geetha Babu", "Uma Murthy", "Vijaya Chowdary", "Saritha Shaik",
    "Pavani Shetty", "Swathi Palli", "Priyanka Kamma", "Divya Dora", "Nandini Reddy",
    "Revathi Naidu", "Kavitha Rao", "Sudha Goud", "Mythili Yadav", "Sujatha Kumar",
    "Deepa Babu", "Anusha Murthy", "Meena Chowdary", "Suma Shaik", "Neha Shetty",
    "Pooja Palli", "Rani Kamma", "Latha Dora", "Shobha Reddy", "Vani Naidu",
    "Sailaja Rao", "Madhuri Goud", "Bindu Yadav", "Harika Kumar", "Sruthi Babu",
    "Nithya Murthy", "Varsha Chowdary", "Supriya Shaik", "Bhargavi Shetty"
]

random.seed(42)
ALL_NAMES = MALE_NAMES + FEMALE_NAMES
random.shuffle(ALL_NAMES)

def generate_pan(name: str) -> str:
    letters = string.ascii_uppercase
    first_three = "".join(random.choices(letters, k=3))
    fourth = "F" if name in FEMALE_NAMES else "P"
    fifth = random.choice(letters)
    digits = "".join(random.choices(string.digits, k=4))
    check = random.choice(letters)
    return f"{first_three}{fourth}{fifth}{digits}{check}"

def generate_unique_pan(name, existing_pans):
    while True:
        pan = generate_pan(name)
        if pan not in existing_pans:
            existing_pans.add(pan)
            return pan

def generate_unique_aadhaar(existing_aadhaars):
    while True:
        aadhaar = "".join(random.choices(string.digits, k=12))
        if aadhaar not in existing_aadhaars:
            existing_aadhaars.add(aadhaar)
            return aadhaar

def generate_unique_account(index, existing_accounts):
    while True:
        acc = f"{index+1:03d}{random.randint(1000000, 9999999)}"
        if acc not in existing_accounts:
            existing_accounts.add(acc)
            return acc

def generate_ifsc(prefix: str) -> str:
    branch_code = "".join(random.choices(string.digits, k=6))
    return f"{prefix}0{branch_code}"

def make_username(name: str, index: int) -> str:
    base = name.lower().replace(" ", "_")
    return f"{base}_{index}"

def make_mobile(index: int) -> str:
    prefixes = ["9", "8", "7", "6"]
    prefix = prefixes[index % len(prefixes)]
    rest = f"{index:09d}"[-9:]
    return f"{prefix}{rest}"

def fake_password_hash(username: str) -> str:
    raw = f"Test@1234:{username}"
    return hashlib.sha256(raw.encode()).hexdigest()

print("Clearing existing dummy data...")
db.execute(delete(DummyPAN))
db.execute(delete(DummyBankAccount))
db.execute(delete(User))
db.commit()
print("Cleared.")

existing_pans = set()
existing_aadhaars = set()
existing_accounts = set()

try:
    for i, name in enumerate(ALL_NAMES, start=1):

        username = make_username(name, i)
        gender = "Female" if name in FEMALE_NAMES else "Male"
        district = random.choice(DISTRICTS)
        if district in AP_DISTRICTS:
            state = "Andhra Pradesh"
        else:
            state = "Telangana"

        address = f"{district}, {state}"

        user = User(
            username=username,
            mobile_number=make_mobile(i),
            password_hash=fake_password_hash(username),
            device_id=None,
            role="USER",
        )
        db.add(user)
        db.flush()

        pan = DummyPAN(
            pan_number=generate_unique_pan(name, existing_pans),
            aadhaar_number=generate_unique_aadhaar(existing_aadhaars),
            full_name=name,
            dob=fake.date_of_birth(minimum_age=MIN_AGE, maximum_age=MAX_AGE),
            address=address,
            gender=gender,
        )
        db.add(pan)

        bank_name, prefix = random.choice(BANKS)
        bank = DummyBankAccount(
            account_number=generate_unique_account(i, existing_accounts),
            ifsc=generate_ifsc(prefix),
            bank_name=bank_name,
            account_holder_name=name,
            is_active=random.choice([True, True, True, False])
        )
        db.add(bank)

    db.commit()

except Exception as e:
    db.rollback()
    print(f"\nERROR: {e}")
    raise

finally:
    db.close()