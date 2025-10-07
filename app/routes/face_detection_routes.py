# app/routes/face_detection_routes.py
from fastapi import APIRouter, UploadFile, File
from typing import List
import os
import uuid
import io
from PIL import Image
from app.services.face_detection import detect_faces

router = APIRouter(
    prefix="/api/v1",
    tags=["Face Detection"]
)

@router.post("/detect-faces")
async def detect_faces_route(files: List[UploadFile] = File(...)):
    """
    Accepts one or more images (ideally black-background ones),
    detects faces, draws bounding boxes, saves in /processed, and returns paths.
    """
    os.makedirs("processed", exist_ok=True)
    saved_paths = []

    for file in files:
        contents = await file.read()
        processed_bytes = detect_faces(contents)
        processed_image = Image.open(io.BytesIO(processed_bytes))

        filename_no_ext = os.path.splitext(file.filename)[0]
        output_filename = f"{filename_no_ext}_faces_{uuid.uuid4().hex}.jpg"
        output_path = os.path.join("processed", output_filename)

        processed_image.save(output_path, format="JPEG")
        saved_paths.append(output_path)

    return {"paths": saved_paths}
