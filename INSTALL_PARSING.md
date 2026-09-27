# Installation: parsing software and pipeline

Tested on Ubuntu (college PC, CPU only, no GPU), Python 3.11 in a Conda environment inside the project folder.
Exact versions of the whole environment: `requirements-full.txt`.

## 1. Environment
```bash
git clone <repo> financial-rag && cd financial-rag
conda create -p ./.venv python=3.11 -y && conda activate ./.venv
```

## 2. Parsing software
| Package | Version | Used for |
|---|---|---|
| Docling | 2.130.0 (docling-core 2.98.0, docling-parse 7.21.0, docling-ibm-models 4.0.3) | Table structure for notes tables (TableFormer, ACCURATE mode, OCR off) |
| PyMuPDF | 1.28.2 | Page text, word coordinates (statement parser, page map), statement-only PDFs |
| PyTorch (CPU) | 2.14.0+cpu | Docling's layout and table models |
| RapidFuzz | 3.14.6 | Label matching |
| fastembed | 0.8.1 | Embeddings: BAAI/bge-base-en-v1.5 (dense) + Qdrant/bm25 (sparse) |
| qdrant-client | 1.19.1 | Vector database client |

```bash
pip install torch==2.14.0+cpu --index-url https://download.pytorch.org/whl/cpu
pip install docling==2.130.0 pymupdf==1.28.2 rapidfuzz==3.14.6
pip install -r requirements-api.txt          # FastAPI, qdrant-client[fastembed], ollama, python-dotenv
# or reproduce the exact environment:  pip install -r requirements-full.txt
```
Docling downloads its layout/table models on first use (cached under ~/.cache). fastembed models are cached in `.cache/fastembed`.
Offline note: fastembed 0.8.1 lists `tamil.txt` and `mock.file` for Qdrant/bm25 that the published model does not contain;
after the first online download create them as empty files in `.cache/fastembed/models--Qdrant--bm25/snapshots/<id>/`
(the index uses English stopwords only) so the backend can start with `HF_HUB_OFFLINE=1`.

## 3. Services
Docker with Compose. Qdrant: `docker compose up -d qdrant`. Ollama Cloud API key in `.env`: `OLLAMA_API_KEY=your_key_here`.

## 4. Run the pipeline (from the repo root)
```bash
bash scripts/download_reports.sh             # four annual report PDFs -> data/raw/
python src/ingest/page_map.py                # page -> section / scope / statement / printed label
python src/ingest/run_docling.py             # Docling tables (about 35 min for all four reports on CPU)
python src/ingest/line_items.py              # coordinate-based statement extraction + balance/subtotal checks
python src/analysis/canonical.py             # canonical financial items
python src/ingest/retained_earnings.py       # page-verified retained earnings (Altman X2)
python src/ingest/segments.py                # segment revenue/EBITDA, reconciled
python src/ingest/company_facts.py           # page-verified company facts
python src/ingest/build_chunks.py && python src/index/build_index.py
python eval/build_questions.py && python eval/run_eval.py
```

## 5. Run the application
```bash
docker compose --profile full up -d --build   # qdrant + backend + frontend (nginx :8080) + Cloudflare tunnel
docker compose logs tunnel | grep trycloudflare.com
docker compose --profile full down            # stop everything
```
