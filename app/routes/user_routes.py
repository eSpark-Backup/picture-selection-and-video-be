from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
import fastapi
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.models.user import User
from app.background_tasks.tasks import process_photos_task
from pydantic import BaseModel, EmailStr
from app.background_tasks.tasks import upload_original_photos_task
from app.models.original_photo import OriginalPhoto
import os

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
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) > 30:
        raise HTTPException(status_code=400, detail="You can upload up to 30 photos only.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    file_names = [f.filename for f in files]
    MAX_FILE_SIZE = 5 * 1024 * 1024
    temp_dir = f"/tmp/uploads_user_{user_id}"
    os.makedirs(temp_dir, exist_ok=True)
    for f in files:
        file_content = await f.read()

        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File '{f.filename}' exceeds the 5 MB size limit."
            )
            
        with open(os.path.join(temp_dir, f.filename), "wb") as buffer:
            buffer.write(file_content)

    upload_original_photos_task.delay(user_id, temp_dir, file_names)

    return {
        "success": True,
        "message": "Your photos are being uploaded and processed in the background. You’ll be notified once complete.",
    }

@router.get("/original-photos/{user_id}")
def get_all_original_photos(user_id: int, db: Session = Depends(get_db)):
    photos = db.query(OriginalPhoto).filter(OriginalPhoto.user_id == user_id).all()
    if not photos:
        return {
            "success": True,
            "message": "No original photos found.",
            "total": 0,
            "data": [],
        }
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

    import asyncio
    import io
    from datetime import datetime
    from uuid import uuid4
    from concurrent.futures import ThreadPoolExecutor
    from app.services.s3_service import upload_to_s3, delete_from_s3
    from app.models.original_photo import OriginalPhoto

    if not file:
        raise HTTPException(status_code=400, detail="Exactly one photo file is required.")

    photo = db.query(OriginalPhoto).filter(OriginalPhoto.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found.")

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    unique = uuid4().hex[:8]
    new_filename = f"original_replaced_{timestamp}_{unique}.jpg"

    loop = asyncio.get_running_loop()
    thread_pool = ThreadPoolExecutor(max_workers=3)

    def delete_old():
        try:
            delete_from_s3(photo.filename)
        except Exception as e:
            print(f"[WARN] Failed to delete old S3 photo ({photo.filename}): {e}")

    def upload_new():
        try:
            file_bytes = file.file.read()
            if not file_bytes:
                raise ValueError("Empty upload detected.")

            class TempUploadFile:
                def __init__(self, data):
                    self.file = io.BytesIO(data)
                    self.content_type = file.content_type or "image/jpeg"

            return upload_to_s3(TempUploadFile(file_bytes), new_filename)
        except Exception as e:
            raise RuntimeError(f"S3 upload failed for new photo: {e}")

    delete_task = loop.run_in_executor(thread_pool, delete_old)
    upload_task = loop.run_in_executor(thread_pool, upload_new)

    new_url = await upload_task
    await delete_task

    try:
        photo.filename = new_filename
        photo.photo_url = new_url
        photo.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(photo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database update failed: {e}")

    return {
        "success": True,
        "message": "Original photo replaced successfully.",
        "data": {
            "photo_id": photo.id,
            "photo_url": photo.photo_url,
            "filename": photo.filename,
            "updated_at": photo.updated_at,
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
    # existing_user = db.query(User).filter(User.email == payload.email).first()
    # if existing_user:
    #     raise HTTPException(status_code=400, detail="Email already exists.")

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

@router.post("/submit-processed-photos/{user_id}")
async def submit_processed_photos(
    user_id: int,
    request: fastapi.Request,
    db: Session = Depends(get_db),
):
    try:
        body = await request.json()
        photo_ids = body.get("photo_ids")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    if not photo_ids or not isinstance(photo_ids, list) or len(photo_ids) == 0:
        raise HTTPException(status_code=400, detail="photo_ids must be a non-empty list.")
    if len(photo_ids) > 30:
        raise HTTPException(status_code=400, detail="You can submit up to 30 photos only.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    process_photos_task.delay(user_id, photo_ids)

    return {
        "success": True,
        "message": "Your photos are being processed in the background. You’ll be notified once it’s done.",
    }

    