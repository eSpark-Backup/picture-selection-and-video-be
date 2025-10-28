import os
import cv2
import numpy as np
from moviepy.editor import VideoClip, concatenate_videoclips
import mediapipe as mp

OUTPUT_VIDEO = "processed_video.mp4"
DURATION_PER_IMAGE = 5
MAX_RESOLUTION = (1280, 720)
FPS = 45

# Tune these to control motion amount and limits
MOVE_FRACTION_X = 0.08
MOVE_FRACTION_Y = 0.08
MAX_MOVE_PIXELS = 70
SAFETY_MARGIN = 8  # pixels inside the circle to keep the face comfortably inside

mp_face = mp.solutions.face_detection.FaceDetection(
    model_selection=1, min_detection_confidence=0.5
)


def detect_face_center_in_bgr(image_bgr):
    """Detect face center on a BGR image and return (x, y) in image coordinates (ints)."""
    if image_bgr is None:
        return None
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    results = mp_face.process(rgb)
    if not results.detections:
        return None
    bbox = results.detections[0].location_data.relative_bounding_box
    h, w, _ = image_bgr.shape
    cx = int((bbox.xmin + bbox.width / 2) * w)
    cy = int((bbox.ymin + bbox.height / 2) * h)
    return cx, cy


def resize_image(image, max_size=MAX_RESOLUTION):
    h, w = image.shape[:2]
    max_w, max_h = max_size
    scale = min(max_w / w, max_h / h, 1.0)
    new_w, new_h = int(w * scale * 0.7), int(h * scale * 0.7)
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

    canvas = np.zeros((max_h, max_w, 3), dtype=np.uint8)
    x_offset = (max_w - new_w) // 2
    y_offset = (max_h - new_h) // 2
    canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
    return canvas



def _smooth_progress(progress):
    """Ease-in-out cosine (progress in [0,1])."""
    progress = float(np.clip(progress, 0.0, 1.0))
    return 0.5 - 0.5 * np.cos(np.pi * progress)


def _compute_alpha_cap(face_pt, center_pt, D_vec, radius_safe):
    """
    Numerically compute max alpha in [0,1] such that for alpha*D_vec added to (face - center),
    the resulting distance <= radius_safe. Returns a scalar in [0,1].
    This is a robust fallback vs solving the quadratic and handles edge cases easily.
    """
    v = np.array([face_pt[0] - center_pt[0], face_pt[1] - center_pt[1]], dtype=float)
    # If already outside safe radius, we won't attempt to force it in here.
    if np.hypot(v[0], v[1]) > radius_safe:
        return 0.0

    # If desired move is zero, keep alpha = 1 (no need to scale).
    norm_D = np.hypot(D_vec[0], D_vec[1])
    if norm_D == 0:
        return 1.0

    # Sample alpha from 1.0 down to 0.0 to find the largest alpha that keeps face in circle.
    for alpha in np.linspace(1.0, 0.0, 201):
        pos = v + alpha * D_vec
        if np.hypot(pos[0], pos[1]) <= radius_safe:
            return float(alpha)
    return 0.0


def create_diagonal_motion_clip(image_path, duration=DURATION_PER_IMAGE, direction=1):
    """
    Create a face-safe, ultra-smooth diagonal-motion clip for one image.
    Ensures the detected face remains within the red circle at all times.
    """
    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        raise ValueError(f"Unable to load image: {image_path}")

    # Resize first (face detection will run on this resized image)
    img_bgr = resize_image(img_bgr)
    h, w, _ = img_bgr.shape

    # Precompute detection on resized image (aligns coords with frames)
    face_center = detect_face_center_in_bgr(img_bgr)
    frame_center = (w // 2, h // 2)

    # Circle parameters (radius & thickness scale with image size)
    radius = int(min(w, h) * 0.48)
    thickness = max(2, int(min(w, h) * 0.03))  # adaptive thickness
    # Safe radius inside which the face must remain
    radius_safe = max(0, radius - SAFETY_MARGIN - max(1, thickness // 2))

    # Movement target (desired D vector at progress=1)
    move_x = min(float(w * MOVE_FRACTION_X), float(MAX_MOVE_PIXELS))
    move_y = min(float(h * MOVE_FRACTION_Y), float(MAX_MOVE_PIXELS))
    D_vec = np.array([direction * move_x, direction * move_y], dtype=float)

    # If no face detected, use center (face will trivially stay inside)
    if face_center is None:
        face_pt = frame_center
    else:
        face_pt = face_center

    # Compute alpha cap so final moved face remains inside circle
    alpha_cap = _compute_alpha_cap(face_pt, frame_center, D_vec, radius_safe)
    # If alpha_cap == 0 and face was outside safe circle initially, we keep zero movement.
    D_vec = D_vec * alpha_cap

    # Convert the image to RGB float32 (MoviePy expects RGB frames)
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)

    def make_frame(t):
        # smooth progress 0..1
        progress = _smooth_progress(t / duration)
        dx = float(D_vec[0] * progress)
        dy = float(D_vec[1] * progress)

        # Subpixel translation using float precision; use black fill for edges (no reflection).
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        shifted = cv2.warpAffine(
            img_rgb,
            M,
            (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0.0, 0.0, 0.0),
        )

        # Convert to uint8 RGB for drawing
        frame_rgb = np.clip(shifted, 0, 255).astype(np.uint8)

        # cv2 drawing expects BGR color ordering, so convert to BGR, draw, then convert back
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        cv2.circle(frame_bgr, frame_center, radius, (0, 0, 255), thickness, lineType=cv2.LINE_AA)  # red in BGR

        # Back to RGB for MoviePy
        final_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        return final_frame

    return VideoClip(make_frame, duration=duration)


def create_video_from_images(image_paths):
    clips = []
    for i, path in enumerate(image_paths):
        direction = 1 if i % 2 == 0 else -1
        clips.append(create_diagonal_motion_clip(path, duration=DURATION_PER_IMAGE, direction=direction))
    final_clip = concatenate_videoclips(clips, method="compose")
    final_clip.write_videofile(OUTPUT_VIDEO, fps=FPS, codec="libx264", audio=False, threads=4)
    return os.path.abspath(OUTPUT_VIDEO)


if __name__ == "__main__":
    # quick local test (provide a list of image paths)
    sample_images = [
        # "path/to/image1.jpg",
        # "path/to/image2.jpg",
    ]
    if sample_images:
        print("Rendering:", create_video_from_images(sample_images))
    else:
        print("No sample images provided. Import this module and call create_video_from_images([...]).")
