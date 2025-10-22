from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.models.user import User
from app.models.photo import Photo
from app.services.s3_service import upload_to_s3
from app.services.bg_removal import remove_background
from app.services.fill_black_bg import fill_black_background
from app.services.face_detection import detect_faces
from datetime import datetime
from pydantic import BaseModel, EmailStr
from PIL import Image
import io
from app.models.reviewer import Reviewer
from app.models.original_photo import OriginalPhoto
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
import jwt, os

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


class UserCreateRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: str | None = None


@router.post("/upload-original-photos/{user_id}")
async def upload_original_photos(
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
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        filename = f"original_{user.last_name}_{user.first_name}_{timestamp}.jpg"
        s3_url = upload_to_s3(file, filename)

        original_photo = OriginalPhoto(user_id=user.id, filename=filename, photo_url=s3_url)
        db.add(original_photo)
        uploaded_photos.append({"photo_id": id, "filename": filename, "photo_url": s3_url})

    db.commit()
    return {
        "success": True,
        "message": "Original photos uploaded successfully.",
        "uploaded_photos": uploaded_photos,
    }


@router.get("/original-photos/{user_id}")
def get_all_original_photos(user_id: int, db: Session = Depends(get_db)):
    photos = db.query(OriginalPhoto).filter(OriginalPhoto.user_id == user_id).all()
    if not photos:
        raise HTTPException(status_code=404, detail="No original photos found.")
    return {
        "success": True,
        "total": len(photos),
        "data": [
            {
                "photo_id": p.id,
                "photo_url": p.photo_url,
                "filename": p.filename,
                "created_at": p.created_at,
            }
            for p in photos
        ],
    }


@router.get("/original-photo/{photo_id}")
def get_original_photo_by_id(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(OriginalPhoto).filter(OriginalPhoto.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found.")
    return {
        "success": True,
        "data": {
            "photo_id": photo.id,
            "photo_url": photo.photo_url,
            "filename": photo.filename,
            "created_at": photo.created_at,
        },
    }


@router.put("/original-photo/{photo_id}")
async def replace_original_photo(
    photo_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not file:
        raise HTTPException(status_code=400, detail="Exactly one photo file is required.")

    photo = db.query(OriginalPhoto).filter(OriginalPhoto.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found.")

    from app.services.s3_service import delete_from_s3, upload_to_s3
    delete_from_s3(photo.filename)

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    new_filename = f"original_replaced_{timestamp}.jpg"
    new_url = upload_to_s3(file, new_filename)

    photo.filename = new_filename
    photo.photo_url = new_url
    photo.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(photo)

    return {
        "success": True,
        "message": "Original photo replaced successfully.",
        "data": {
            "photo_id": photo.id,
            "photo_url": photo.photo_url,
            "filename": photo.filename,
        },
    }



@router.delete("/original-photo/{photo_id}")
def delete_original_photo(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(OriginalPhoto).filter(OriginalPhoto.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found.")

    from app.services.s3_service import delete_from_s3
    delete_from_s3(photo.filename)

    db.delete(photo)
    db.commit()

    return {"success": True, "message": f"Photo ID {photo_id} deleted successfully."}


@router.post("/submit-form")
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

@router.post("/upload-processed-photos/{user_id}")
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
        try:
            # Step 1: Read image bytes
            image_bytes = await file.read()

            # Step 2: Remove background
            bg_removed_bytes = remove_background(image_bytes)

            # Step 3: Fill background with solid black
            black_bg_bytes = fill_black_background(bg_removed_bytes)

            # Step 4: Detect faces
            final_processed_bytes = detect_faces(black_bg_bytes)

            # Step 5: Convert processed bytes to UploadFile-like object for S3
            processed_image = Image.open(io.BytesIO(final_processed_bytes))
            image_buffer = io.BytesIO()
            processed_image.save(image_buffer, format="JPEG")
            image_buffer.seek(0)

            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
            filename = f"{user.last_name}_{user.first_name}_{timestamp}.jpg"

            # Step 6: Upload to S3
            class TempUploadFile:
                def __init__(self, file_bytes):
                    self.file = file_bytes
                    self.content_type = "image/jpeg"

            s3_url = upload_to_s3(TempUploadFile(image_buffer), filename)

            # Step 7: Save record in DB
            photo = Photo(user_id=user.id, filename=filename, photo_url=s3_url)
            db.add(photo)
            uploaded_photos.append({"filename": filename, "photo_url": s3_url})

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing {file.filename}: {e}")

    db.commit()

    return {
        "success": True,
        "message": "Photos processed and uploaded successfully!",
        "uploaded_photos": uploaded_photos,
    }
