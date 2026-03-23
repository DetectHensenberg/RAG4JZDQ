"""Full pipeline test: reranker + filename boost for '数据仓库'."""
import sys, time, logging
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

from pathlib import Path
from api.deps import get_hybrid_search, reset_all

reset_all()

t0 = time.perf_counter()
search = get_hybrid_search("default")
print(f"Init: {time.perf_counter()-t0:.2f}s")
print(f"Reranker: {search.reranker is not None}")

query = "数据仓库"
t1 = time.perf_counter()
results = search.search(query=query, top_k=10)
elapsed = time.perf_counter() - t1
print(f"\nSearch: {elapsed:.2f}s")

print(f"\n=== Top 10 for '{query}' (reranker + filename boost) ===")
for i, r in enumerate(results):
    src = Path(r.metadata.get("source_path", "?")).name
    tags = []
    if r.metadata.get("reranked"):
        tags.append("reranked")
    if r.metadata.get("filename_boosted"):
        tags.append("boosted")
    tag = f" [{', '.join(tags)}]" if tags else ""
    marker = " ★" if "数据仓库-数据建模" in src else ""
    print(f"  {i+1}. score={r.score:.4f} | {src}{tag}{marker}")
