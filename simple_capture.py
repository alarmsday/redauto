"""简单截取当前页面"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
import io
from device_manager.controller import list_connected_devices, get_device_controller

def main():
    devices = list_connected_devices()
    if not devices:
        print("no device")
        return

    ctrl = get_device_controller(devices[0])
    display = ctrl.display_info

    # 截图
    screenshot_bytes = ctrl.take_screenshot()
    img = Image.open(io.BytesIO(screenshot_bytes))

    # 保存
    img.save("debug_steps/current_page.png")
    print("saved to debug_steps/current_page.png")

    # 裁剪底部
    bottom_h = int(display.height * 0.12)
    bottom = img.crop((0, display.height - bottom_h, display.width, display.height))
    bottom.save("debug_steps/bottom_buttons.png")
    print(f"saved bottom region to debug_steps/bottom_buttons.png, size {display.width}x{bottom_h}")

if __name__ == "__main__":
    main()
