import cv2
import mediapipe as mp
import numpy as np
import os
import sys
from moviepy import VideoFileClip
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

MODEL_PATH = "selfie_multiclass_256x256.tflite"
INPUT_VIDEO = r"C:\Users\gssjr\OneDrive\Desktop\FILES\VIDEOS\TRY\20260420131942921.mp4"
OUTPUT_VIDEO = r"C:\Users\gssjr\OneDrive\Desktop\FILES\VIDEOS\TRY\golden_blonde_hair.mp4"
TARGET_COLOR_BGR = (88, 163, 197) 
STRENGTH = 0.45 

def change_hair_color(frame, hair_mask, target_color_bgr, strength):
    overlay = np.zeros_like(frame)
    overlay[:] = target_color_bgr
    hair_mask = cv2.GaussianBlur(hair_mask, (7, 7), 0)
    mask_3d = cv2.merge([hair_mask, hair_mask, hair_mask])
    frame_float = frame.astype(np.float32)
    overlay_float = overlay.astype(np.float32)
    tinted = (frame_float * (1 - strength) + overlay_float * strength).clip(0, 255).astype(np.uint8)
    return np.where(mask_3d > 0.5, tinted, frame)

def process_video():
    print("--- 1. INITIALIZING AI ---")
    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.ImageSegmenterOptions(base_options=base_options, output_category_mask=True)
    segmenter = vision.ImageSegmenter.create_from_options(options)

    print("--- 2. LOADING VIDEO ---")
    clip = VideoFileClip(INPUT_VIDEO)
    
    def process_frame(frame):
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
        result = segmenter.segment(mp_image)
        # Fix: used .numpy_view() instead of .get_numpy_view()
        category_mask = result.category_mask.numpy_view()
        hair_mask = (category_mask == 1).astype(np.float32)
        return change_hair_color(frame, hair_mask, TARGET_COLOR_BGR, STRENGTH)

    print("--- 3. RUNNING TRANSFORMATION ---")
    new_clip = clip.image_transform(process_frame)
    new_clip.write_videofile(OUTPUT_VIDEO, audio=True, codec='libx264', fps=clip.fps, logger='bar')
    print(f"--- SUCCESS! Saved to {OUTPUT_VIDEO} ---")

if __name__ == '__main__':
    process_video()
