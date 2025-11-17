from datetime import datetime
import uuid
from fastapi import APIRouter, HTTPException, Depends
from fastapi import UploadFile, File
import fastapi
import requests
from app.background_tasks.tasks import create_video_for_user_task
from app.services.s3_service import upload_to_s3
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.models.reviewer import Reviewer
from app.models.photo import Photo
from app.models.video import Video
from app.models.user import User
from app.services.video_creation import create_video_from_images
from app.services.s3_service import upload_to_s3
import tempfile
import shutil
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import joinedload
from app.auth.reviewer_auth import get_current_reviewer
import jwt, os
from dotenv import load_dotenv
load_dotenv()

class PhotoStatusUpdate(BaseModel):
    status: str  # expected values: pending | approved | rejected

router = APIRouter(prefix="/api/v1/reviewer", tags=["Reviewer"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("JWT_SECRET_KEY")


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
        "reviewer": {
            "username": reviewer.username,
            "email": reviewer.email,
        },
    }

@router.get("/dashboard")
def get_all_photos_grouped_by_user(
    db: Session = Depends(get_db),
    current_reviewer: Reviewer = Depends(get_current_reviewer),
    page: int = 1,
    limit: int = 10
):
    if page < 1 or limit < 1:
        raise HTTPException(status_code=400, detail="page and limit must be positive integers.")

    total_users = db.query(User).count()
    users = (
        db.query(User)
        .options(joinedload(User.photos))
        .order_by(User.id.asc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    if not users:
        return {
            "success": True,
            "message": "No users found.",
            "page": page,
            "limit": limit,
            "total_users": 0,
            "total_pages": 0,
            "data": [],
        }

    result = []
    for user in users:
        user_photos = [
            {
                "photo_id": photo.id,
                "photo_url": photo.photo_url,
                "filename": photo.filename,
                "status": photo.status,
                "created_at": photo.created_at,
                "updated_at": photo.updated_at
            }
            for photo in user.photos
        ]

        result.append({
            "user_id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone": user.phone,
            "photos": user_photos
        })

    return {
        "success": True,
        "message": "All user photos fetched successfully.",
        "page": page,
        "limit": limit,
        "total_users": total_users,
        "total_photos": sum(len(user.photos) for user in users),
        "total_pages": (total_users + limit - 1) // limit,
        "data": result,
    }

@router.get("/videos", dependencies=[Depends(get_current_reviewer)])
def get_all_videos_dashboard(
    db: Session = Depends(get_db),
    current_reviewer: Reviewer = Depends(get_current_reviewer),
    page: int = 1,
    limit: int = 10
):
    if page < 1 or limit < 1:
        raise HTTPException(status_code=400, detail="page and limit must be positive integers.")

    total_users = db.query(User).count()
    users = (
        db.query(User)
        .options(joinedload(User.videos))
        .order_by(User.id.asc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    if not users:
        return {
            "success": True,
            "message": "No users found.",
            "page": page,
            "limit": limit,
            "total_users": 0,
            "total_videos": 0,
            "total_pages": 0,
            "data": [],
        }

    result = []
    for user in users:
        user_videos = [
            {
                "video_id": video.id,
                "video_url": video.video_url,
                "filename": video.filename,
                "created_at": video.created_at,
            }
            for video in user.videos
        ]

        result.append({
            "user_id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone": user.phone,
            "videos": user_videos
        })

    return {
        "success": True,
        "message": "All user videos fetched successfully.",
        "page": page,
        "limit": limit,
        "total_users": total_users,
        "total_videos": sum(len(user.videos) for user in users),
        "total_pages": (total_users + limit - 1) // limit,
        "data": result,
    }



@router.get("/videos/{video_id}", dependencies=[Depends(get_current_reviewer)])
def get_video_by_id(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")

    return {
        "success": True,
        "message": "Video fetched successfully.",
        "data": [
            {
                "user_id": video.user.id if video.user else None,
                "first_name": video.user.first_name if video.user else None,
                "last_name": video.user.last_name if video.user else None,
                "email": video.user.email if video.user else None,
                "videos": [
                    {
                        "video_id": video.id,
                        "video_url": video.video_url,
                        "filename": video.filename,
                        "created_at": video.created_at
                    }
                ]
            }
        ]
    }


@router.delete("/videos/{video_id}", dependencies=[Depends(get_current_reviewer)])
def delete_video_by_id(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")

    from app.services.s3_service import delete_from_s3
    delete_from_s3(video.filename)

    db.delete(video)
    db.commit()

    return {
        "success": True,
        "message": f"Video with ID {video_id} deleted successfully from database and S3."
    }


@router.post("/create-video", dependencies=[Depends(get_current_reviewer)])
async def create_video_for_user(
    request: "fastapi.Request",
    db: Session = Depends(get_db),
    current_reviewer: Reviewer = Depends(get_current_reviewer),
):
    import json
    body = await request.json()
    photo_ids = body.get("photo_ids")

    if not photo_ids or not isinstance(photo_ids, list) or len(photo_ids) == 0:
        raise HTTPException(
            status_code=400,
            detail="photo_ids must be provided as a non-empty list. Example: {\"photo_ids\": [1,2,3]}",
        )
    
    photos = db.query(Photo).filter(Photo.id.in_(photo_ids)).all()

    if not photos:
        raise HTTPException(status_code=404, detail="No photos found.")

    user_ids = {p.user_id for p in photos}
    if len(user_ids) > 1:
        raise HTTPException(
            status_code=400,
            detail="All photos must belong to the same user."
        )

    # invalid = [p.id for p in photos if p.status != "approved"]
    # if invalid:
    #     raise HTTPException(
    #         status_code=400,
    #         detail=f"These photos are not approved: {invalid}"
    #     )
    
    # create_video_for_user_task.delay(photo_ids)

    pending = [p.id for p in photos if p.status == "pending"]
    if pending:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot create video. These photos are pending: {pending}"
        )
    
    approved_photos = [p.id for p in photos if p.status == "approved"]
    if not approved_photos:
        raise HTTPException(
            status_code=400,
            detail="No approved photos available to create video."
        )
    
    create_video_for_user_task.delay(approved_photos)

    return {
        "success": True,
        "message": "Video creation started in the background. You’ll be notified once it’s complete.",
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
        "data": [
            {
                "user_id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "phone": user.phone,
                "photos": [
                    {
                        "photo_id": photo.id,
                        "photo_url": photo.photo_url,
                        "filename": photo.filename,
                        "status": photo.status,
                        "created_at": photo.created_at,
                        "updated_at": photo.updated_at
                    }
                ]
            }
        ]
}



@router.put("/photos/{photo_id}")
async def edit_photo(
    photo_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_reviewer: Reviewer = Depends(get_current_reviewer)
):
    import asyncio
    import io
    from datetime import datetime
    from app.services.s3_service import upload_to_s3, delete_from_s3

    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found.")

    user = db.query(User).filter(User.id == photo.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Associated user not found.")

    old_filename = photo.filename

    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise ValueError("Empty file upload detected.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read upload: {e}")

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    new_filename = f"{user.last_name}_{user.first_name}_{timestamp}.jpg"

    class TempUploadFile:
        def __init__(self, buffer_io):
            self.file = io.BytesIO(buffer_io)
            self.content_type = file.content_type or "image/jpeg"

    new_upload_obj = TempUploadFile(file_bytes)

    loop = asyncio.get_running_loop()
    delete_task = loop.run_in_executor(None, delete_from_s3, old_filename)
    upload_task = loop.run_in_executor(None, upload_to_s3, new_upload_obj, new_filename)

    try:
        _, new_url = await asyncio.gather(delete_task, upload_task)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 operation failed: {e}")

    try:
        photo.filename = new_filename
        photo.photo_url = new_url
        photo.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(photo)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database update failed: {e}")

    return {
        "success": True,
        "message": "Photo replaced successfully.",
        "data": [
            {
                "user_id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "phone": user.phone,
                "photos": [
                    {
                        "photo_id": photo.id,
                        "photo_url": photo.photo_url,
                        "filename": photo.filename,
                        "status": photo.status,
                        "created_at": photo.created_at,
                        "updated_at": photo.updated_at
                    }
                ]
            }
        ]
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
        "data": [
            {
                "user_id": photo.user.id if photo.user else None,
                "first_name": photo.user.first_name if photo.user else None,
                "last_name": photo.user.last_name if photo.user else None,
                "email": photo.user.email if photo.user else None,
                "phone": photo.user.phone if photo.user else None,
                "photos": [
                    {
                        "photo_id": photo.id,
                        "photo_url": photo.photo_url,
                        "filename": photo.filename,
                        "status": photo.status,
                        "created_at": photo.created_at,
                        "updated_at": photo.updated_at
                    }
                ]
            }
        ]
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
