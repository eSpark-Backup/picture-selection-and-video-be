from app.database.connection import SessionLocal
from app.models.reviewer import Reviewer
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

db = SessionLocal()

hashed_password = pwd_context.hash("SecurePass123#")

reviewer = Reviewer(
    username="reviewer",
    email="james@showcaseholograms.com",
    # email="reviewer@hello.com",
    password=hashed_password
)

db.add(reviewer)
db.commit()
db.close()

print("✅ Reviewer created successfully")
