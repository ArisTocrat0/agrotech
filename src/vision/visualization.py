from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def find_font(size: int = 18):
    for path in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
                 "C:/Windows/Fonts/arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    for root in [Path("/usr/share/fonts"), Path.home()/".local/share/fonts"]:
        for path in root.rglob("*.ttf"):
            if any(name in path.name.lower() for name in ["dejavu", "liberation", "noto"]):
                try:
                    return ImageFont.truetype(str(path), size)
                except OSError:
                    pass
    return ImageFont.load_default()


def annotate(image: Image.Image, detections: list) -> Image.Image:
    result = image.copy()
    draw, font = ImageDraw.Draw(result), find_font()
    for d in detections:
        from ..domain.agronomy import plant_info
        kind = plant_info(d.species, getattr(d,'kind','') or None)['kind']
        color = {'weed':'#ff3fa4','crop':'#00d9ff','unknown':'#ffd600'}.get(kind,'#ffffff')
        draw.rectangle((d.x1, d.y1, d.x2-1, d.y2-1), outline="black", width=7)
        draw.rectangle((d.x1, d.y1, d.x2-1, d.y2-1), outline=color, width=3)
        score_label = 'margin' if getattr(d, 'score_type', '') == 'linear_margin_not_probability' else 'sim'
        label = f"{d.species} | {d.stage} | {score_label}={d.similarity_score:.2f}"
        try:
            draw.text((d.x1, max(0, d.y1-22)), label, fill=color, font=font,
                      stroke_width=1, stroke_fill="black")
        except UnicodeEncodeError:
            draw.text((d.x1, d.y1), label.encode("ascii", "replace").decode(), fill="yellow", font=font)
    return result
