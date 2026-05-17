---
name: pdf-reader
description: Comprehensive PDF manipulation toolkit for extracting text and tables, creating and editing PDFs, merging/splitting documents, and handling forms. Supports batch processing for large files and OCR for scanned PDFs.
license: Proprietary. LICENSE.txt has complete terms
---

# PDF Processing Guide

## Overview

This guide covers essential PDF operations using Python libraries and command-line tools. For advanced features, JavaScript libraries, and detailed examples, see `reference.md`. For PDF forms, refer to `forms.md`.

---

## Quick Start

### Read and Extract Text (Batch-Friendly)
```python
import pdfplumber

text = ""
batch_size = 5  # process 5 pages at a time
with pdfplumber.open("document.pdf") as pdf:
    total_pages = len(pdf.pages)
    for start in range(0, total_pages, batch_size):
        end = min(start + batch_size, total_pages)
        for page in pdf.pages[start:end]:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n\n"
````

---

## Python Libraries

### `pypdf` - Basic Operations

#### Merge PDFs

```python
from pypdf import PdfWriter, PdfReader

writer = PdfWriter()
for file in ["doc1.pdf", "doc2.pdf", "doc3.pdf"]:
    reader = PdfReader(file)
    for page in reader.pages:
        writer.add_page(page)

with open("merged.pdf", "wb") as f:
    writer.write(f)
```

#### Split PDF

```python
reader = PdfReader("input.pdf")
for i, page in enumerate(reader.pages):
    writer = PdfWriter()
    writer.add_page(page)
    with open(f"page_{i+1}.pdf", "wb") as f:
        writer.write(f)
```

#### Extract Metadata

```python
reader = PdfReader("document.pdf")
meta = reader.metadata
print(f"Title: {meta.title}, Author: {meta.author}, Subject: {meta.subject}, Creator: {meta.creator}")
```

#### Rotate Pages

```python
reader = PdfReader("input.pdf")
writer = PdfWriter()
page = reader.pages[0]
page.rotate(90)
writer.add_page(page)
with open("rotated.pdf", "wb") as f:
    writer.write(f)
```

---

### `pdfplumber` - Text & Table Extraction

#### Extract Tables

```python
import pdfplumber
import pandas as pd

all_tables = []
with pdfplumber.open("document.pdf") as pdf:
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            if table:
                df = pd.DataFrame(table[1:], columns=table[0])
                all_tables.append(df)

if all_tables:
    combined_df = pd.concat(all_tables, ignore_index=True)
    combined_df.to_excel("extracted_tables.xlsx", index=False)
```

---

### `reportlab` - PDF Creation

#### Basic PDF

```python
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

c = canvas.Canvas("hello.pdf", pagesize=letter)
c.drawString(100, 700, "Hello World!")
c.save()
```

#### Multi-Page PDF

```python
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet

doc = SimpleDocTemplate("report.pdf")
styles = getSampleStyleSheet()
story = []

story.append(Paragraph("Report Title", styles['Title']))
story.append(Spacer(1, 12))
story.append(Paragraph("This is the body text " * 20, styles['Normal']))
story.append(PageBreak())
story.append(Paragraph("Page 2 Content", styles['Normal']))

doc.build(story)
```

---

## Command-Line Tools

* **pdftotext**:

```bash
pdftotext -layout input.pdf output.txt  # preserves layout
pdftotext -f 1 -l 5 input.pdf output.txt  # specific pages
```

* **qpdf**:

```bash
qpdf --empty --pages file1.pdf file2.pdf -- merged.pdf
qpdf input.pdf --pages . 1-5 -- pages1-5.pdf
qpdf input.pdf output.pdf --rotate=+90:1
qpdf --password=mypassword --decrypt encrypted.pdf decrypted.pdf
```

* **pdftk**:

```bash
pdftk file1.pdf file2.pdf cat output merged.pdf
pdftk input.pdf burst
pdftk input.pdf rotate 1east output rotated.pdf
```

---

## Common Tasks

### OCR for Scanned PDFs

```python
import pytesseract
from pdf2image import convert_from_path

text = ""
images = convert_from_path("scanned.pdf")
for i, img in enumerate(images):
    text += f"Page {i+1}:\n{pytesseract.image_to_string(img)}\n\n"
```

### Add Watermark

```python
from pypdf import PdfReader, PdfWriter

watermark = PdfReader("watermark.pdf").pages[0]
reader = PdfReader("document.pdf")
writer = PdfWriter()

for page in reader.pages:
    page.merge_page(watermark)
    writer.add_page(page)

with open("watermarked.pdf", "wb") as f:
    writer.write(f)
```

### Password Protection

```python
reader = PdfReader("input.pdf")
writer = PdfWriter()
for page in reader.pages:
    writer.add_page(page)
writer.encrypt("userpassword", "ownerpassword")
with open("encrypted.pdf", "wb") as f:
    writer.write(f)
```

---

## Quick Reference

| Task             | Tool          | Command/Code            |
| ---------------- | ------------- | ----------------------- |
| Merge PDFs       | pypdf         | `writer.add_page(page)` |
| Split PDFs       | pypdf         | One page per file       |
| Extract text     | pdfplumber    | `page.extract_text()`   |
| Extract tables   | pdfplumber    | `page.extract_tables()` |
| OCR scanned PDFs | pytesseract   | Convert to image first  |
| Create PDFs      | reportlab     | Canvas or Platypus      |
| Fill PDF forms   | pdf-lib/pypdf | see `forms.md`          |

---

## Notes

* Large PDFs: Use **batch processing** to avoid memory or API limits.
* Advanced JS libraries: see `reference.md`.
* For forms and interactive PDFs: see `forms.md`.

```
