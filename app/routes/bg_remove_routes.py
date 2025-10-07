# app/routes/bg_remove_routes.py
from fastapi import APIRouter, UploadFile, File
from typing import List
from PIL import Image
import io
import uuid
import os

from app.services.bg_removal import remove_background

router = APIRouter(
    prefix="/api/v1",
    tags=["Background Removal"]
)

@router.post("/remove-background")
async def remove_background_route(files: List[UploadFile] = File(...)):
    """
    Accepts one or more image files, removes their backgrounds,
    saves the processed images in the 'processed' directory,
    and returns their saved paths.
    """
    processed_dir = os.path.join(os.getcwd(), "processed")
    os.makedirs(processed_dir, exist_ok=True)

    saved_paths = []

    for file in files:
        # Read uploaded file bytes
        contents = await file.read()

        # Process image background
        processed_image_bytes = remove_background(contents)

        # Convert bytes to PIL Image
        processed_image = Image.open(io.BytesIO(processed_image_bytes))

        # Save as PNG to preserve transparency
        filename_no_ext = os.path.splitext(file.filename)[0]
        output_filename = f"{filename_no_ext}_{uuid.uuid4().hex}.png"
        output_path = os.path.join(processed_dir, output_filename)

        processed_image.save(output_path, format="PNG")
        saved_paths.append(output_path)

    return {"paths": saved_paths}
