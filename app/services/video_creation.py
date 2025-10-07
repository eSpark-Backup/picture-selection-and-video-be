import os
from moviepy.editor import VideoClip, concatenate_videoclips
import cv2
import mediapipe as mp
import numpy as np

OUTPUT_VIDEO = "processed_video.mp4"
DURATION_PER_IMAGE = 5  # seconds per image
MAX_RESOLUTION = (1280, 720)  # prevent memory issues

mp_face = mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)


def detect_face_center(image_path):
    """Detect the face center coordinates in an image."""
    image = cv2.imread(image_path)
    if image is None:
        return None

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = mp_face.process(rgb)
    if not results.detections:
        return None

    detection = results.detections[0]
    bbox = detection.location_data.relative_bounding_box
    h, w, _ = image.shape
    center_x = int((bbox.xmin + bbox.width / 2) * w)
    center_y = int((bbox.ymin + bbox.height / 2) * h)
    return center_x, center_y


def resize_image(image, max_size=MAX_RESOLUTION):
    """Resize image to fit within max_size while maintaining aspect ratio."""
    h, w = image.shape[:2]
    max_w, max_h = max_size
    scale = min(max_w / w, max_h / h, 1.0)
    new_w, new_h = int(w * scale), int(h * scale)
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


def create_diagonal_motion_clip(image_path, duration=DURATION_PER_IMAGE, direction=1):
    """Creates a faster, wider diagonal motion and adds a red circle in the center."""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Unable to load image: {image_path}")

    img = resize_image(img)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w, _ = img_rgb.shape

    # Increase motion distance
    move_x = min(w * 0.05, 50)
    move_y = min(h * 0.05, 50)

    # Red circle setup
    center = (w // 2, h // 2)
    radius = int(min(w, h) * 0.5)
    color = (255, 0, 0)
    thickness = 30

    def make_frame(t):
        # Faster diagonal motion
        progress = (t / duration)
        dx = int(direction * move_x * progress)
        dy = int(direction * move_y * progress)

        # Apply translation
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        shifted = cv2.warpAffine(img_rgb, M, (w, h))

        # Draw red circle on top
        frame = shifted.copy()
        cv2.circle(frame, center, radius, color, thickness)
        return frame

    return VideoClip(make_frame, duration=duration)


def create_video_from_images(image_paths):
    """Combine images into a smooth, faster diagonal motion video with red circle."""
    clips = []
    for i, path in enumerate(image_paths):
        direction = 1 if i % 2 == 0 else -1  # alternate direction
        clips.append(create_diagonal_motion_clip(path, direction=direction))
    final_clip = concatenate_videoclips(clips, method="compose")
    final_clip.write_videofile(OUTPUT_VIDEO, fps=24, codec="libx264", audio=False)
    return os.path.abspath(OUTPUT_VIDEO)
