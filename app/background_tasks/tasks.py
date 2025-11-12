from .celery_app import celery_app
from app.services.s3_service import upload_to_s3
from app.models import User
from app.database.connection import SessionLocal
import os, io
from datetime import datetime, timezone
from uuid import uuid4
from app.services.email_service import send_email

# @celery_app.task(name="upload_original_photos_task")
@celery_app.task(name="upload_original_photos_task", queue="photo_queue")
def upload_original_photos_task(user_id, temp_dir, file_names):
    db = SessionLocal()
    from app.models.original_photo import OriginalPhoto
    try:
        photos = []
        for fname in file_names:
            with open(os.path.join(temp_dir, fname), "rb") as f:
                class TempUploadFile:
                    def __init__(self, buffer_io):
                        self.file = io.BytesIO(buffer_io)
                        self.content_type = "image/jpeg"

                buffer_io = f.read()
                timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
                unique = uuid4().hex[:8]
                filename = f"original_{user_id}_{timestamp}_{unique}.jpg"
                s3_url = upload_to_s3(TempUploadFile(buffer_io), filename)
                photos.append(OriginalPhoto(user_id=user_id, filename=filename, photo_url=s3_url))
        db.add_all(photos)
        db.commit()
        from app.background_tasks.tasks import send_photos_submission_email
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            send_photos_submission_email.delay(user_email=user.email, user_name=user.first_name)
    finally:
        db.close()
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

# @celery_app.task(name="process_photos_task")
@celery_app.task(name="process_photos_task", queue="photo_queue")
def process_photos_task(user_id, photo_ids):
    from app.database.connection import SessionLocal
    from app.models.original_photo import OriginalPhoto
    from app.models.photo import Photo
    from app.services.bg_removal import remove_background
    from app.services.fill_black_bg import fill_black_background
    from app.services.face_detection import detect_faces
    from app.services.s3_service import upload_to_s3, s3, BUCKET_NAME
    import requests, io
    from datetime import datetime
    from uuid import uuid4

    db = SessionLocal()
    try:
        originals = db.query(OriginalPhoto).filter(
            OriginalPhoto.user_id == user_id,
            OriginalPhoto.id.in_(photo_ids)
        ).all()

        for orig in originals:
            presigned = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": BUCKET_NAME, "Key": orig.filename},
                ExpiresIn=300,
            )
            img_bytes = requests.get(presigned, timeout=20).content
            processed = detect_faces(fill_black_background(remove_background(img_bytes)))

            class TempUploadFile:
                def __init__(self, buf):
                    self.file = io.BytesIO(buf)
                    self.content_type = "image/jpeg"

            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
            user = db.query(User).filter(User.id == user_id).first()
            filename = f"{user.last_name.lower()}_{user.first_name.lower()}_{timestamp}.jpg"
            s3_url = upload_to_s3(TempUploadFile(processed), filename)
            photo = Photo(user_id=user_id, filename=filename, photo_url=s3_url)
            db.add(photo)

        db.commit()
        from app.background_tasks.tasks import send_photos_submission_email
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            send_photos_submission_email.delay(user_email=user.email, user_name=user.first_name)
    finally:
        db.close()

# @celery_app.task(name="create_video_for_user_task")        
@celery_app.task(name="create_video_for_user_task", queue="video_queue")
def create_video_for_user_task(photo_ids):
    from app.database.connection import SessionLocal
    from app.models.photo import Photo
    from app.models.video import Video
    from app.models.user import User
    from app.services.video_creation import create_video_from_images
    from app.services.s3_service import upload_to_s3, s3, BUCKET_NAME
    from app.background_tasks.tasks import send_video_ready_email
    import tempfile, os, uuid, shutil, requests

    db = SessionLocal()
    try:
        photos = db.query(Photo).filter(Photo.id.in_(photo_ids)).all()
        if not photos:
            return "No valid photos found"

        user_id = photos[0].user_id
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return "User not found"

        temp_dir = tempfile.mkdtemp(prefix="video_photos_")
        local_paths = []
        for photo in photos:
            download_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": BUCKET_NAME, "Key": photo.filename},
                ExpiresIn=300,
            )
            resp = requests.get(download_url, stream=True, timeout=20)
            resp.raise_for_status()
            file_path = os.path.join(temp_dir, os.path.basename(photo.filename))
            with open(file_path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            local_paths.append(file_path)

        video_path = create_video_from_images(local_paths)
        s3_filename = f"videos/{uuid.uuid4().hex}_final_video.mp4"
        with open(video_path, "rb") as vf:
            s3_url = upload_to_s3(vf, s3_filename)

        new_video = Video(user_id=user.id, video_url=s3_url, filename=s3_filename)
        db.add(new_video)
        db.commit()
        

        send_video_ready_email.delay(
            user_email=user.email,
            user_name=f"{user.first_name}",
            video_link=s3_url
        )

    finally:
        db.close()
        shutil.rmtree(temp_dir, ignore_errors=True)
        if 'video_path' in locals() and os.path.exists(video_path):
            os.remove(video_path)

# @celery_app.task(name="send_photos_submission_email")
@celery_app.task(name="send_photos_submission_email", queue="email_queue")
def send_photos_submission_email(user_email, user_name):
    subject = "Your photos have been submitted!"
    body = f"Hi {user_name},\n\nYour photos have been submitted successfully. We will notify you once your video is ready.\n\nThank you!"
    send_email(user_email, subject, body)

# @celery_app.task(name="send_video_ready_email")
@celery_app.task(name="send_video_ready_email", queue="email_queue")
def send_video_ready_email(user_email, user_name, video_link):
    subject = "Your video is ready!"
    body = f"Hi {user_name},\n\nYour video has been created successfully. You can watch it here:\n{video_link}\n\nThank you!"
    send_email(user_email, subject, body)

