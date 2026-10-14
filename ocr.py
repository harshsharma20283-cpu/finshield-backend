def run_ocr(path):
    """Returns (status, text). Status matches what the frontend expects."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return 'unavailable', None
    try:
        text = pytesseract.image_to_string(Image.open(path)).strip()
    except Exception as exc:
        return ('unavailable' if 'tesseract' in type(exc).__name__.lower() else 'failed'), None
    return ('extracted' if text else 'empty'), (text or None)
