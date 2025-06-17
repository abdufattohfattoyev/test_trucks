from PIL import Image, ImageDraw, ImageFont
import os



def create_gradient_background(size, color1=(44, 62, 80), color2=(26, 188, 156)):
    # Gradient fon yaratish
    image = Image.new('RGB', size)
    draw = ImageDraw.Draw(image)
    for y in range(size[1]):
        r = color1[0] + (color2[0] - color1[0]) * y // size[1]
        g = color1[1] + (color2[1] - color1[1]) * y // size[1]
        b = color1[2] + (color2[2] - color1[2]) * y // size[1]
        draw.line((0, y, size[0], y), fill=(r, g, b))
    return image


def create_favicon(size=(32, 32), filename='favicon.png', font_size=20):
    # Gradient fonli rasm
    image = create_gradient_background(size)
    draw = ImageDraw.Draw(image)

    # Yumaloq ramka effekti
    draw.ellipse((2, 2, size[0] - 3, size[1] - 3), outline=(255, 255, 255, 128), width=1)

    # "T" harfini chizish
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()

    text = "T"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Harfni markazga joylashtirish
    draw.text(
        ((size[0] - text_width) / 2, (size[1] - text_height) / 2),
        text,
        fill='white',
        font=font
    )

    # Faylni saqlash
    static_dir = os.path.join('D:\\truck_savdo\\static')
    os.makedirs(static_dir, exist_ok=True)
    favicon_path = os.path.join(static_dir, filename)
    image.save(favicon_path, 'PNG')
    print(f"Favicon {favicon_path} ga saqlandi")


if __name__ == "__main__":
    # Favicon (32x32) yaratish
    create_favicon(size=(32, 32), filename='favicon.png', font_size=20)
    # Apple Touch Icon (180x180) yaratish
    create_favicon(size=(180, 180), filename='apple-touch-icon.png', font_size=100)