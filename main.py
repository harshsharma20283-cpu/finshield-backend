import os, uuid
from pathlib import Path
from typing import Optional
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import core
from db import connect, init_db
from ocr import run_ocr
from seed import seed

UPLOAD_DIR = Path(os.environ.get('UPLOAD_DIR', '/tmp/finshield_uploads'))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 5 * 1024 * 1024

app = FastAPI(title='FIN-SHIELD API')
origins = [o.strip() for o in os.environ.get('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173,https://fin-shield-jet.vercel.app').split(',') if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['*'], allow_headers=['*'])
app.mount('/uploads', StaticFiles(directory=str(UPLOAD_DIR)), name='uploads')


def db():
    c = connect()
    try:
        yield c
    finally:
        c.close()


@app.on_event('startup')
def startup():
    c = connect(); init_db(c); seed(c); c.close()


def found(x, what='Not found'):
    if x is None:
        raise HTTPException(404, what)
    return x



@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.get('/api/dashboard/summary')
def dashboard(c=Depends(db)):
    return core.dashboard(c)


@app.get('/api/ads')
def ads(q: Optional[str] = None, risk: Optional[str] = None, review_status: Optional[str] = None,
        page: int = 1, page_size: int = 12, c=Depends(db)):
    return core.list_ads(c, q, risk, review_status, max(page, 1), min(max(page_size, 1), 100))


@app.get('/api/ads/{ad_id}')
def ad(ad_id: str, c=Depends(db)):
    return found(core.detail(c, ad_id), 'Advertisement not found')


@app.get('/api/ads/{ad_id}/relationships')
def rels(ad_id: str, c=Depends(db)):
    found(core.detail(c, ad_id), 'Advertisement not found')
    return core.relationships_of(c, ad_id)


@app.post('/api/analyze')
async def analyze(text: str = Form(default=''), source: Optional[str] = Form(default=None),
                  source_url: Optional[str] = Form(default=None), image: Optional[UploadFile] = File(default=None),
                  c=Depends(db)):
    text = (text or '').strip()
    fname, ocr_text, ocr_status = None, None, 'not_requested'
    if image and image.filename:
        ext = Path(image.filename).suffix.lower()
        data = await image.read()
        if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
            raise HTTPException(400, 'Image must be JPEG, PNG or WebP.')
        if len(data) > MAX_BYTES:
            raise HTTPException(400, 'Image must be 5 MB or smaller.')
        fname = f'{uuid.uuid4().hex}{ext}'
        (UPLOAD_DIR / fname).write_bytes(data)
        ocr_status, ocr_text = run_ocr(UPLOAD_DIR / fname)
    if not text and not ocr_text:
        if not fname:
            raise HTTPException(400, 'Provide advertisement text or an image.')
    ad_id = core.analyze_and_store(c, text, (source or '').strip() or None, (source_url or '').strip() or None,
                                   fname, ocr_text, ocr_status)
    return core.detail(c, ad_id)


@app.get('/api/campaigns')
def campaigns(c=Depends(db)):
    return core.campaigns(c)


@app.get('/api/campaigns/{cid}')
def campaign(cid: str, c=Depends(db)):
    return found(core.campaign_detail(c, cid), 'Campaign not found')


@app.get('/api/alerts')
def alerts(unread_only: bool = False, c=Depends(db)):
    return core.list_alerts(c, unread_only)


class ReadBody(BaseModel):
    is_read: bool


class ReviewBody(BaseModel):
    review_status: str


class NoteBody(BaseModel):
    content: str


@app.patch('/api/alerts/{alert_id}')
def mark(alert_id: str, body: ReadBody, c=Depends(db)):
    return found(core.mark_alert(c, alert_id, body.is_read), 'Alert not found')


@app.patch('/api/ads/{ad_id}/review')
def review(ad_id: str, body: ReviewBody, c=Depends(db)):
    return found(core.set_review(c, ad_id, body.review_status), 'Invalid review status or ad not found')


@app.post('/api/ads/{ad_id}/notes')
def note(ad_id: str, body: NoteBody, c=Depends(db)):
    if not body.content.strip():
        raise HTTPException(400, 'Note cannot be empty.')
    return found(core.add_note(c, ad_id, body.content), 'Advertisement not found')
