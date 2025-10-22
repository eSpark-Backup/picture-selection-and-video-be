from app.database.connection import Base, engine
from app.models.user import User
from app.models.reviewer import Reviewer
from app.models.photo import Photo
from app.models.original_photo import OriginalPhoto
from app.models.video import Video

print("⚙️ Resetting database...")

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

print("✅ Database reset successfully.")
