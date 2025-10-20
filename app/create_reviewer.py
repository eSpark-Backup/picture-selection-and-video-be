from app.database.connection import SessionLocal
from app.models.reviewer import Reviewer
from passlib.context import CryptContext

# Create an instance of CryptContext with bcrypt scheme
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Create a new session
db = SessionLocal()

# Hash the password using passlib's bcrypt
hashed_password = pwd_context.hash("SecurePass123#")

# Create a new reviewer object
reviewer = Reviewer(
    username="reviewer",
    email="reviewer@hello.com",
    password=hashed_password
)

# Add the reviewer to the database
db.add(reviewer)
db.commit()
db.close()

print("✅ Reviewer created successfully")
