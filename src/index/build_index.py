"""Stage 5: embed every chunk (dense bge-base + sparse BM25) and load into Qdrant with payload indexes."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))
from qdrant_client import models
from search import client, dense, sparse, COLL

chunks = [json.loads(l) for l in open("data/processed/chunks.jsonl")]
if client.collection_exists(COLL): client.delete_collection(COLL)
client.create_collection(COLL,
    vectors_config={"dense": models.VectorParams(size=768, distance=models.Distance.COSINE)},
    sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)})
for field, schema in [("report", "keyword"), ("fiscal_years", "keyword"), ("scope", "keyword"), ("section", "keyword"),
                      ("type", "keyword"), ("topics", "keyword"), ("page", "integer")]:
    client.create_payload_index(COLL, field, field_schema=schema)

texts = [c["text"] for c in chunks]
t = time.time()
dv = list(dense.embed(texts, batch_size=32))
print(f"Dense embeddings: {len(dv)} in {time.time() - t:.0f}s", flush=True)
t = time.time()
sv = list(sparse.embed(texts, batch_size=64))
print(f"Sparse embeddings: {len(sv)} in {time.time() - t:.0f}s", flush=True)
client.upload_points(COLL, [models.PointStruct(id=c["chunk_id"], payload=c, vector={
    "dense": d.tolist(), "bm25": models.SparseVector(indices=s.indices.tolist(), values=s.values.tolist())})
    for c, d, s in zip(chunks, dv, sv)], batch_size=128)
print(f"Indexed {client.count(COLL).count} points into '{COLL}'")
