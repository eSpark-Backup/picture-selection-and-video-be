import os
import cv2
import numpy as np
from moviepy.editor import VideoClip, concatenate_videoclips
from concurrent.futures import ThreadPoolExecutor

OUTPUT_VIDEO = "processed_video.mp4"
DURATION_PER_IMAGE = 5
MAX_RESOLUTION = (1280, 720)
FPS = 30

MOVE_FRACTION_X = 0.1
MOVE_FRACTION_Y = 0.1
MAX_MOVE_PIXELS = 70
SAFETY_MARGIN = 8
MAX_WORK_RESOLUTION = (1920, 1080)

def _create_face_detector():
    import mediapipe as mp
    return mp.solutions.face_detection.FaceDetection(
        model_selection=1,
        min_detection_confidence=0.5
    )


def detect_face_center_in_bgr(image_bgr):
    if image_bgr is None:
        return None
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    with _create_face_detector() as face_detector:
        results = face_detector.process(rgb)
    if not results.detections:
        return None
    bbox = results.detections[0].location_data.relative_bounding_box
    h, w, _ = image_bgr.shape
    return int((bbox.xmin + bbox.width / 2) * w), int((bbox.ymin + bbox.height / 2) * h)

def resize_image(image, max_size=MAX_RESOLUTION):
    h, w = image.shape[:2]
    max_w, max_h = max_size
    scale = min(max_w / w, max_h / h, 1.0)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((max_h, max_w, 3), dtype=np.uint8)
    x_offset = (max_w - new_w) // 2
    y_offset = (max_h - new_h) // 2
    canvas[y_offset:y_offset + new_h, x_offset:x_offset + new_w] = resized
    return canvas


def _smooth_progress(p):
    return 0.5 - 0.5 * np.cos(np.pi * np.clip(p, 0.0, 1.0))


def _compute_alpha_cap(face_pt, center_pt, D_vec, radius_safe):
    v = np.array([face_pt[0] - center_pt[0], face_pt[1] - center_pt[1]], float)
    if np.hypot(*v) > radius_safe:
        return 0.0
    norm_D = np.hypot(*D_vec)
    if norm_D == 0:
        return 1.0
    for alpha in np.linspace(1.0, 0.0, 80):
        pos = v + alpha * D_vec
        if np.hypot(*pos) <= radius_safe:
            return float(alpha)
    return 0.0


def generate_clip_data(image_path, direction):
    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        raise ValueError(f"Cannot load {image_path}")

    img_bgr = resize_image(img_bgr)
    h, w, _ = img_bgr.shape

    with _create_face_detector() as face_detector:
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        results = face_detector.process(rgb)

    frame_center = np.array([w // 2, h // 2], float)
    radius = int(min(w, h) * 0.48)
    radius_safe = radius - 12

    # ---------------- FACE DETECTION ----------------
    if results.detections:
        det = results.detections[0]
        bbox = det.location_data.relative_bounding_box

        face_w = bbox.width * w
        face_h = bbox.height * h
        face_size = max(face_w, face_h)

        # ---------------- FACE FIT FIX ----------------
        circle_diam = 2 * radius

        # top/head safe — 50%
        scale_y = (circle_diam * 0.50) / face_h

        # left-right safe — 65%
        scale_x = (circle_diam * 0.65) / face_w

        # final scale so NOTHING cuts
        scale_factor = min(scale_x, scale_y)

        # clamp
        scale_factor = float(np.clip(scale_factor, 0.55, 1.40))

    else:
        # No face detected, scale whole image
        scale_factor = (2 * radius) / min(w, h)
        scale_factor = float(np.clip(scale_factor, 0.55, 1.40))

    # ---------------- APPLY ZOOM ----------------
    M_zoom = cv2.getRotationMatrix2D(tuple(frame_center), 0, scale_factor)
    img_bgr = cv2.warpAffine(
        img_bgr, M_zoom, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0)
    )

    # ---------------- UPDATE FACE CENTER ----------------
    face_center = np.array([
        (bbox.xmin + bbox.width / 2) * w,
        (bbox.ymin + bbox.height / 2) * h
    ]) if results.detections else frame_center.copy()

    face_center = (face_center - frame_center) * scale_factor + frame_center

    # ---------------- CENTER FACE IN CIRCLE ----------------
    shift_vec = frame_center - face_center
    shift_norm = np.linalg.norm(shift_vec)
    max_shift = radius_safe * 0.80

    if shift_norm > max_shift:
        shift_vec = shift_vec / shift_norm * max_shift

    M_shift = np.float32([[1, 0, shift_vec[0]], [0, 1, shift_vec[1]]])
    img_bgr = cv2.warpAffine(img_bgr, M_shift, (w, h),
                             flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_CONSTANT,
                             borderValue=(0, 0, 0))

    # ---------------- FINAL MOVEMENT ----------------
    move_px = min(radius_safe * 0.15, 40)
    D_vec = np.array([direction * move_px, direction * move_px], float)

    # ---------------- OUTPUT ----------------
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
    return img_rgb, w, h, tuple(frame_center.astype(int)), radius, 8, D_vec

def _process_clip_args(params):
    path, direction = params
    return generate_clip_data(path, direction)


def make_motion_clip(args):
    img_rgb, w, h, frame_center, radius, thickness, D_vec = args

    def make_frame(t):
        progress = _smooth_progress(t / DURATION_PER_IMAGE)
        dx, dy = D_vec * progress
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        shifted = cv2.warpAffine(
            img_rgb, M, (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0.0, 0.0, 0.0)
        )
        frame_bgr = cv2.cvtColor(np.clip(shifted, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
        cv2.circle(frame_bgr, frame_center, radius, (0, 0, 255), thickness, lineType=cv2.LINE_AA)
        return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    return VideoClip(make_frame, duration=DURATION_PER_IMAGE)


def create_video_from_images(image_paths):
    if not image_paths:
        raise ValueError("No image paths provided")

    args_list = [(path, 1 if i % 2 == 0 else -1) for i, path in enumerate(image_paths)]

    with ThreadPoolExecutor() as executor:
        processed_data = list(executor.map(_process_clip_args, args_list))

    clips = [make_motion_clip(data) for data in processed_data]
    final_clip = concatenate_videoclips(clips, method="compose")
    final_clip.write_videofile(OUTPUT_VIDEO, fps=FPS, codec="libx264", audio=False, threads=4)
    return os.path.abspath(OUTPUT_VIDEO)


if __name__ == "__main__":
    test_images = []
    if test_images:
        print("Rendering:", create_video_from_images(test_images))
    else:
        print("No sample images provided.")
