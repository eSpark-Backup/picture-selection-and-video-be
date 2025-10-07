import os
import cv2
import mediapipe as mp
import numpy as np
from moviepy.editor import VideoClip, concatenate_videoclips

OUTPUT_VIDEO = "processed_video.mp4"
DURATION_PER_IMAGE = 5  # seconds per image
FRAME_SIZE = (1280, 720)

mp_face = mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)


def detect_face_center(image_path):
    """Return (cx, cy) of face center; fallback to image center if not found."""
    image = cv2.imread(image_path)
    if image is None:
        return None
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = mp_face.process(rgb)
    h, w, _ = image.shape
    if not results.detections:
        return (w // 2, h // 2)
    det = results.detections[0].location_data.relative_bounding_box
    cx = int((det.xmin + det.width / 2) * w)
    cy = int((det.ymin + det.height / 2) * h)
    return (cx, cy)


def resize_image(image, max_size=FRAME_SIZE):
    """Resize image to fit within max_size while keeping aspect ratio."""
    h, w = image.shape[:2]
    max_w, max_h = max_size
    scale = min(max_w / w, max_h / h, 1.0)
    new_w, new_h = int(w * scale), int(h * scale)
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


def create_face_safe_diagonal_clip(image_path, duration=DURATION_PER_IMAGE):
    """Creates smooth diagonal motion keeping face safely inside a red circle."""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Cannot load image: {image_path}")

    img = resize_image(img)
    h, w, _ = img.shape
    face_center = detect_face_center(image_path)
    if face_center is None:
        face_center = (w // 2, h // 2)

    cx, cy = face_center

    # Circle setup
    circle_center = (FRAME_SIZE[0] // 2, FRAME_SIZE[1] // 2)
    circle_radius = int(min(FRAME_SIZE) * 0.45)
    circle_stroke = 10

    # Motion range
    move_x = min(w * 0.08, 80)
    move_y = min(h * 0.08, 80)

    def make_frame(t):
        progress = np.sin(2 * np.pi * (t / duration))
        dx = int(move_x * progress)
        dy = int(move_y * progress)

        # Target placement so the face stays near circle center
        target_x = circle_center[0] - cx + dx
        target_y = circle_center[1] - cy + dy

        # Black background
        frame = np.zeros((FRAME_SIZE[1], FRAME_SIZE[0], 3), dtype=np.uint8)

        # Compute safe coordinates
        x1 = max(target_x, 0)
        y1 = max(target_y, 0)
        x2 = min(target_x + w, FRAME_SIZE[0])
        y2 = min(target_y + h, FRAME_SIZE[1])

        img_x1 = max(0, -target_x)
        img_y1 = max(0, -target_y)
        img_x2 = img_x1 + (x2 - x1)
        img_y2 = img_y1 + (y2 - y1)

        # Only draw if the region is valid
        if (x2 > x1) and (y2 > y1) and (img_x2 > img_x1) and (img_y2 > img_y1):
            frame[y1:y2, x1:x2] = img[img_y1:img_y2, img_x1:img_x2]

        # Draw the red circle (larger, thicker)
        cv2.circle(frame, circle_center, circle_radius, (0, 0, 255), circle_stroke)

        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    return VideoClip(make_frame, duration=duration)


def create_video_from_images(image_paths):
    """Combine all clips into one video with safe diagonal motion."""
    clips = [create_face_safe_diagonal_clip(p) for p in image_paths]
    final = concatenate_videoclips(clips, method="compose")
    final.write_videofile(OUTPUT_VIDEO, fps=24, codec="libx264", audio=False)
    return os.path.abspath(OUTPUT_VIDEO)
