import io
import pytest
import pypdf
import docx
from app.services.extractors import (
    clean_text,
    compute_content_hash,
    extract_docx_content,
    extract_html_content,
    extract_metadata_from_text,
    extract_pdf_content,
    extract_txt_content,
)


def test_clean_text_and_content_hash():
    dirty = "  Hello   World!\xa0\xa0\tNew  line.\n\n\n\nParagraph 2.  "
    cleaned = clean_text(dirty)
    assert cleaned == "Hello World! New line.\n\nParagraph 2."

    h1 = compute_content_hash(cleaned)
    h2 = compute_content_hash(cleaned)
    assert h1 == h2
    assert len(h1) == 64


def test_extract_metadata_dates():
    sample_text = (
        "Welcome to the 2024/2025 Academic Calendar for Adama Science and Technology University. "
        "Published on October 12, 2024 by the Registrar."
    )
    ay, pub_date = extract_metadata_from_text(sample_text)
    assert ay == "2024/2025"
    assert pub_date == "October 12, 2024"

    empty_text = "No dates mentioned here."
    ay2, pub_date2 = extract_metadata_from_text(empty_text)
    assert ay2 is None
    assert pub_date2 is None


def test_extract_html_content_removes_nav_and_footer():
    html = """
    <!DOCTYPE html>
    <html>
      <head><title>ASTU Registrar</title></head>
      <body>
        <nav><a href="/home">Home</a><a href="/login">Login</a></nav>
        <header><h1>Header Navigation</h1></header>
        <main>
          <h1>Undergraduate Admission</h1>
          <p>Registration for semester 1 begins next Monday for 2024/2025.</p>
          <a href="/docs/calendar_2025.pdf">Download Academic Calendar (PDF)</a>
        </main>
        <footer><p>© 2024 ASTU. All rights reserved.</p></footer>
      </body>
    </html>
    """
    res = extract_html_content(html, base_url="https://www.astu.edu.et")
    assert "Undergraduate Admission" in res["text"]
    assert "Home" not in res["text"]
    assert "Login" not in res["text"]
    assert "All rights reserved" not in res["text"]
    assert res["title"] == "ASTU Registrar"
    assert len(res["pdf_links"]) == 1
    assert "/docs/calendar_2025.pdf" in res["pdf_links"][0]
    assert res["academic_year"] == "2024/2025"
    assert not res["requires_ocr"]


def test_extract_txt_content():
    content = "Adama Science and Technology University\nStudent Services Guide\nDean of Students."
    res = extract_txt_content(content.encode("utf-8"), filename="guide.txt")
    assert res["title"] == "guide.txt"
    assert "Student Services Guide" in res["text"]
    assert not res["requires_ocr"]


def test_extract_docx_content():
    doc = docx.Document()
    doc.add_heading("ASTU Department of CSE", level=1)
    doc.add_paragraph("Courses for second year students include Data Structures and Algorithms.")
    table = doc.add_table(rows=1, cols=2)
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "Course Code"
    hdr_cells[1].text = "Course Title"

    buf = io.BytesIO()
    doc.save(buf)
    docx_bytes = buf.getvalue()

    res = extract_docx_content(docx_bytes, filename="cse_courses.docx")
    assert res["title"] == "cse_courses.docx"
    assert "Department of CSE" in res["text"]
    assert "Data Structures" in res["text"]
    assert "Course Code | Course Title" in res["text"]
    assert not res["requires_ocr"]


def test_extract_pdf_content_with_text():
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)

    # Empty PDF should be flagged as requiring OCR
    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    res = extract_pdf_content(pdf_bytes, filename="scanned.pdf")
    assert res["requires_ocr"] is True
    assert res["text"] == ""
