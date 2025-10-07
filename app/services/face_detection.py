# app/services/face_detection.py
import cv2
import numpy as np

def detect_faces(image_bytes: bytes) -> bytes:
    """
    Detects faces in an image using OpenCV Haar cascade.
    Draws bounding boxes around detected faces and returns processed image bytes (JPEG).
    """
    # Load image from bytes
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Load OpenCV's built-in face detector
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    # Convert to grayscale for detection
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Detect faces
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

    # Draw bounding boxes
    for (x, y, w, h) in faces:
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)

    # Encode back to JPEG bytes
    _, processed_bytes = cv2.imencode(".jpg", img)
    return processed_bytes.tobytes()
