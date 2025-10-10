import os
import cv2
import numpy as np
from moviepy.editor import VideoClip, concatenate_videoclips
import mediapipe as mp

OUTPUT_VIDEO = "processed_video.mp4"
DURATION_PER_IMAGE = 5
MAX_RESOLUTION = (1280, 720)
FPS = 60

mp_face = mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)


def detect_face_center(image_path):
    image = cv2.imread(image_path)
    if image is None:
        return None
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = mp_face.process(rgb)
    if not results.detections:
        return None
    bbox = results.detections[0].location_data.relative_bounding_box
    h, w, _ = image.shape
    return int((bbox.xmin + bbox.width / 2) * w), int((bbox.ymin + bbox.height / 2) * h)


def resize_image(image, max_size=MAX_RESOLUTION):
    h, w = image.shape[:2]
    max_w, max_h = max_size
    scale = min(max_w / w, max_h / h, 1.0)
    new_w, new_h = int(w * scale), int(h * scale)
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


def create_diagonal_motion_clip(image_path, duration=DURATION_PER_IMAGE, direction=1):
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Unable to load image: {image_path}")
    img = resize_image(img)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)
    h, w, _ = img_rgb.shape

    move_x = min(w * 0.08, 50)
    move_y = min(h * 0.08, 50)
    center = (w // 2, h // 2)
    radius = int(min(w, h) * 0.48)
    color = (255, 0, 0)
    thickness = 30

    def smooth_motion(progress):
        return 0.5 - 0.5 * np.cos(np.pi * progress)  # ease-in-out cosine

    def make_frame(t):
        progress = smooth_motion(t / duration)
        dx = float(direction * move_x * progress)
        dy = float(direction * move_y * progress)

        # Smooth subpixel translation with float precision
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        shifted = cv2.warpAffine(img_rgb, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)

        frame = shifted.copy()
        cv2.circle(frame, center, radius, color, thickness)
        return np.clip(frame, 0, 255).astype(np.uint8)

    return VideoClip(make_frame, duration=duration)


def create_video_from_images(image_paths):
    clips = []
    for i, path in enumerate(image_paths):
        direction = 1 if i % 2 == 0 else -1
        clips.append(create_diagonal_motion_clip(path, direction=direction))
    final_clip = concatenate_videoclips(clips, method="compose")
    final_clip.write_videofile(OUTPUT_VIDEO, fps=FPS, codec="libx264", audio=False, threads=4)
    return os.path.abspath(OUTPUT_VIDEO)
