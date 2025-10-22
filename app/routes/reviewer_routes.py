from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi import UploadFile, File
from app.services.s3_service import upload_to_s3
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.models.reviewer import Reviewer
from app.models.photo import Photo
from app.models.user import User
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel
from app.auth.reviewer_auth import get_current_reviewer
import jwt, os

class PhotoStatusUpdate(BaseModel):
    status: str  # expected values: pending | approved | rejected

router = APIRouter(prefix="/api/v1/reviewer", tags=["Reviewer"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "supersecretkey")


@router.post("/login")
def reviewer_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    reviewer = db.query(Reviewer).filter(Reviewer.email == form_data.username).first()
    if not reviewer or not pwd_context.verify(form_data.password, reviewer.password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = jwt.encode(
        {"reviewer_id": reviewer.id, "email": reviewer.email},
        SECRET_KEY,
        algorithm="HS256",
    )

    return {
        "success": True,
        "message": "Reviewer logged in successfully.",
        "access_token": token,
        "token_type": "bearer",
    }
    
@router.get("/dashboard")
def get_all_photos_with_users(db: Session = Depends(get_db), current_reviewer: Reviewer = Depends(get_current_reviewer)):
    photos = (
        db.query(Photo, User)
        .join(User, User.id == Photo.user_id)
        .order_by(Photo.created_at.desc())
        .all()
    )

    if not photos:
        raise HTTPException(status_code=404, detail="No photos found.")

    result = []
    for photo, user in photos:
        result.append({
            "photo_id": photo.id,
            "photo_url": photo.photo_url,
            "filename": photo.filename,
            "status": photo.status,
            "created_at": photo.created_at,
            "updated_at": photo.updated_at,
            "user": {
                "user_id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "phone": user.phone,
            },
        })

    return {
        "success": True,
        "message": "All user photos fetched successfully.",
        "total": len(result),
        "data": result,
    }
    
@router.get("/photos/{photo_id}")
def get_photo_by_id(photo_id: int, db: Session = Depends(get_db), current_reviewer: Reviewer = Depends(get_current_reviewer)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found.")
    
    user = db.query(User).filter(User.id == photo.user_id).first()

    return {
        "success": True,
        "message": "Photo fetched successfully.",
        "data": {
            "photo_id": photo.id,
            "photo_url": photo.photo_url,
            "filename": photo.filename,
            "status": photo.status,
            "created_at": photo.created_at,
            "updated_at": photo.updated_at,
            "user": {
                "user_id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "phone": user.phone,
            },
        },
    }


@router.put("/photos/{photo_id}")
async def edit_photo(photo_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), current_reviewer: Reviewer = Depends(get_current_reviewer)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found.")

    user = db.query(User).filter(User.id == photo.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Associated user not found.")

    old_filename = photo.filename

    # Upload new photo to S3
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    new_filename = f"{user.last_name}_{user.first_name}_{timestamp}.jpg"
    new_url = upload_to_s3(file, new_filename)

    # Delete old photo from S3
    from app.services.s3_service import delete_from_s3
    delete_from_s3(old_filename)

    # Update DB record
    photo.filename = new_filename
    photo.photo_url = new_url
    photo.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(photo)

    return {
        "success": True,
        "message": "Photo replaced successfully.",
        "data": {
            "photo_id": photo.id,
            "photo_url": photo.photo_url,
            "filename": photo.filename,
            "status": photo.status,
        },
    }
    


@router.put("/update-photo-status/{photo_id}")
def update_photo_status(photo_id: int, payload: PhotoStatusUpdate, db: Session = Depends(get_db), current_reviewer: Reviewer = Depends(get_current_reviewer)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found.")

    valid_statuses = ["pending", "approved", "rejected"]
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    photo.status = payload.status
    db.commit()
    db.refresh(photo)

    return {
        "success": True,
        "message": f"Photo status updated to '{payload.status}' successfully.",
        "data": {
            "photo_id": photo.id,
            "photo_url": photo.photo_url,
            "status": photo.status,
        },
    }
    
@router.delete("/photos/{photo_id}")
def delete_photo(photo_id: int, db: Session = Depends(get_db), current_reviewer: Reviewer = Depends(get_current_reviewer)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found.")

    from app.services.s3_service import delete_from_s3
    delete_from_s3(photo.filename)

    db.delete(photo)
    db.commit()

    return {
        "success": True,
        "message": f"Photo with ID {photo_id} deleted successfully from database and S3."
    }
