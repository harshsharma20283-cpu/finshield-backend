import re

PHONE_RE = re.compile(r'(?<!\d)(?:\+?91[\s-]?)?([6-9]\d{4}[\s-]?\d{5})(?!\d)')
UPI_RE = re.compile(r'\b[a-zA-Z0-9._-]{2,}@[a-zA-Z]{2,}\b(?!\.[a-zA-Z])')
URL_RE = re.compile(r'(?:https?://|www\.|t\.me/|wa\.me/)[^\s,;)]+', re.I)


def normalize_phone(raw: str) -> str:
    """'99988 77665' and '+91 99988-77665' both become '+919998877665'."""
    digits = re.sub(r'\D', '', raw)[-10:]
    return '+91' + digits


def extract_entities(text: str) -> dict:
    phones = sorted({normalize_phone(m.group(1)) for m in PHONE_RE.finditer(text)})
    upis = sorted({m.group(0).lower() for m in UPI_RE.finditer(text)})
    urls = sorted({m.group(0).rstrip('.').lower() for m in URL_RE.finditer(text)})
    return {'phones': phones, 'upi_ids': upis, 'urls': urls}
