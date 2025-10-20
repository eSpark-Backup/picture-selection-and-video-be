from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.models.user import User
from app.models.photo import Photo
from app.services.s3_service import upload_to_s3
from datetime import datetime
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


class UserCreateRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: str | None = None


@router.post("/submit")
def submit_user_form(payload: UserCreateRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists.")

    user = User(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone=payload.phone,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "success": True,
        "message": "User form submitted successfully.",
        "data": {"user_id": user.id, "email": user.email, "phone": user.phone},
    }


@router.post("/upload-photos/{user_id}")
async def upload_photos(
    user_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if len(files) > 30:
        raise HTTPException(status_code=400, detail="You can upload up to 30 photos only.")

    uploaded_photos = []

    for file in files:
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        filename = f"{user.last_name}_{user.first_name}_{timestamp}.jpg"

        s3_url = upload_to_s3(file, filename)

        photo = Photo(user_id=user.id, filename=filename, photo_url=s3_url)
        db.add(photo)
        uploaded_photos.append({"filename": filename, "photo_url": s3_url})

    db.commit()

    return {
        "success": True,
        "message": "Photos uploaded successfully!",
        "uploaded_photos": uploaded_photos,
    }
