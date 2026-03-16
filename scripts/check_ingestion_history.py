"""Quick check of ingestion_history.db status."""
import sqlite3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

path = "data/db/ingestion_history.db"
print(f"ingestion_history.db exists: {os.path.exists(path)}")

if not os.path.exists(path):
    print("No ingestion history database found!")
    print("This means no files have been ingested through the pipeline.")
    sys.exit(0)

conn = sqlite3.connect(path)
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print(f"Tables: {[t[0] for t in tables]}")

for t in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
    print(f"  {t[0]}: {count} rows")

try:
    cols = conn.execute("SELECT DISTINCT collection FROM ingestion_history").fetchall()
    print(f"Collections: {[c[0] for c in cols]}")
    statuses = conn.execute(
        "SELECT status, COUNT(*) FROM ingestion_history GROUP BY status"
    ).fetchall()
    print(f"Statuses: {statuses}")
    # Show a few recent records
    rows = conn.execute(
        "SELECT file_hash, file_path, collection, status, processed_at "
        "FROM ingestion_history ORDER BY processed_at DESC LIMIT 5"
    ).fetchall()
    for r in rows:
        print(f"  {r[3]:8s} | {r[2]:10s} | {r[4]} | {r[1]}")
except Exception as e:
    print(f"Error: {e}")

conn.close()
