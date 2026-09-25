from typing import List, Tuple
import pymupdf as fitz  # PyMuPDF (modern import)
import logging


logger = logging.getLogger(__name__)

def extract_text_from_pdf(file_bytes: bytes) -> List[Tuple[int, str]]:
    """
    Extract text from PDF bytes, returning a list of (page_number, text) tuples.
    Page numbers are 1-indexed.
    Raises ValueError on invalid PDF.
    """
    pages_text = []
    try:
        doc = fitz.open(stream=file_bytes, filetype='pdf')
    except Exception as e:
        logger.error(f"Failed to open PDF: {e}")
        raise ValueError("Invalid or corrupted PDF file.") from e

    if doc.is_encrypted:
        try:
            doc.authenticate("")
        except Exception:
            pass
        if doc.is_encrypted:
            logger.error("PDF is encrypted and could not be unlocked.")
            raise ValueError("PDF is encrypted and cannot be processed.")

    for i in range(len(doc)):
        page = doc.load_page(i)
        text = page.get_text('text')
        if text:
            pages_text.append((i + 1, text))
        else:
            pages_text.append((i + 1, ""))
            
    doc.close()
    return pages_text
