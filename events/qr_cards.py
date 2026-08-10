from io import BytesIO

import qrcode
from PIL import Image, ImageDraw, ImageFont


CARD_WIDTH = 1600
CARD_HEIGHT = 760
NAVY = "#17365d"
MUTED = "#64748b"
BORDER = "#b9c7d6"


def _font(size, *, bold=False):
    names = (
        ("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf")
        if bold
        else ("DejaVuSans.ttf", "LiberationSans-Regular.ttf")
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _wrap_text(draw, text, font, max_width, max_lines):
    words = str(text or "—").split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    consumed = " ".join(lines)
    original = " ".join(words)
    if consumed != original and lines:
        while lines[-1] and draw.textlength(f"{lines[-1]}…", font=font) > max_width:
            lines[-1] = lines[-1][:-1]
        lines[-1] = f"{lines[-1].rstrip()}…"
    return lines or ["—"]


def _draw_lines(draw, lines, position, font, fill, spacing):
    x, y = position
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += spacing
    return y


def render_participant_qr_card(participant, verification_url):
    """Return a paste-ready PNG card containing the participant's QR identity."""
    card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), "white")
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle(
        (3, 3, CARD_WIDTH - 4, CARD_HEIGHT - 4),
        radius=28,
        outline=BORDER,
        width=4,
    )

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(verification_url)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_image = qr_image.resize((420, 420), Image.Resampling.NEAREST)
    card.paste(qr_image, (90, 170))

    text_x = 585
    text_width = CARD_WIDTH - text_x - 80
    event_font = _font(31, bold=True)
    name_font = _font(49, bold=True)
    institution_font = _font(28)
    instruction_font = _font(27)

    identity_lines = _wrap_text(
        draw,
        f"{participant.event.code} · {participant.source_sheet} / {participant.source_number}",
        event_font,
        text_width,
        1,
    )
    _draw_lines(
        draw,
        identity_lines,
        (text_x, 183),
        event_font,
        NAVY,
        40,
    )
    name_lines = _wrap_text(
        draw,
        participant.full_name,
        name_font,
        text_width,
        2,
    )
    y = _draw_lines(
        draw,
        name_lines,
        (text_x, 245),
        name_font,
        "#000000",
        62,
    )
    institution_lines = _wrap_text(
        draw,
        participant.institution,
        institution_font,
        text_width,
        3,
    )
    y = _draw_lines(
        draw,
        institution_lines,
        (text_x, y + 9),
        institution_font,
        "#111111",
        39,
    )
    draw.text(
        (text_x, min(y + 20, 625)),
        "Scan to view the verified participant row",
        font=instruction_font,
        fill=MUTED,
    )

    output = BytesIO()
    card.save(output, format="PNG", optimize=True)
    return output.getvalue()
