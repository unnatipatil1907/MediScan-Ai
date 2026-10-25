from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("MEDISCAN_DB_PATH", str(APP_DIR / "mediscan.db")))


def db_connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with db_connect() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            total_tests INTEGER NOT NULL,
            low_count INTEGER NOT NULL,
            in_range_count INTEGER NOT NULL,
            high_count INTEGER NOT NULL,
            summary TEXT NOT NULL
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
            test TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT NOT NULL,
            min REAL NOT NULL,
            max REAL NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Low','In range','High')),
            review_flag TEXT NOT NULL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_results_report_id ON results(report_id)")


def save_report(df: pd.DataFrame, source_name: str, source_type: str, raw_bytes: bytes, summary: str) -> int:
    low = int((df.status == "Low").sum())
    normal = int((df.status == "In range").sum())
    high = int((df.status == "High").sum())
    created = datetime.now().astimezone().isoformat(timespec="seconds")
    digest = hashlib.sha256(raw_bytes).hexdigest()
    with db_connect() as conn:
        cur = conn.execute("""INSERT INTO reports
            (created_at,source_name,source_type,source_sha256,total_tests,low_count,in_range_count,high_count,summary)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (created, source_name, source_type, digest, len(df), low, normal, high, summary))
        report_id = cur.lastrowid
        conn.executemany("""INSERT INTO results
            (report_id,test,value,unit,min,max,status,review_flag) VALUES (?,?,?,?,?,?,?,?)""",
            [(report_id, str(r.test), float(r.value), str(r.unit), float(r["min"]), float(r["max"]), str(r.status), str(r.review_flag))
             for _, r in df.iterrows()])
        return int(report_id)


def get_history():
    with db_connect() as conn:
        return pd.read_sql_query("""SELECT id,created_at,source_name,source_type,total_tests,low_count,in_range_count,high_count
                                    FROM reports ORDER BY id DESC""", conn)


def get_report(report_id: int):
    with db_connect() as conn:
        report = conn.execute("SELECT * FROM reports WHERE id=?", (int(report_id),)).fetchone()
        rows = pd.read_sql_query("SELECT test,value,unit,min,max,status,review_flag FROM results WHERE report_id=? ORDER BY id",
                                 conn, params=(int(report_id),))
    return report, rows
