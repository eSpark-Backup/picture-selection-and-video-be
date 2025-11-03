from datetime import datetime
import uuid
from fastapi import APIRouter, HTTPException, Depends
from fastapi import UploadFile, File
import fastapi
import requests
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
    
@router.post("/create-video", dependencies=[Depends(get_current_reviewer)])
async def create_video_for_user(
    request: "fastapi.Request",
    db: Session = Depends(get_db),
    current_reviewer: Reviewer = Depends(get_current_reviewer),
):
    """
    Create a video from selected photos (by photo IDs).
    Accepts:
    - JSON body: { "photo_ids": [1, 2, 3] }
    - OR multipart/form-data with field 'photo_ids' as JSON string or CSV.
    """
    import json, os, uuid, tempfile, shutil, requests
    from fastapi import HTTPException
    from app.services.s3_service import s3, BUCKET_NAME

    # --- 1) Parse incoming photo_ids ---
    photo_ids = None
    try:
        body = await request.json()
        if isinstance(body, dict) and "photo_ids" in body:
            photo_ids = body["photo_ids"]
    except Exception:
        pass

    if not photo_ids:
        try:
            form = await request.form()
            if "photo_ids" in form:
                raw = form.get("photo_ids")
                try:
                    photo_ids = json.loads(raw)
                except Exception:
                    if isinstance(raw, str):
                        photo_ids = [int(x) for x in raw.split(",") if x.strip().isdigit()]
        except Exception:
            pass

    if not photo_ids or not isinstance(photo_ids, (list, tuple)) or len(photo_ids) == 0:
        raise HTTPException(
            status_code=400,
            detail="photo_ids must be provided as a non-empty list. Example: {\"photo_ids\": [1,2,3]}",
        )

    try:
        photo_ids = [int(pid) for pid in photo_ids]
    except Exception:
        raise HTTPException(status_code=400, detail="photo_ids must contain integers only.")

    # --- 2) Validate photos ---
    photos = db.query(Photo).filter(Photo.id.in_(photo_ids)).all()
    if not photos:
        raise HTTPException(status_code=404, detail="No valid photos found for given IDs.")

    user_id = photos[0].user_id
    if any(p.user_id != user_id for p in photos):
        raise HTTPException(status_code=400, detail="All photos must belong to the same user.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Associated user not found.")

    # --- 3) Download photos securely with presigned URLs ---
    temp_dir = tempfile.mkdtemp(prefix="video_photos_")
    local_paths, video_path = [], None

    try:
        for photo in photos:
            try:
                # Generate a fresh, short-lived presigned URL for each file
                download_url = s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": BUCKET_NAME, "Key": photo.filename},
                    ExpiresIn=300,  # valid for 5 minutes
                )

                resp = requests.get(download_url, stream=True, timeout=20)
                resp.raise_for_status()
            except requests.RequestException as e:
                raise HTTPException(status_code=400, detail=f"Failed to download photo ID {photo.id}: {str(e)}")

            safe_filename = os.path.basename(photo.filename) or f"{photo.id}.jpg"
            local_path = os.path.join(temp_dir, safe_filename)

            try:
                with open(local_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                local_paths.append(local_path)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to save photo ID {photo.id}: {str(e)}")

        if not local_paths:
            raise HTTPException(status_code=400, detail="No photos were downloaded successfully.")

        # --- 4) Create video ---
        try:
            video_path = create_video_from_images(local_paths)
            if not video_path or not os.path.exists(video_path):
                raise Exception("Video creation returned invalid or missing file.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Video creation failed: {str(e)}")

        # --- 5) Upload video to S3 ---
        s3_filename = f"videos/{uuid.uuid4().hex}_final_video.mp4"
        try:
            with open(video_path, "rb") as vf:
                s3_video_url = upload_to_s3(vf, s3_filename)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload video to S3: {str(e)}")

        # --- 6) Save video record ---
        try:
            video_record = Video(user_id=user_id, video_url=s3_video_url, filename=s3_filename)
            db.add(video_record)
            db.commit()
            db.refresh(video_record)
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Database save failed: {str(e)}")

        return {
            "success": True,
            "message": "Video created, uploaded, and saved successfully.",
            "video_url": s3_video_url,
            "video_id": video_record.id,
            "user": {
                "id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email
            },
            "total_photos_used": len(local_paths),
        }

    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
        try:
            if video_path and os.path.exists(video_path):
                os.remove(video_path)
        except Exception:
            pass


    
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
