import hashlib
import io
import re
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
import pypdf
import docx


def compute_content_hash(content: bytes | str) -> str:
    """Compute SHA-256 hash of content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def clean_text(text: str) -> str:
    """Normalize whitespace and strip unprintable characters while preserving paragraph breaks."""
    if not text:
        return ""
    # Replace non-breaking spaces and tabs
    text = text.replace("\xa0", " ").replace("\t", " ")
    # Replace consecutive spaces on a line
    text = re.sub(r"[ \t]+", " ", text)
    # Normalize multiple newlines to max 2
    text = re.sub(r"\n\s*\n\s*", "\n\n", text)
    return text.strip()


def extract_metadata_from_text(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Look for academic year or dates in text using pattern matching.
    Never invents dates. If not found, returns (None, None).
    """
    academic_year = None
    publication_date = None

    # Academic year pattern, e.g., 2023/2024, 2024/25, 2025/2026, 2016/2017 E.C.
    ay_match = re.search(
        r"\b(20\d{2}[/-](?:20)?\d{2}(?:\s*(?:E\.?C\.?|A\.?Y\.?|G\.?C\.?))?)\b",
        text,
        re.IGNORECASE,
    )
    if ay_match:
        academic_year = ay_match.group(1).strip()

    # Publication date pattern, e.g. "October 15, 2024" or "15/10/2024" or "2024-09-01"
    date_match = re.search(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+20\d{2}\b",
        text,
        re.IGNORECASE,
    )
    if not date_match:
        date_match = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", text)

    if date_match:
        publication_date = date_match.group(0).strip()

    return academic_year, publication_date


def extract_html_content(html_content: str, base_url: str = "") -> Dict[str, any]:
    """
    Extract readable main content from HTML.
    Strips navigation menus, scripts, styles, footers, sidebars, and menu containers.
    Also extracts PDF links.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Extract title before decomposing
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    elif soup.h1:
        title = soup.h1.get_text().strip()

    # Extract PDF links on the page before decomposing
    pdf_links: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().endswith(".pdf") or ".pdf?" in href.lower():
            pdf_links.append(href)

    # Remove script, style, nav, footer, header, aside, form elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg"]):
        tag.decompose()

    # Remove menu and sidebar containers
    for tag in soup.find_all(class_=re.compile(r"maximenuck|art-menu|\bmenu\b|\bnav\b|sidebar|breadcrumb|pagination", re.I)):
        tag.decompose()

    # Prefer main content containers if present and containing substantial text
    main_el = soup.find("main") or soup.find("article") or soup.find(id=re.compile(r"content|main", re.I)) or soup.find(class_=re.compile(r"content|main|article|post|item-page", re.I))
    if main_el and len(main_el.get_text().strip()) >= 50:
        target = main_el
    else:
        target = soup.body or soup

    raw_text = target.get_text(separator="\n")
    cleaned = clean_text(raw_text)

    ay, pub_date = extract_metadata_from_text(cleaned)

    return {
        "title": title or "ASTU Webpage",
        "text": cleaned,
        "content_hash": compute_content_hash(cleaned),
        "pdf_links": pdf_links,
        "academic_year": ay,
        "publication_date": pub_date,
        "requires_ocr": len(cleaned) < 30,
    }


def extract_pdf_content(pdf_bytes: bytes, filename: str = "document.pdf") -> Dict[str, any]:
    """
    Extract text from PDF using pypdf.
    Detects scanned or empty PDFs (where extracted text is empty or nearly empty).
    """
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        num_pages = len(reader.pages)
        page_texts: List[str] = []

        for page in reader.pages:
            try:
                t = page.extract_text() or ""
                page_texts.append(t)
            except Exception:
                page_texts.append("")

        full_text = clean_text("\n\n".join(page_texts))

        # Check for scanned or nearly empty PDF
        # If total text is less than 50 characters or average per page < 15 characters
        is_scanned_or_empty = False
        if num_pages > 0:
            avg_chars = len(full_text) / num_pages
            if len(full_text) < 50 or avg_chars < 15:
                is_scanned_or_empty = True
        else:
            is_scanned_or_empty = True

        title = filename
        if reader.metadata and reader.metadata.title:
            title = reader.metadata.title.strip() or filename

        ay, pub_date = extract_metadata_from_text(full_text)

        return {
            "title": title,
            "text": full_text,
            "content_hash": compute_content_hash(full_text if full_text else pdf_bytes),
            "num_pages": num_pages,
            "requires_ocr": is_scanned_or_empty,
            "academic_year": ay,
            "publication_date": pub_date,
        }
    except Exception as e:
        return {
            "title": filename,
            "text": "",
            "content_hash": compute_content_hash(pdf_bytes),
            "num_pages": 0,
            "requires_ocr": True,
            "error": f"Failed to parse PDF: {str(e)}",
            "academic_year": None,
            "publication_date": None,
        }


def extract_docx_content(docx_bytes: bytes, filename: str = "document.docx") -> Dict[str, any]:
    """Extract text from DOCX files."""
    try:
        doc = docx.Document(io.BytesIO(docx_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

        # Also extract table text
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    paragraphs.append(row_text)

        full_text = clean_text("\n\n".join(paragraphs))
        ay, pub_date = extract_metadata_from_text(full_text)

        return {
            "title": filename,
            "text": full_text,
            "content_hash": compute_content_hash(full_text),
            "requires_ocr": len(full_text) < 20,
            "academic_year": ay,
            "publication_date": pub_date,
        }
    except Exception as e:
        return {
            "title": filename,
            "text": "",
            "content_hash": compute_content_hash(docx_bytes),
            "requires_ocr": False,
            "error": f"Failed to parse DOCX: {str(e)}",
            "academic_year": None,
            "publication_date": None,
        }


def extract_txt_content(txt_bytes: bytes, filename: str = "document.txt") -> Dict[str, any]:
    """Extract text from plain text file with encoding fallback."""
    for encoding in ("utf-8", "latin-1", "utf-16"):
        try:
            raw_text = txt_bytes.decode(encoding)
            cleaned = clean_text(raw_text)
            ay, pub_date = extract_metadata_from_text(cleaned)
            return {
                "title": filename,
                "text": cleaned,
                "content_hash": compute_content_hash(cleaned),
                "requires_ocr": len(cleaned) == 0,
                "academic_year": ay,
                "publication_date": pub_date,
            }
        except UnicodeDecodeError:
            continue

    return {
        "title": filename,
        "text": "",
        "content_hash": compute_content_hash(txt_bytes),
        "requires_ocr": False,
        "error": "Failed to decode text file with supported encodings.",
        "academic_year": None,
        "publication_date": None,
    }
