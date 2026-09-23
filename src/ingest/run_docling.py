"""Stage 2: run Docling over every financial-statement page of each report (from the page map).

Saves the full Docling document per year to data/interim/docling_<FY>.json.
Skips years already done, so it is safe to re-run after an interruption.
"""
import json, sys, time
from pathlib import Path
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
try:
    from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
except ImportError:
    from docling.datamodel.pipeline_options import AcceleratorOptions, AcceleratorDevice

INTERIM = Path("data/interim")
YEARS = sys.argv[1:] or ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]

opts = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
opts.table_structure_options.mode = TableFormerMode.ACCURATE
opts.table_structure_options.do_cell_matching = True
opts.accelerator_options = AcceleratorOptions(num_threads=24, device=AcceleratorDevice.CPU)
converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
converter.initialize_pipeline(InputFormat.PDF)

for fy in YEARS:
    out = INTERIM / f"docling_{fy}.json"
    if out.exists():
        print(f"{fy}: already done, skipping", flush=True)
        continue
    page_map = json.loads((INTERIM / f"page_map_{fy}.json").read_text())
    fs_pages = [p["page"] for p in page_map if p["section"] == "financial_statements"]
    first, last = min(fs_pages), max(fs_pages)
    print(f"{fy}: starting pages {first}-{last} ({last - first + 1} pages)", flush=True)
    t = time.time()
    result = converter.convert(f"data/raw/TataSteel_{fy}.pdf", page_range=(first, last))
    result.document.save_as_json(out)
    print(f"{fy}: DONE - {len(result.document.tables)} tables in {(time.time() - t) / 60:.1f} min", flush=True)

print("ALL YEARS COMPLETE", flush=True)
