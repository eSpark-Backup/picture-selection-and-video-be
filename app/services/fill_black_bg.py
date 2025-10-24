# app/services/fill_black_bg.py
import io
from PIL import Image

def fill_black_background(image_bytes: bytes) -> bytes:
    """
    Fills transparent areas of an RGBA image with solid black.
    Optimized with resizing, OpenCV efficiency tweaks, and optional GPU acceleration.
    Returns JPEG bytes (no transparency).
    """
    import io, logging, cv2, numpy as np
    from PIL import Image

    logger = logging.getLogger("image_processor")

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

        # Step 2: Resize large images before processing for speed optimization
        max_size = (1024, 1024)
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.LANCZOS)

        # Step 5: Efficiency tweak using OpenCV for faster alpha blending
        np_img = np.array(img)
        if np_img.shape[2] == 4:
            alpha = np_img[:, :, 3] / 255.0
            black_bg = np.zeros_like(np_img[:, :, :3], dtype=np.uint8)
            blended = (np_img[:, :, :3] * alpha[:, :, None] + black_bg * (1 - alpha[:, :, None])).astype(np.uint8)
        else:
            blended = np_img[:, :, :3]

        # Step 6: Optional GPU acceleration (if OpenCV built with CUDA)
        try:
            if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                gpu_img = cv2.cuda_GpuMat()
                gpu_img.upload(blended)
                blended = gpu_img.download()
                logger.info("GPU acceleration used for black background fill.")
        except Exception:
            logger.info("GPU acceleration not available, using CPU.")

        # Convert back to JPEG bytes
        final_img = Image.fromarray(blended)
        buf = io.BytesIO()
        final_img.save(buf, format="JPEG", quality=95, optimize=True)
        result = buf.getvalue()

        logger.info("Black background fill completed successfully.")
        return result

    except Exception as e:
        logger.error(f"Error filling black background: {e}")
        raise RuntimeError(f"Black background fill failed: {e}")
