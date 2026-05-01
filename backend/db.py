"""
Database connection and schema helpers.
"""
import sqlite3

from paths import DB_PATH


def _db() -> sqlite3.Connection:
    """Return a thread-local SQLite connection with row_factory."""
    import threading
    if not hasattr(_db, "_local"):
        _db._local = threading.local()
    if not hasattr(_db._local, "conn"):
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
        conn.row_factory = _sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        _db._local.conn = conn
    return _db._local.conn


def _ensure_biomarker_tables():
    """Create all tables if they don't exist."""
    conn = _db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS metrics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT    NOT NULL,
            start_ts    REAL    NOT NULL,
            end_ts      REAL,
            value       REAL,
            unit        TEXT,
            source      TEXT,
            device      TEXT,
            UNIQUE(metric_name, start_ts, source)
        );
        CREATE INDEX IF NOT EXISTS idx_metrics_name_ts ON metrics(metric_name, start_ts);

        CREATE TABLE IF NOT EXISTS workouts (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            workout_type        TEXT,
            start_ts            REAL    NOT NULL,
            end_ts              REAL,
            duration_min        REAL,
            distance_km         REAL,
            active_energy_kcal  REAL,
            source              TEXT,
            device              TEXT,
            moving_time_min     REAL,
            elevation_m         REAL,
            avg_hr              REAL,
            max_hr              REAL,
            suffer_score        REAL,
            avg_cadence         REAL,
            avg_watts           REAL,
            avg_speed_kmh       REAL,
            activity_name       TEXT,
            workout_subtype     TEXT,
            trainer             INTEGER DEFAULT 0,
            UNIQUE(start_ts, workout_type)
        );
        CREATE INDEX IF NOT EXISTS idx_workouts_ts   ON workouts(start_ts);
        CREATE INDEX IF NOT EXISTS idx_workouts_type ON workouts(workout_type, start_ts);

        CREATE TABLE IF NOT EXISTS sleep (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            date         TEXT    NOT NULL,
            stage        TEXT,
            start_ts     REAL,
            end_ts       REAL,
            duration_min REAL,
            source       TEXT,
            UNIQUE(start_ts, stage, source)
        );
        CREATE INDEX IF NOT EXISTS idx_sleep_date ON sleep(date);

        CREATE TABLE IF NOT EXISTS gdrive_files (
            file_id       TEXT PRIMARY KEY,
            file_name     TEXT,
            modified_time TEXT,
            processed_at  REAL,
            records_added INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sync_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            source    TEXT,
            synced_at REAL,
            added     INTEGER,
            skipped   INTEGER,
            note      TEXT
        );

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

        CREATE TABLE IF NOT EXISTS goals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            event_date  TEXT    NOT NULL,
            target_ctl  REAL,
            created_at  INTEGER DEFAULT (unixepoch())
        );
    """)
    conn.commit()
