# app/services/face_detection.py
import cv2
import numpy as np

def detect_faces(image_bytes: bytes) -> bytes:
    """
    Detects faces in an image using OpenCV Haar cascade.
    Optimized with resizing, efficiency tweaks, and optional GPU acceleration.
    Draws bounding boxes and returns processed JPEG bytes.
    """
    import cv2, numpy as np, io, logging

    logger = logging.getLogger("image_processor")

    try:
        # Decode image from bytes
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Invalid image data")

        # Step 2: Resize for faster detection while preserving aspect ratio
        max_width = 1024
        if img.shape[1] > max_width:
            scale = max_width / img.shape[1]
            img = cv2.resize(img, (max_width, int(img.shape[0] * scale)), interpolation=cv2.INTER_AREA)

        # Convert to grayscale for detection
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Step 6: Optional GPU acceleration (CUDA Haar Cascade if available)
        use_gpu = False
        try:
            if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                gpu_gray = cv2.cuda_GpuMat()
                gpu_gray.upload(gray)
                cascade = cv2.cuda_CascadeClassifier.create(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
                faces_gpu = cascade.detectMultiScale(gpu_gray)
                faces = faces_gpu.download() if faces_gpu is not None else []
                use_gpu = True
                logger.info("GPU acceleration used for face detection.")
            else:
                faces = None
        except Exception:
            faces = None

        # Step 5: CPU fallback and detection optimization
        if faces is None or len(faces) == 0:
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30))

        # Draw bounding boxes
        for (x, y, w, h) in faces:
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)

        # Encode back to JPEG bytes (optimized)
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
        success, encoded_img = cv2.imencode(".jpg", img, encode_params)
        if not success:
            raise RuntimeError("Failed to encode processed image")

        logger.info(f"Face detection completed successfully (GPU={use_gpu}, faces={len(faces)}).")
        return encoded_img.tobytes()

    except Exception as e:
        logger.error(f"Face detection failed: {e}")
        raise RuntimeError(f"Face detection failed: {e}")
