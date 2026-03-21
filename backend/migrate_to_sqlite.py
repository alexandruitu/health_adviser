#!/usr/bin/env python3
"""One-time migration: all CSVs → SQLite health.db"""
import sqlite3, pandas as pd, os, math
from pathlib import Path

DB_PATH  = Path(__file__).parent / "health.db"
DATA_DIR = Path(__file__).parent.parent.parent / "health_csvs" / "cleaned"
BY_TYPE  = DATA_DIR / "by_type"

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# ── Schema ────────────────────────────────────────────────────────────────────
cur.executescript("""
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

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
""")
conn.commit()
print("✓ Schema created")


# ── Helpers ───────────────────────────────────────────────────────────────────
def to_ts(s):
    try:
        return pd.Timestamp(s).timestamp()
    except:
        return None


def clean(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except:
        return None


def insert_batches(cur, sql, rows, batch_size=1000):
    """Insert rows in batches; return total rows passed to executemany."""
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        cur.executemany(sql, batch)
        total += len(batch)
    return total


# ── 1. Workouts ───────────────────────────────────────────────────────────────
print("\n── Migrating workouts …")
workouts_csv = DATA_DIR / "workouts.csv"

df_w = pd.read_csv(workouts_csv, low_memory=False)

workout_rows = []
for _, r in df_w.iterrows():
    workout_rows.append((
        r.get("workoutType"),
        to_ts(r.get("startDate")),
        to_ts(r.get("endDate")),
        clean(r.get("duration_min")),
        clean(r.get("distance")),           # distance_km
        clean(r.get("activeEnergy_kcal")),
        r.get("sourceName") if pd.notna(r.get("sourceName")) else None,
        r.get("device") if pd.notna(r.get("device")) else None,
        clean(r.get("moving_time_min")),
        clean(r.get("elevation_m")),
        clean(r.get("avg_hr")),
        clean(r.get("max_hr")),
        clean(r.get("suffer_score")),
        clean(r.get("avg_cadence")),
        clean(r.get("avg_watts")),
        clean(r.get("avg_speed_kmh")),
        r.get("activity_name") if pd.notna(r.get("activity_name")) else None,
        r.get("workout_subtype") if pd.notna(r.get("workout_subtype")) else None,
        int(r.get("trainer")) if pd.notna(r.get("trainer")) else 0,
    ))

sql_workout = """
INSERT OR IGNORE INTO workouts
    (workout_type, start_ts, end_ts, duration_min, distance_km,
     active_energy_kcal, source, device, moving_time_min, elevation_m,
     avg_hr, max_hr, suffer_score, avg_cadence, avg_watts, avg_speed_kmh,
     activity_name, workout_subtype, trainer)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""

before = cur.execute("SELECT COUNT(*) FROM workouts").fetchone()[0]
insert_batches(cur, sql_workout, workout_rows)
conn.commit()
after = cur.execute("SELECT COUNT(*) FROM workouts").fetchone()[0]
print(f"  workouts.csv  → {after - before:,} rows inserted  (total in table: {after:,})")


# ── 2. Metrics (all by_type CSVs) ─────────────────────────────────────────────
print("\n── Migrating metrics …")

sql_metric = """
INSERT OR IGNORE INTO metrics
    (metric_name, start_ts, end_ts, value, unit, source, device)
VALUES (?,?,?,?,?,?,?)
"""

total_metrics_inserted = 0
csv_files = sorted(BY_TYPE.glob("*.csv"))

for csv_path in csv_files:
    metric_name = csv_path.stem  # filename without .csv

    try:
        df_m = pd.read_csv(csv_path, low_memory=False)
    except Exception as e:
        print(f"  ✗ {metric_name}: could not read ({e})")
        continue

    rows = []
    for _, r in df_m.iterrows():
        rows.append((
            metric_name,
            to_ts(r.get("startDate")),
            to_ts(r.get("endDate")),
            clean(r.get("value_num")),
            r.get("unit") if pd.notna(r.get("unit")) else None,
            r.get("sourceName") if pd.notna(r.get("sourceName")) else None,
            r.get("device") if pd.notna(r.get("device")) else None,
        ))

    before = cur.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    insert_batches(cur, sql_metric, rows)
    conn.commit()
    after = cur.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    inserted = after - before
    total_metrics_inserted += inserted
    print(f"  {metric_name:<45} → {inserted:>7,} rows inserted")

print(f"\n  Total metrics rows inserted: {total_metrics_inserted:,}")


# ── 3. Sleep ──────────────────────────────────────────────────────────────────
print("\n── Migrating sleep …")

# sleep_sessions.csv (cleaned) already has stage column derived from the raw
# HKCategoryValueSleepAnalysis* values; use it as the authoritative source.
# Fall back to by_type/SleepAnalysis.csv if the sessions file is unavailable.

sleep_sessions_csv = DATA_DIR / "sleep_sessions.csv"

STAGE_MAP = {
    "HKCategoryValueSleepAnalysisAsleepREM":         "REM",
    "HKCategoryValueSleepAnalysisAsleepDeep":        "Deep",
    "HKCategoryValueSleepAnalysisAsleepCore":        "Core",
    "HKCategoryValueSleepAnalysisInBed":             "InBed",
    "HKCategoryValueSleepAnalysisAwake":             "Awake",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "Unspecified",
}

def parse_stage(raw):
    """Normalise a stage value coming from either source."""
    if pd.isna(raw):
        return None
    s = str(raw).strip()
    # Already a clean label (from sleep_sessions.csv)
    if s in {"REM", "Deep", "Core", "InBed", "Awake", "Unspecified"}:
        return s
    # Full HK constant (from SleepAnalysis.csv value column)
    if s in STAGE_MAP:
        return STAGE_MAP[s]
    # Partial suffix match: "…AsleepREM" → "REM"
    for hk, label in STAGE_MAP.items():
        if s.endswith(hk.split("Analysis")[-1]):
            return label
    return s  # keep whatever is there rather than lose the row


if sleep_sessions_csv.exists():
    print(f"  Using {sleep_sessions_csv.name}")
    df_s = pd.read_csv(sleep_sessions_csv, low_memory=False)

    # Expected columns: startDate, endDate, stage, duration_hours, sourceName
    sleep_rows = []
    for _, r in df_s.iterrows():
        start_ts = to_ts(r.get("startDate"))
        end_ts   = to_ts(r.get("endDate"))
        stage    = parse_stage(r.get("stage"))
        source   = r.get("sourceName") if pd.notna(r.get("sourceName")) else None

        # Duration: prefer duration_hours column, else compute from timestamps
        if pd.notna(r.get("duration_hours")):
            duration_min = clean(r.get("duration_hours")) * 60
        elif start_ts and end_ts:
            duration_min = (end_ts - start_ts) / 60.0
        else:
            duration_min = None

        # Date: use the date of end_ts (overnight sessions end in the morning)
        if end_ts:
            date = pd.Timestamp(end_ts, unit="s").strftime("%Y-%m-%d")
        elif start_ts:
            date = pd.Timestamp(start_ts, unit="s").strftime("%Y-%m-%d")
        else:
            continue  # skip rows with no timestamps

        sleep_rows.append((date, stage, start_ts, end_ts, duration_min, source))

else:
    # Fallback: by_type/SleepAnalysis.csv (no stage column – all rows get None)
    print(f"  sleep_sessions.csv not found – falling back to by_type/SleepAnalysis.csv")
    df_s = pd.read_csv(BY_TYPE / "SleepAnalysis.csv", low_memory=False)

    sleep_rows = []
    for _, r in df_s.iterrows():
        start_ts = to_ts(r.get("startDate"))
        end_ts   = to_ts(r.get("endDate"))
        source   = r.get("sourceName") if pd.notna(r.get("sourceName")) else None
        stage    = None
        duration_min = (end_ts - start_ts) / 60.0 if (start_ts and end_ts) else None

        if end_ts:
            date = pd.Timestamp(end_ts, unit="s").strftime("%Y-%m-%d")
        elif start_ts:
            date = pd.Timestamp(start_ts, unit="s").strftime("%Y-%m-%d")
        else:
            continue

        sleep_rows.append((date, stage, start_ts, end_ts, duration_min, source))

sql_sleep = """
INSERT OR IGNORE INTO sleep
    (date, stage, start_ts, end_ts, duration_min, source)
VALUES (?,?,?,?,?,?)
"""

before = cur.execute("SELECT COUNT(*) FROM sleep").fetchone()[0]
insert_batches(cur, sql_sleep, sleep_rows)
conn.commit()
after = cur.execute("SELECT COUNT(*) FROM sleep").fetchone()[0]
print(f"  sleep_sessions.csv → {after - before:,} rows inserted  (total in table: {after:,})")


# ── Final summary ─────────────────────────────────────────────────────────────
print("\n── Row counts ──────────────────────────────────────────────────────────")
for table in ("workouts", "metrics", "sleep", "gdrive_files", "sync_log"):
    n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table:<15} {n:>10,}")

conn.close()
print("\n✓ Migration complete  →", DB_PATH)
