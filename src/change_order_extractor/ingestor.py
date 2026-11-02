import re
from dataclasses import dataclass, field
from pathlib import Path
import pymupdf as fitz
from .schemas import DocumentQualityReport

@dataclass
class IngestedDocument:
    source_filename:str
    source_type:str
    pages:list[str]
    full_text:str
    quality_report:DocumentQualityReport
    page_images_png:list[bytes] = field(default_factory=list)

OCR_NOISE_PATTERNS = [
    re.compile(r"\$[\d,]*[OIl][\d,.]*"),  # e.g. "$14,5OO.00", "$l,250.00", "$85.I0"
    re.compile(r"\b\d+[OIl]\d*\b"),       # e.g. "2O" (20 hours), "1O5" (105), "4l" (41), "1O/05/2026"
    re.compile(r"\[\s*(?:illegible|unclear)\s*\]", re.IGNORECASE),  # e.g. "[illegible]", "[ UNCLEAR ]"
    re.compile(r"~{2,}|\?{3,}"),          # e.g. "~~~" (scanner smudge lines) or "???" (garbled text)
]


def estimate_ocr_noise(text:str) -> tuple[float,list[str]]:
    if not text.strip():
        return 1.0,["Empty document"]
    
    words = text.split()
    noise_hits = 0 
    notes:list[str] = []

    for pattern in OCR_NOISE_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            noise_hits += len(matches)
            notes.append(f"Detected OCR glitches ({len(matches)}x):{matches[:3]}")
        
    noise_ratio = min(1.0,(noise_hits * 4.0) / max(len(words),20))
    # noise_hits * 4.0      -> Give each OCR glitch a 4x penalty weight.
    # / max(len(words), 20) -> Divide by total word count (with a minimum floor of 20 words).
    # min(1.0, ...)         -> Cap the final ratio at a maximum of 1.0.
    return round(noise_ratio,4), notes


def ingest_text(text:str, source_filename:str = "inline.txt")->IngestedDocument:
    noise_ratio, notes = estimate_ocr_noise(text)
    quality_score = round(max(0.15,1.0 - noise_ratio),4)

    report = DocumentQualityReport(
        source_filename = source_filename,
        source_type = "raw_text",
        page_count = 1,
        total_characters = len(text),
        estimated_ocr_noise_ratio = noise_ratio,
        document_quality_score = quality_score,
        quality_notes = notes,
        )
    return IngestedDocument(
        source_filename = source_filename,
        source_type = "raw_text",
        pages = [text.strip()],
        full_text = text,
        quality_report = report,
        )

def ingest_file(file_path:str | Path) -> IngestedDocument:
    path = Path(file_path)
    if path.suffix.lower() != ".pdf":
        return ingest_text(path.read_text(encoding="utf-8"),
        source_filename = path.name)

    doc = fitz.open(str(path))
    pages = [page.get_text("text",sort = True).strip() for page in doc]
    full_text = "\n\n".join(pages)
    noise_ratio,notes = estimate_ocr_noise(full_text)

    page_images:list[bytes] = []

    if noise_ratio>0.1 or any(len(p)<60 for p in pages):
        for page in doc:
            page_images.append(page.get_pixmap(dpi=150).tobytes("png"))
    doc.close()
    quality_score = round(max(0.15, 1.0 - noise_ratio), 4)
    report = DocumentQualityReport(
        source_filename = path.name,
        source_type = "pdf",
        page_count = len(pages),
        total_characters = len(full_text),
        estimated_ocr_noise_ratio = noise_ratio,
        document_quality_score = quality_score,
        quality_notes = notes,
        )

    return IngestedDocument(
        source_filename = path.name,
        source_type = "pdf",
        pages = pages,
        full_text = full_text,
        quality_report = report,
        page_images_png = page_images,
        ) 





    