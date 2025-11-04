from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
import fastapi
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
    import asyncio
    from datetime import datetime
    from app.models.original_photo import OriginalPhoto
    from app.services.s3_service import upload_to_s3

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail="No files provided.")

    if len(files) > 30:
        raise HTTPException(status_code=400, detail="You can upload up to 30 photos only.")

    uploaded_photos = []

    async def process_and_upload(file: UploadFile):
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
            filename = f"original_{user.last_name}_{user.first_name}_{timestamp}.jpg"
            s3_url = await asyncio.to_thread(upload_to_s3, file, filename)
            return {"filename": filename, "s3_url": s3_url}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Upload failed for {file.filename}: {e}")

    # Step 1: Upload all images concurrently
    upload_results = await asyncio.gather(*[process_and_upload(file) for file in files])

    # Step 2: Insert all DB records in batch
    photo_objects = [
        OriginalPhoto(user_id=user.id, filename=res["filename"], photo_url=res["s3_url"])
        for res in upload_results
    ]
    db.add_all(photo_objects)
    db.commit()
    db.refresh(user)

    # Step 3: Prepare response
    for photo in photo_objects:
        uploaded_photos.append(
            {"photo_id": photo.id, "filename": photo.filename, "photo_url": photo.photo_url}
        )

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

@router.post("/submit-processed-photos/{user_id}")
async def submit_processed_photos(
    user_id: int,
    request: fastapi.Request,
    db: Session = Depends(get_db),
):
    """
    Highly optimized processing pipeline:
      - Validates inputs and limits (max 30)
      - Downloads originals using S3 presigned URLs concurrently (bounded)
      - Runs CPU/IO-heavy image processing in worker threads (asyncio.to_thread) to avoid blocking the event loop
      - Uploads processed images to S3 concurrently (again using worker threads)
      - Performs all DB writes in the main thread in a single batch (db.add_all + commit)
    Notes:
      - We keep DB operations out of worker threads for session safety.
      - Concurrency is bounded with a semaphore to avoid memory/CPU spikes.
    """
    import io
    import json
    import asyncio
    import requests
    from datetime import datetime
    from uuid import uuid4
    from PIL import Image
    from concurrent.futures import ThreadPoolExecutor
    from app.models.user import User
    from app.models.original_photo import OriginalPhoto
    from app.models.photo import Photo
    from app.services.s3_service import s3, upload_to_s3, BUCKET_NAME

    # Validate user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Parse body
    try:
        body = await request.json()
        photo_ids = body.get("photo_ids")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    if not photo_ids or not isinstance(photo_ids, list) or len(photo_ids) == 0:
        raise HTTPException(status_code=400, detail="photo_ids must be a non-empty list.")

    if len(photo_ids) > 30:
        raise HTTPException(status_code=400, detail="You can submit up to 30 photos only.")

    # Fetch originals (DB access kept synchronous here)
    originals = (
        db.query(OriginalPhoto)
        .filter(OriginalPhoto.id.in_(photo_ids), OriginalPhoto.user_id == user_id)
        .all()
    )
    if not originals:
        raise HTTPException(status_code=404, detail="No matching original photos found.")

    # Bound concurrency to avoid OOM / oversubscription
    cpu_count = (os.cpu_count() or 2)
    # Use a modest multiple for IO+CPU mix; tune as needed.
    max_concurrency = min(8, cpu_count * 2)
    semaphore = asyncio.Semaphore(max_concurrency)

    # Shared thread pool for blocking operations (downloads, processing, uploads)
    thread_pool = ThreadPoolExecutor(max_workers=max_concurrency)

    # Local helper that performs the processing pipeline in worker threads only.
    # It will be executed via asyncio.to_thread (so no pickling concerns).
    def process_image_pipeline_get_upload_result(original):
        """
        Runs in a worker thread:
          - Gets presigned URL and downloads image (requests)
          - Runs background removal -> fill_black_background -> face_detection
          - Converts to JPEG bytes
          - Returns (filename, s3_url)
        """
        try:
            # 1) presigned url (boto3 sync)
            presigned_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": BUCKET_NAME, "Key": original.filename},
                ExpiresIn=300,
            )

            # 2) download (requests sync)
            resp = requests.get(presigned_url, stream=True, timeout=20)
            resp.raise_for_status()
            image_bytes = resp.content

            # 3) processing chain (these are sync functions in services)
            # Import inside function to avoid overhead unless used
            from app.services.bg_removal import remove_background
            from app.services.fill_black_bg import fill_black_background
            from app.services.face_detection import detect_faces

            # Apply CPU/IO ops in sequence
            processed_bytes = detect_faces(fill_black_background(remove_background(image_bytes)))

            # Ensure PIL can read it and convert to standard JPEG bytes
            processed_image = Image.open(io.BytesIO(processed_bytes)).convert("RGB")
            out_buffer = io.BytesIO()
            processed_image.save(out_buffer, format="JPEG", quality=95, optimize=True)
            out_buffer.seek(0)

            # 4) create unique filename
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
            unique = uuid4().hex[:8]
            filename = f"{user.last_name}_{user.first_name}_{timestamp}_{unique}.jpg"

            # 5) wrapper for upload_to_s3 expects UploadFile-like; keep minimal wrapper
            class TempUploadFile:
                def __init__(self, buffer_io):
                    self.file = buffer_io
                    self.content_type = "image/jpeg"

            # 6) upload to S3 (sync)
            s3_url = upload_to_s3(TempUploadFile(out_buffer), filename)

            return {"filename": filename, "s3_url": s3_url}

        except Exception as e:
            # raise here so the thread exception propagates back to asyncio
            raise RuntimeError(f"Processing failed for {original.filename}: {e}") from e

    # Async wrapper that enforces semaphore and runs the pipeline in the thread pool
    async def bounded_process(original):
        async with semaphore:
            # run in thread pool
            return await asyncio.get_running_loop().run_in_executor(thread_pool, process_image_pipeline_get_upload_result, original)

    # Launch all processing tasks concurrently (bounded)
    try:
        tasks = [bounded_process(orig) for orig in originals]
        results = await asyncio.gather(*tasks)  # will raise on first exception by default
    except Exception as e:
        # Provide a clear message to client
        raise HTTPException(status_code=500, detail=str(e))

    # All processing & uploads succeeded; create DB Photo objects in main thread only
    photo_objects = []
    for res in results:
        photo_objects.append(
            Photo(user_id=user.id, filename=res["filename"], photo_url=res["s3_url"])
        )

    # Bulk insert and commit once to minimize DB overhead
    try:
        db.add_all(photo_objects)
        db.commit()
        # refresh to populate ids and timestamps
        for p in photo_objects:
            db.refresh(p)
    except Exception as e:
        # If DB fails, consider cleaning up uploaded S3 objects or log for cleanup (not implemented here)
        raise HTTPException(status_code=500, detail=f"Database error while saving processed photos: {e}")

    # Prepare response
    uploaded_photos = [
        {"photo_id": p.id, "filename": p.filename, "photo_url": p.photo_url}
        for p in photo_objects
    ]

    return {
        "success": True,
        "message": "Original photos processed and uploaded successfully.",
        "uploaded_photos": uploaded_photos,
    }

