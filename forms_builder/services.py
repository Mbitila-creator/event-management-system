from io import BytesIO
from urllib.parse import urljoin

import qrcode
from django.conf import settings
from django.urls import reverse
from django.utils import translation


def public_form_path(event_form, language="sw"):
    with translation.override(language):
        return reverse(
            "forms_builder:public_event_form",
            kwargs={
                "event_slug": event_form.event.slug,
                "form_slug": event_form.slug,
            },
        )


def public_form_url(event_form, request=None, language="sw"):
    path = public_form_path(event_form, language=language)
    base_url = settings.PUBLIC_BASE_URL

    if base_url:
        return urljoin(f"{base_url}/", path.lstrip("/"))

    if request is not None:
        return request.build_absolute_uri(path)

    return path


def generate_qr_png(value):
    qr_code = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr_code.add_data(value)
    qr_code.make(fit=True)

    image = qr_code.make_image(
        fill_color="#000000",
        back_color="#ffffff",
    )

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
