import os
import cv2
import numpy as np
from moviepy.editor import VideoClip, concatenate_videoclips
from concurrent.futures import ThreadPoolExecutor

OUTPUT_VIDEO = "processed_video.mp4"
DURATION_PER_IMAGE = 5
MAX_RESOLUTION = (1280, 720)
FPS = 1

MOVE_FRACTION_X = 0.1
MOVE_FRACTION_Y = 0.1
MAX_MOVE_PIXELS = 70
SAFETY_MARGIN = 8
MAX_WORK_RESOLUTION = (1920, 1080)

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


def generate_clip_data(image_path, direction):
    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        raise ValueError(f"Cannot load {image_path}")
    
    img_bgr = resize_image(img_bgr)

    h, w, _ = img_bgr.shape

    frame_center = np.array([w // 2, h // 2], float)
    radius = 350         
    thickness = 10

    scale_factor = radius * 2 / min(w, h)
    scale_factor = np.clip(scale_factor, 0.7, 2.8)

    M_zoom = cv2.getRotationMatrix2D(tuple(frame_center), 0, scale_factor)
    img_bgr = cv2.warpAffine(
        img_bgr, M_zoom, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0)
    )

    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)

    return img_rgb, w, h, tuple(frame_center.astype(int)), radius, thickness, np.array([0, 0], float)  

def make_motion_clip(args):
    img_rgb, w, h, frame_center, radius, thickness, D_vec = args

    def make_frame(t):
        frame_bgr = cv2.cvtColor(np.clip(img_rgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
        cv2.circle(frame_bgr, frame_center, radius, (0, 0, 255), thickness, lineType=cv2.LINE_AA)
        return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    return VideoClip(make_frame, duration=DURATION_PER_IMAGE)

def create_video_from_images(image_paths):
    if not image_paths:
        raise ValueError("No image paths provided")
    clips = [make_motion_clip(generate_clip_data(path, 1 if i % 2 == 0 else -1)) for i, path in enumerate(image_paths)]
    final_clip = concatenate_videoclips(clips, method="compose")
    final_clip.write_videofile(OUTPUT_VIDEO, fps=FPS, codec="libx264", audio=False, threads=4)
    return os.path.abspath(OUTPUT_VIDEO)



if __name__ == "__main__":
    test_images = []
    if test_images:
        print("Rendering:", create_video_from_images(test_images))
    else:
        print("No sample images provided.")
