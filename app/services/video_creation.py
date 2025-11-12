import os
import cv2
import numpy as np
import mediapipe as mp
from moviepy.editor import VideoClip, concatenate_videoclips
from concurrent.futures import ThreadPoolExecutor

OUTPUT_VIDEO = "processed_video.mp4"
DURATION_PER_IMAGE = 5
MAX_RESOLUTION = (1280, 720)
FPS = 30

MOVE_FRACTION_X = 0.08
MOVE_FRACTION_Y = 0.08
MAX_MOVE_PIXELS = 70
SAFETY_MARGIN = 8

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
    thickness = max(2, int(min(w, h) * 0.03))
    radius_safe = radius - (SAFETY_MARGIN * 1.5)


    face_centers = []
    if results.detections:
        for det in results.detections:
            bbox = det.location_data.relative_bounding_box
            cx = (bbox.xmin + bbox.width / 2) * w
            cy = (bbox.ymin + bbox.height / 2) * h
            face_centers.append([cx, cy])
    else:
        face_centers = [frame_center.copy()]

    face_centers = np.array(face_centers, dtype=float)

    mean_face = np.mean(face_centers, axis=0)

    if face_centers.shape[0] == 1:
        max_dist = 0.0
    else:
        max_dist = float(np.max(np.linalg.norm(face_centers - mean_face, axis=1)))

    zoom_out_factor = 1.0

    containment_margin = 10.0

    if max_dist > 0:
        candidate = (radius_safe - containment_margin) / max_dist
        if candidate < 1.0:
            zoom_out_factor = float(candidate)

    min_zoom = 0.3
    zoom_out_factor = max(min_zoom, min(1.0, zoom_out_factor))

    for _ in range(8):
        new_w = max(1, int(w * zoom_out_factor))
        new_h = max(1, int(h * zoom_out_factor))
        x_off = (w - new_w) // 2
        y_off = (h - new_h) // 2

        transformed = face_centers * zoom_out_factor + np.array([x_off, y_off], dtype=float)

        dists = np.linalg.norm(transformed - frame_center, axis=1)
        max_after = float(np.max(dists))

        if max_after <= (radius_safe - containment_margin):
            break

        required_zoom = (radius_safe - containment_margin) / (max_after + 1e-6)
        zoom_out_factor = float(max(min_zoom, min(zoom_out_factor * required_zoom * 0.98, zoom_out_factor * 0.995)))

    if zoom_out_factor < 1.0:
        new_size = (max(1, int(w * zoom_out_factor)), max(1, int(h * zoom_out_factor)))
        img_small = cv2.resize(img_bgr, new_size, interpolation=cv2.INTER_AREA)
        canvas = np.zeros((h, w, 3), dtype=np.uint8)
        x_off = (w - new_size[0]) // 2
        y_off = (h - new_size[1]) // 2
        canvas[y_off:y_off + new_size[1], x_off:x_off + new_size[0]] = img_small
        img_bgr = canvas

        face_centers = face_centers * zoom_out_factor + np.array([x_off, y_off], dtype=float)
    else:
        face_centers = face_centers.astype(float)

    mean_face = np.mean(face_centers, axis=0)

    shift_vec = frame_center - mean_face
    shift_norm = np.linalg.norm(shift_vec)
    max_shift = radius_safe * 0.8
    if shift_norm > max_shift and shift_norm > 0:
        shift_vec = shift_vec / shift_norm * max_shift

    M_shift = np.float32([[1, 0, shift_vec[0]], [0, 1, shift_vec[1]]])
    img_bgr = cv2.warpAffine(img_bgr, M_shift, (w, h),
                             flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_CONSTANT,
                             borderValue=(0, 0, 0))

    face_centers = face_centers + shift_vec


    move_x = min(w * MOVE_FRACTION_X, MAX_MOVE_PIXELS)
    move_y = min(h * MOVE_FRACTION_Y, MAX_MOVE_PIXELS)
    
    max_allowed_move = radius_safe * 0.15
    move_x = min(move_x, max_allowed_move)
    move_y = min(move_y, max_allowed_move)

    
    D_vec = np.array([direction * move_x, direction * move_y], float)

    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
    return img_rgb, w, h, tuple(frame_center.astype(int)), radius, thickness, D_vec


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
