import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

def extract_text_from_txt(file_bytes: bytes) -> List[Tuple[int, str]]:
    """
    Extract text from TXT bytes, returning a list of (page_number, text) tuples.
    Detect encoding (try UTF-8, fallback to latin-1).
    Estimate pages: every 3000 characters = 1 page.
    """
    try:
        text = file_bytes.decode('utf-8')
    except UnicodeDecodeError:
        try:
            text = file_bytes.decode('latin-1')
        except Exception as e:
            logger.error(f"Failed to decode TXT: {e}")
            raise ValueError("Invalid or unsupported text encoding.") from e

    pages = []
    current_page = 1
    current_text = ""
    
    paragraphs = text.split('\n\n')
    
    for para in paragraphs:
        if not para.strip():
            continue
            
        if len(current_text) + len(para) > 3000 and current_text:
            pages.append((current_page, current_text.strip()))
            current_page += 1
            current_text = para + "\n\n"
        else:
            current_text += para + "\n\n"
            
    if current_text.strip():
        pages.append((current_page, current_text.strip()))
        
    if not pages:
        return []
        
    return pages
