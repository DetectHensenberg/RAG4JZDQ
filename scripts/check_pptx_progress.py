"""Check how many PPTX files have been re-ingested."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

conn = sqlite3.connect("data/db/chroma/chroma.sqlite3")

total = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]

pptx_rows = conn.execute(
    "SELECT DISTINCT m.string_value, COUNT(e.id) as cnt "
    "FROM embedding_metadata m "
    "JOIN embeddings e ON e.id = m.id "
    "WHERE m.key = 'source_path' AND (m.string_value LIKE '%.pptx' OR m.string_value LIKE '%.ppt') "
    "GROUP BY m.string_value "
    "ORDER BY m.string_value"
).fetchall()

print(f"Total chunks in DB: {total}")
print(f"PPTX files ingested: {len(pptx_rows)}")
pptx_chunks = sum(r[1] for r in pptx_rows)
print(f"PPTX chunks total: {pptx_chunks}")
print()
for path, cnt in pptx_rows:
    name = Path(path).name
    print(f"  {cnt:>3} chunks  {name}")
conn.close()
