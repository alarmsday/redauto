"""Extract bottom area to find button positions"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image
import cv2
import numpy as np

# Load the screenshot
screenshot = Image.open("debug_steps/btn3_1_post_detail.png")
img_array = np.array(screenshot)
h, w = img_array.shape[:2]
print(f"Screenshot size: {w}x{h}")

# Extract the bottom 15% of the screen where buttons are located
y_start = int(h * 0.85)
bottom_area = img_array[y_start:, :]

# Save the bottom area for inspection
bottom_img = Image.fromarray(bottom_area)
bottom_img.save("debug_steps/bottom_area.png")
print(f"Saved bottom area (y={y_start} to {h})")

# Now try to extract the like button more precisely
# Based on the screenshot, buttons are at the very bottom
# Let's crop a region that should contain the buttons
# Estimated: x=700-1050, y=2350-2550

like_region = img_array[2350:2550, 700:1050]
like_img = Image.fromarray(like_region)
like_img.save("debug_steps/like_region.png")
print(f"Saved like region (700-1050, 2350-2550)")

# Also try to detect the heart icon by color
# Heart icon is typically red/pink
hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)

# Define range of red colors
lower_red = np.array([0, 100, 100])
upper_red = np.array([15, 255, 255])

# Threshold the HSV image to get red components
mask1 = cv2.inRange(hsv, lower_red, upper_red)
lower_red2 = np.array([160, 100, 100])
upper_red2 = np.array([180, 255, 255])
mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
mask = cv2.bitwise_or(mask1, mask2)

# Save the mask to see where red colors are
mask_img = Image.fromarray(mask)
mask_img.save("debug_steps/red_mask.png")
print("Saved red color mask")

# Find contours in the mask
contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# Look for small red objects in the bottom area
print(f"Found {len(contours)} red objects")
for i, contour in enumerate(contours):
    area = cv2.contourArea(contour)
    x, y, w, h = cv2.boundingRect(contour)
    if 500 < area < 5000 and y > int(img_array.shape[0] * 0.8):
        print(f"  Contour {i}: area={area}, pos=({x}, {y}), size={w}x{h}")

        # Extract this region as a potential button
        margin = 10
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(img_array.shape[1], x + w + margin)
        y2 = min(img_array.shape[0], y + h + margin)

        button_crop = img_array[y1:y2, x1:x2]
        button_img = Image.fromarray(button_crop)
        button_img.save(f"debug_steps/potential_button_{i}.png")
        print(f"    Saved potential button at ({x1}, {y1})")
