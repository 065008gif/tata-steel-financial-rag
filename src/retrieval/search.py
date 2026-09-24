"""Hybrid search over the Tata Steel index: dense (bge-base) + sparse (BM25), fused with RRF, with metadata filters."""
import os
from qdrant_client import QdrantClient, models
from fastembed import TextEmbedding, SparseTextEmbedding

COLL = "tata_steel"
CACHE = os.path.join(os.path.dirname(__file__), "..", "..", ".cache", "fastembed")
client = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))
dense = TextEmbedding("BAAI/bge-base-en-v1.5", cache_dir=CACHE, threads=24)
sparse = SparseTextEmbedding("Qdrant/bm25", cache_dir=CACHE)

def build_filter(report=None, fiscal_year=None, scope=None, types=None, section=None, topic=None):
    must = []
    def add(key, val):
        if val: must.append(models.FieldCondition(key=key, match=models.MatchAny(any=val) if isinstance(val, list) else models.MatchValue(value=val)))
    add("report", report); add("fiscal_years", fiscal_year); add("scope", scope)
    add("type", types); add("section", section); add("topics", topic)
    return models.Filter(must=must) if must else None

def search(query, k=8, **filters):
    flt = build_filter(**filters)
    dq, sq = next(dense.query_embed(query)), next(sparse.query_embed(query))
    res = client.query_points(COLL, prefetch=[
        models.Prefetch(query=dq.tolist(), using="dense", limit=40, filter=flt),
        models.Prefetch(query=models.SparseVector(indices=sq.indices.tolist(), values=sq.values.tolist()), using="bm25", limit=40, filter=flt)],
        query=models.FusionQuery(fusion=models.Fusion.RRF), limit=k, with_payload=True)
    return res.points
