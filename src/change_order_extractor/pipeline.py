from pathlib import Path
from .confidence import calibrate_extraction
from .ingestor import IngestedDocument, ingest_file, ingest_text
from .llm_extractor import extract_with_provider
from .schemas import ExtractionPipelineResult
from .validator import validate_extraction


class ChangeOrderPipeline:
    def __init__(
        self, provider: str = "auto", review_threshold: float = 0.80
    ) -> None:
        self.provider = provider
        self.review_threshold = review_threshold

    def run_on_document(self, doc: IngestedDocument) -> ExtractionPipelineResult:
        extraction, provider_used = extract_with_provider(doc, provider=self.provider)
        validation_report = validate_extraction(extraction)

        overall_confidence, needs_human_review, review_reasons = calibrate_extraction(extraction=extraction, 
        source_text=doc.full_text, 
        doc_quality=doc.quality_report, 
        validation_report=validation_report, 
        review_threshold=self.review_threshold,)

        return ExtractionPipelineResult(
            provider_used=provider_used,
            overall_confidence=overall_confidence,
            needs_human_review=needs_human_review,
            review_reasons=review_reasons,
            document_quality=doc.quality_report,
            validation=validation_report,
            data=extraction,
        )

    def extract_file(self, file_path: str | Path) -> ExtractionPipelineResult:
        doc = ingest_file(file_path)
        return self.run_on_document(doc)

    def extract_text(
        self, text: str, source_filename: str = "inline.txt"
    ) -> ExtractionPipelineResult:
        doc = ingest_text(text, source_filename=source_filename)
        return self.run_on_document(doc)