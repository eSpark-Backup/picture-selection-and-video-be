from app.database.connection import engine, Base
from app.models import user, photo, video

print("🔄 Creating all database tables...")
Base.metadata.create_all(bind=engine)
print("✅ Tables created successfully!")
