import os, sqlite3
from datetime import datetime, timezone

DB_PATH = os.environ.get('DB_PATH', '/tmp/finshield.db')
SCHEMA = """
CREATE TABLE IF NOT EXISTS ads(id TEXT PRIMARY KEY, text TEXT, source TEXT, source_url TEXT, is_seed INTEGER,
 analysis_status TEXT, review_status TEXT, risk_score INTEGER, risk_category TEXT, created_at TEXT, image_filename TEXT,
 ocr_text TEXT, ocr_status TEXT, limitations TEXT, recommendation TEXT, analyzed_at TEXT, warnings TEXT);
CREATE TABLE IF NOT EXISTS entities(id TEXT PRIMARY KEY, ad_id TEXT, entity_type TEXT, raw_value TEXT, normalized_value TEXT,
 source_text TEXT, extraction_method TEXT, confidence REAL);
CREATE INDEX IF NOT EXISTS ix_ent ON entities(entity_type, normalized_value);
CREATE TABLE IF NOT EXISTS signals(id TEXT PRIMARY KEY, ad_id TEXT, signal_type TEXT, title TEXT, explanation TEXT,
 evidence TEXT, contribution INTEGER, recommendation TEXT);
CREATE TABLE IF NOT EXISTS relationships(id TEXT PRIMARY KEY, source_ad_id TEXT, target_ad_id TEXT, relationship_type TEXT,
 evidence TEXT, explanation TEXT, similarity_score REAL);
CREATE TABLE IF NOT EXISTS alerts(id TEXT PRIMARY KEY, alert_key TEXT UNIQUE, alert_type TEXT, severity TEXT,
 advertisement_id TEXT, campaign_id TEXT, reason TEXT, is_read INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, ad_id TEXT, content TEXT, created_at TEXT);
"""


def connect(path=None):
    c = sqlite3.connect(path or DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db(c):
    c.executescript(SCHEMA)
    c.commit()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')
