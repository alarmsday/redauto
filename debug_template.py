import cv2
import numpy as np
import io
from PIL import Image
import os
import time

from device_manager.controller import get_device_controller

ctrl = get_device_controller('NABDU20330005550')

# Navigate to a post (click on first post area)
ctrl.click(300, 500)
time.sleep(3)

# Take screenshot of post detail
screenshot_bytes = ctrl.take_screenshot()
img = Image.open(io.BytesIO(screenshot_bytes))
screenshot = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
h, w = screenshot.shape[:2]
print(f"Screenshot size: {w}x{h}")

# Save full screenshot
cv2.imwrite('debug_post.png', screenshot)
print("Saved debug_post.png")

# Define ROI for like/collect buttons (bottom-right area)
roi_y1 = int(h * 0.85)
roi_y2 = int(h * 0.98)
roi_x1 = int(w * 0.55)
roi_x2 = int(w * 0.95)

print(f"ROI: x={roi_x1}-{roi_x2}, y={roi_y1}-{roi_y2}")

# Save ROI for debugging
roi = screenshot[roi_y1:roi_y2, roi_x1:roi_x2]
cv2.imwrite('debug_roi.png', roi)
print(f"ROI saved to debug_roi.png (size: {roi.shape[1]}x{roi.shape[0]})")

# Try template matching
for btn_name, template_paths in [("like", ["templates/like_button.png", "templates/video_like.png"]),
                                  ("collect", ["templates/collect_button.png", "templates/video_collect.png"])]:
    for tpath in template_paths:
        if not os.path.exists(tpath):
            continue
        template = cv2.imread(tpath)
        if template is None:
            continue

        template_h, template_w = template.shape[:2]
        scale = min(w / 1080.0, h / 2340.0)
        target_w = max(int(template_w * scale), 10)
        target_h = max(int(template_h * scale), 10)

        if target_w > roi.shape[1] or target_h > roi.shape[0]:
            print(f"  {btn_name} ({tpath}): template too big ({target_w}x{target_h} > ROI {roi.shape[1]}x{roi.shape[0]})")
            continue

        scaled_template = cv2.resize(template, (target_w, target_h))
        s_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        t_gray = cv2.cvtColor(scaled_template, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(s_gray, t_gray, cv2.TM_CCOEFF_NORMED)
        max_score = np.max(result)
        print(f"  {btn_name} ({tpath}): max_score={max_score:.3f}, template={target_w}x{target_h}")

        if max_score > 0.5:
            max_loc = np.unravel_index(np.argmax(result), result.shape)
            x, y = int(max_loc[1]), int(max_loc[0])
            center_x = roi_x1 + x + target_w // 2
            center_y = roi_y1 + y + target_h // 2
            print(f"    -> Best match at ROI({x},{y}) = screen({center_x},{center_y})")

# Also try matching on full screenshot without ROI
print("\nFull screenshot matching:")
for btn_name, template_paths in [("like", ["templates/like_button.png", "templates/video_like.png"]),
                                  ("collect", ["templates/collect_button.png", "templates/video_collect.png"])]:
    for tpath in template_paths:
        if not os.path.exists(tpath):
            continue
        template = cv2.imread(tpath)
        if template is None:
            continue

        template_h, template_w = template.shape[:2]
        scale = min(w / 1080.0, h / 2340.0)
        target_w = max(int(template_w * scale), 10)
        target_h = max(int(template_h * scale), 10)

        if target_w > w or target_h > h:
            continue

        scaled_template = cv2.resize(template, (target_w, target_h))
        s_gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        t_gray = cv2.cvtColor(scaled_template, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(s_gray, t_gray, cv2.TM_CCOEFF_NORMED)
        max_score = np.max(result)
        print(f"  {btn_name} ({tpath}): max_score={max_score:.3f}")

        if max_score > 0.5:
            max_loc = np.unravel_index(np.argmax(result), result.shape)
            x, y = int(max_loc[1]), int(max_loc[0])
            center_x = x + target_w // 2
            center_y = y + target_h // 2
            print(f"    -> screen({center_x},{center_y})")

# Go back
ctrl.press_back()
time.sleep(1)
