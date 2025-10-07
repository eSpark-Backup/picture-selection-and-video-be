# app/routes/fill_black_bg_routes.py
from fastapi import APIRouter, UploadFile, File
from typing import List
from PIL import Image
import io
import uuid
import os

from app.services.fill_black_bg import fill_black_background

router = APIRouter(
    prefix="/api/v1",
    tags=["Fill Black Background"]
)

@router.post("/fill-black-background")
async def fill_black_background_route(files: List[UploadFile] = File(...)):
    """
    Accepts one or more transparent PNG files, fills black background,
    saves results in /processed, and returns file paths.
    """
    os.makedirs("processed", exist_ok=True)
    saved_paths = []

    for file in files:
        contents = await file.read()
        processed_bytes = fill_black_background(contents)
        processed_image = Image.open(io.BytesIO(processed_bytes))

        filename_no_ext = os.path.splitext(file.filename)[0]
        output_filename = f"{filename_no_ext}_black_{uuid.uuid4().hex}.jpg"
        output_path = os.path.join("processed", output_filename)

        processed_image.save(output_path, format="JPEG")
        saved_paths.append(output_path)

    return {"paths": saved_paths}
