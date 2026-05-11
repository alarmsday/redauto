config_path = r'C:\Users\Administrator\AppData\Local\Programs\Python\Python310\lib\site-packages\easyocr\config.py'
with open(config_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 先恢复原始URL
content = content.replace(
    "'url': 'https://github.moeyy.xyz/https://github.com/",
    "'url': 'https://github.com/"
)

# 使用 gh-proxy.com 镜像
mirror = 'https://gh-proxy.com/'
new_content = content.replace(
    "'url': 'https://github.com/",
    "'url': '" + mirror + "https://github.com/"
)

with open(config_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Config patched with gh-proxy.com mirror')
