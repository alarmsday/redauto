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

cv2.imwrite('debug_post2.png', screenshot)
print(f"Saved debug_post2.png ({w}x{h})")

# The like/collect buttons are at bottom-right area
# Based on previous run: like at (777, 2176), collect at (885, 2176)
# Extract button regions for templates

# Like button region (left of collect)
like_x1, like_y1 = 730, 2130
like_x2, like_y2 = 820, 2220
like_region = screenshot[like_y1:like_y2, like_x1:like_x2]
cv2.imwrite('templates/like_button.png', like_region)
print(f"Extracted like button: {like_x1},{like_y1} -> {like_x2},{like_y2}")

# Collect button region (right of like)
collect_x1, collect_y1 = 830, 2130
collect_x2, collect_y2 = 930, 2220
collect_region = screenshot[collect_y1:collect_y2, collect_x1:collect_x2]
cv2.imwrite('templates/collect_button.png', collect_region)
print(f"Extracted collect button: {collect_x1},{collect_y1} -> {collect_x2},{collect_y2}")

# Go back
ctrl.press_back()
time.sleep(2)
