"""Run Docling table extraction (OCR off, embedded PDF text only) on a single page."""
import sys, time
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

pdf_path, page = sys.argv[1], int(sys.argv[2])
opts = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
opts.table_structure_options.do_cell_matching = True
converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})

start = time.time()
result = converter.convert(pdf_path, page_range=(page, page))
doc = result.document
print(f"\nPage {page}: {len(doc.tables)} table(s) found in {time.time() - start:.1f}s\n")
for n, table in enumerate(doc.tables, 1):
    print(f"===== TABLE {n} =====")
    print(table.export_to_markdown(doc=doc))
    print()
