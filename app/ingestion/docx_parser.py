from typing import List, Tuple
from docx import Document
from docx.oxml.ns import qn
import io
import logging

logger = logging.getLogger(__name__)

def extract_text_from_docx(file_bytes: bytes) -> List[Tuple[int, str]]:
    """
    Extract text from DOCX bytes, returning a list of (page_number, text) tuples.
    Page number estimation: every 50 paragraphs = 1 page.
    """
    try:
        doc = Document(io.BytesIO(file_bytes))
    except Exception as e:
        logger.error(f"Failed to open DOCX: {e}")
        raise ValueError("Invalid or corrupted DOCX file.") from e
        
    pages = []
    current_page = 1
    current_text = []
    
    for i, para in enumerate(doc.paragraphs):
        style_name = para.style.name if para.style else ""
        text = para.text
        
        if not text.strip():
            continue
            
        if style_name.startswith('Heading'):
            try:
                level = int(style_name.replace('Heading ', ''))
                text = f"{'#' * level} {text}"
            except ValueError:
                text = f"# {text}"
            # Heading paragraphs always flush to their own page boundary
            current_text.append(text)

        else:
            current_text.append(text)

        if (i + 1) % 50 == 0:
            pages.append((current_page, "\n\n".join(current_text)))
            current_page += 1
            current_text = []

    if current_text:
        pages.append((current_page, "\n\n".join(current_text)))
        
    if not pages:
        return [(1, "")]
        
    return pages
