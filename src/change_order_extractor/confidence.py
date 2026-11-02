from typing import Any
from .ingestor import estimate_ocr_noise
from .schemas import(
    ChangeOrderExtraction,
    ConfidenceSignals,
    DocumentQualityReport,
    ScoredField,
    ValidationReport
)

def compute_grounding_score(value:Any, evidence_quote:str|None, source_text:str) -> tuple[float,list[str]]:
    flags:list[str] = []
    if value is None:
        return 0.8,flags
    if not evidence_quote or not evidence_quote.strip():
        return 0.3,["MISSING_EVIDENCE_QUOTE"]

    if evidence_quote.strip().lower() in source_text.lower():
        score = 1.0

    else:
        score = 0.4
        flags.append("WEAK_SOURCE_GROUNDING")

    noise,_ = estimate_ocr_noise(evidence_quote)
    if noise > 0.0:
        score =  max(0.3,score - 0.35)
        flags.append("OCR_CORRUPTED_EVIDENCE")

    return round(score,4) , flags

def calibrate_field(field_obj: ScoredField[Any], source_text: str, doc_quality: DocumentQualityReport,) -> float:
    llm_conf = field_obj.confidence
    grounding_score,g_flags = compute_grounding_score(field_obj.value, field_obj.evidence_quote, source_text)


    has_math_error = any(f.startswith("MATH_") for f in field_obj.flags)
    consistency_score = 0.35 if has_math_error else 1.0
    doc_score = doc_quality.document_quality_score
    for flag in g_flags:
        if flag not in field_obj.flags:
            field_obj.flags.append(flag)

    final_score = ( 0.3 * llm_conf + 0.3 * grounding_score + 0.25 * consistency_score + 0.15 * doc_score)

    if has_math_error:
        final_score = min(final_score,0.45)
    elif "OCR_CORRUPTED_EVIDENCE" in field_obj.flags or "OCR_DIGIT_SUBSTITUTION" in field_obj.flags:
        final_score = min(final_score,0.65)

    field_obj.confidence = round(final_score,4)
    field_obj.signals = ConfidenceSignals(
        llm_self_confidence = round(llm_conf,4),
        grounding_score = round(grounding_score,4),
        consistency_score = round(consistency_score,4),
        document_quality_score = round(doc_score,4),
    )

    return field_obj.confidence

def calibrate_extraction(extraction:ChangeOrderExtraction,source_text:str,doc_quality:DocumentQualityReport,validation_report:ValidationReport,review_threshold:float = 0.80,) -> tuple[float,bool,list[str]]:
    cs = extraction.cost_summary
    cr = extraction.contract_reconciliation

    all_fields = [
        extraction.change_order_number,
        extraction.project_name,
        extraction.project_number,
        extraction.title,
        extraction.status,
        extraction.issue_date,
        extraction.effective_or_approval_date,
        extraction.reason_for_change,
        extraction.scope_of_work_summary,
        extraction.owner_name,
        extraction.general_contractor_name,
        extraction.subcontractor_name,
        extraction.schedule_impact_days,
        cs.subtotal,
        cs.overhead_and_profit,
        cs.tax_amount,
        cs.total_change_order_amount,
        cr.original_contract_sum,
        cr.net_change_by_previous_change_orders,
        cr.contract_sum_prior_to_this_change_order,
        cr.this_change_order_amount,
        cr.new_contract_sum_including_this_change_order,
    ]

    for f in all_fields:
        calibrate_field(f,source_text,doc_quality)

    for item in extraction.line_items:
        row_fields = [
            item.item_number,
            item.description,
            item.category,
            item.quantity,
            item.unit,
            item.unit_price,
            item.total_amount,
        ]

        scores = [calibrate_field(rf,source_text,doc_quality) for rf in row_fields]
        item.row_confidence = round(sum(scores)/len(scores),4)

    critical_fields = [
        ("change_order_number", extraction.change_order_number),
        ("project_name", extraction.project_name),
        ("cost_summary.subtotal", cs.subtotal),
        ("cost_summary.total_change_order_amount",cs.total_change_order_amount)
    ]

    overall_confidence = round(sum(f.confidence for _, f in critical_fields)/len(critical_fields),4)

    review_reasons:list[str] = []

    if not validation_report.is_valid:
        for anomaly in validation_report.anomalies:
            review_reasons.append(f"[{anomaly.code}]{anomaly.message}")

    for name,f in critical_fields:
        if f.confidence < review_threshold:
            review_reasons.append(
                f"Low confidence on {name} ({f.confidence}<{review_threshold})"
            )

    if doc_quality.estimated_ocr_noise_ratio >= 0.1:
        review_reasons.append("High OCR noise detected in document") 

    needs_human_review = len(review_reasons) > 0 or overall_confidence < review_threshold

    return overall_confidence, needs_human_review, review_reasons
