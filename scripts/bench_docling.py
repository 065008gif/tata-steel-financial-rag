"""Benchmark Docling (OCR off, accurate tables, 24 threads) over a page range in one run."""
import sys, time
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
try:
    from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
except ImportError:
    from docling.datamodel.pipeline_options import AcceleratorOptions, AcceleratorDevice

pdf_path, first, last = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
opts = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
opts.table_structure_options.mode = TableFormerMode.ACCURATE
opts.table_structure_options.do_cell_matching = True
opts.accelerator_options = AcceleratorOptions(num_threads=24, device=AcceleratorDevice.CPU)
converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})

t0 = time.time()
converter.initialize_pipeline(InputFormat.PDF)
t1 = time.time()
result = converter.convert(pdf_path, page_range=(first, last))
t2 = time.time()
n = last - first + 1
print(f"\nModel load: {t1 - t0:.1f}s | {n} pages converted in {t2 - t1:.1f}s = {(t2 - t1) / n:.1f}s per page")
print(f"Tables found: {len(result.document.tables)}")
