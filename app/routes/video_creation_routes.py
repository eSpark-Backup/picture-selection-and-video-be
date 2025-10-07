# app/routes/video_creation_routes.py
from fastapi import APIRouter, UploadFile, File
from typing import List
import os
import uuid

from app.services.video_creation import create_video_from_images

router = APIRouter(
    prefix="/api/v1",
    tags=["Video Creation"]
)

@router.post("/create-video")
async def create_video_route(files: List[UploadFile] = File(...)):
    """
    Accepts up to 30 processed (black-background + face-detected) images,
    creates a video with diagonal face-safe motion, and returns the video path.
    """
    os.makedirs("processed", exist_ok=True)
    image_paths = []

    for file in files:
        filename = f"{uuid.uuid4().hex}_{file.filename}"
        file_path = os.path.join("processed", filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        image_paths.append(file_path)

    video_path = create_video_from_images(image_paths)
    return {"video_path": video_path}
