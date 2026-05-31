# make_icon.py
# 生成 app.ico 应用图标（无需美术资源，纯代码绘制）
# 用法：python make_icon.py
# 设计：深色圆角背景 + 渐变播放三角 + 音符，呼应"视频转音频"主题

from PIL import Image, ImageDraw

# 用较大尺寸绘制再缩放，边缘更平滑
SIZE = 256
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

def rounded_rect(d, box, radius, fill):
    """画圆角矩形背景"""
    d.rounded_rectangle(box, radius=radius, fill=fill)

# 背景：深蓝紫圆角方块
rounded_rect(draw, [8, 8, SIZE - 8, SIZE - 8], radius=48, fill=(40, 42, 66, 255))

# 竖向渐变叠加，增加层次（从顶部稍亮到底部稍暗）
grad = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
gd = ImageDraw.Draw(grad)
for y in range(SIZE):
    a = int(40 * (1 - y / SIZE))  # 顶部更亮
    gd.line([(0, y), (SIZE, y)], fill=(120, 130, 255, a))
# 用背景形状裁剪渐变
mask = Image.new("L", (SIZE, SIZE), 0)
ImageDraw.Draw(mask).rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=48, fill=255)
img.paste(grad, (0, 0), mask)
draw = ImageDraw.Draw(img)

# 播放三角形（橙色，代表视频/播放）
tri = [(96, 70), (96, 186), (188, 128)]
draw.polygon(tri, fill=(255, 138, 60, 255))

# 音符（白色，代表提取出的音频）放在右下角
# 符头
draw.ellipse([150, 158, 182, 186], fill=(255, 255, 255, 255))
# 符杆
draw.rectangle([178, 96, 184, 172], fill=(255, 255, 255, 255))
# 符尾旗
draw.polygon([(184, 96), (184, 120), (206, 110), (206, 90)], fill=(255, 255, 255, 255))

# 导出多分辨率 ico，Windows 会按需取用合适尺寸
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save("app.ico", format="ICO", sizes=sizes)
# 同时存一份 png 便于预览
img.save("app_icon_preview.png", format="PNG")
print("已生成 app.ico 和 app_icon_preview.png")
