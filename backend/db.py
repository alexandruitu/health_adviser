"""
Database connection and schema helpers.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "health.db"


def _db() -> sqlite3.Connection:
    """Return a thread-local SQLite connection with row_factory."""
    import threading
    if not hasattr(_db, "_local"):
        _db._local = threading.local()
    if not hasattr(_db._local, "conn"):
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = _sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _db._local.conn = conn
    return _db._local.conn


def _ensure_biomarker_tables():
    """Create biomarker tables if they don't exist."""
    conn = _db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS biomarker_uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            upload_ts INTEGER,
            test_date TEXT,
            lab_name TEXT,
            records_extracted INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS biomarkers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id INTEGER REFERENCES biomarker_uploads(id) ON DELETE CASCADE,
            test_date TEXT,
            marker_name TEXT,
            marker_canonical TEXT,
            value REAL,
            unit TEXT,
            ref_min REAL,
            ref_max REAL,
            category TEXT,
            status TEXT,
            UNIQUE(upload_id, marker_canonical)
        );
        CREATE INDEX IF NOT EXISTS idx_bio_marker ON biomarkers(marker_canonical);
        CREATE INDEX IF NOT EXISTS idx_bio_date ON biomarkers(test_date);
    """)
    conn.commit()
