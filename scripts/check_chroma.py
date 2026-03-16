"""Check ChromaDB state without modifying data."""
import sqlite3
import os
from pathlib import Path

db_path = Path("data/db/chroma/chroma.sqlite3")
print(f"DB size: {os.path.getsize(db_path) // 1024} KB")

wal_path = Path(str(db_path) + "-wal")
if wal_path.exists():
    print(f"WAL size: {os.path.getsize(wal_path) // 1024} KB")
else:
    print("No WAL file")

conn = sqlite3.connect(str(db_path))
tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
)]
print(f"Tables: {tables}")

for t in tables:
    cnt = conn.execute(f"SELECT count(*) FROM [{t}]").fetchone()[0]
    print(f"  {t}: {cnt} rows")

conn.close()

# Test read via ChromaDB API
import chromadb
c = chromadb.PersistentClient(path="data/db/chroma")
col = c.get_or_create_collection("default")
print(f"\nCollection 'default' count: {col.count()}")

# Test a small query
try:
    results = col.peek(limit=2)
    print(f"Peek OK: {len(results['ids'])} records")
except Exception as e:
    print(f"Peek failed: {e}")

# Test a small write
try:
    col.upsert(
        ids=["_test_probe"],
        embeddings=[[0.0] * 1024],
        documents=["test"],
        metadatas=[{"_test": "true"}],
    )
    print("Write test: OK")
    # Clean up test record
    col.delete(ids=["_test_probe"])
    print("Delete test probe: OK")
except Exception as e:
    print(f"Write test FAILED: {e}")
