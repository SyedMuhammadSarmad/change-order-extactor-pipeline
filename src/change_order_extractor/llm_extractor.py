import os
import re
import json
from typing import Any, Optional
from .ingestor import IngestedDocument
from .schemas import (
    ChangeOrderExtraction,
    ContractSumReconciliation,
    CostSummary,
    ExtractedLineItem,
    ScoredField,
)

SYSTEM_PROMPT = f"""You are an expert Construction Cost Engineer and Document Verification AI.
Extract the Change Order into a JSON object matching this exact JSON Schema:
{json.dumps(ChangeOrderExtraction.model_json_schema())}

Strict Rules:
1. Wrap every field in ScoredField with value, confidence (0.0-1.0), and verbatim evidence_quote from the text/image.
2. DATES (AIA G701 & Construction Forms):
   - `issue_date`: The date the Change Order document was issued (labeled 'DATE:' next to Change Order Number, e.g. 'November 1, 2024'). NEVER put 'CONTRACT DATE:' (the original prime contract date, e.g. 2021 or 2022) into `issue_date`!
   - `effective_or_approval_date`: The execution or signature approval date (often beside Owner/Architect signature, or effective date).
   - If a project number or status is not explicitly stated in the document, return `value: null` with `evidence_quote: null`.
3. OPTIONAL COSTS (Overhead & Profit, Tax):
   - If Overhead & Profit or Sales Tax are NOT explicitly stated as separate line items on the document, set `value: 0.0` or `null` with `evidence_quote: null`.
   - If no separate markup lines exist, set `cost_summary.subtotal` equal to `cost_summary.total_change_order_amount`.
4. MUNICIPAL CIVIL UNIT-PRICE SCHEDULES (Multi-column Quantity Increase/Decrease Tables):
   - Municipal civil tables commonly have 9 columns:
     [ITEM | DESCRIPTION | UNIT | QUANTITY | QUANTITY INCREASE | QUANTITY DECREASE | UNIT PRICE | COST INCREASE | COST DECREASE]
   - NEVER use the 4th column ('QUANTITY') — that is only the old original contract base quantity!
   - For `quantity`: Take exclusively from 'QUANTITY INCREASE' (as positive float) or 'QUANTITY DECREASE' (as negative float).
   - For `total_amount`: Take exclusively from 'COST INCREASE' (as positive float) or 'COST DECREASE' (as negative float).
   - Preserve exact 1-to-1 rows. Do not duplicate rows. Each printed table row with an Item number is one line item.
   - Double-check each row arithmetic: `quantity * unit_price == total_amount` must hold for each change item.
   - The sum of all line item `total_amount` values must equal the table Net Change / Total!
5. Do NOT silently fix contractor math errors if they are printed on the document; extract what is printed verbatim.
6. Lower confidence (< 0.65) if a number has OCR glitches like 'O' instead of '0'.
"""


def extract_with_gemini(doc: IngestedDocument, api_key: str) -> ChangeOrderExtraction:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    contents: list[Any] = [f"Extract change order from: \n\n{doc.full_text}"]

    for img_bytes in doc.page_images_png:
        contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))

    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0,
            response_mime_type="application/json",
        ),
    )

    return ChangeOrderExtraction.model_validate_json(response.text)


def parse_ocr_float(raw: Optional[str]) -> tuple[Optional[float], bool]:
    if not raw:
        return None, False
    had_glitch = bool(re.search(r"[OIl]", raw))
    cleaned = raw.replace("O", "0").replace("I", "1").replace("l", "1")
    cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
    try:
        return float(cleaned), had_glitch
    except ValueError:
        return None, had_glitch


def extract_offline(doc: IngestedDocument) -> ChangeOrderExtraction:
    text = doc.full_text

    def find_text(pattern: str) -> ScoredField[str]:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if not m:
            return ScoredField(value=None, confidence=0.75, evidence_quote=None)
        val = m.group(1).strip()
        quote = m.group(0).strip()
        conf = 0.45 if "[illegible]" in val.lower() else 0.95
        return ScoredField(value=val, confidence=conf, evidence_quote=quote)

    def find_amount(pattern: str) -> ScoredField[float]:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if not m:
            return ScoredField(value=0.0, confidence=0.80, evidence_quote=None)
        num, had_glitch = parse_ocr_float(m.group(1))
        flags = ["OCR_DIGIT_SUBSTITUTION"] if had_glitch else []
        conf = 0.60 if had_glitch else 0.95
        return ScoredField(
            value=num, confidence=conf, evidence_quote=m.group(0).strip(), flags=flags
        )

    # Extract table rows separated by "|" (e.g. 01 | Description | LABOR | 40 | HR | $85.00 | $3,400.00)
    line_items: list[ExtractedLineItem] = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) == 7 and parts[0].isdigit():
            q_val, q_gl = parse_ocr_float(parts[3])
            up_val, up_gl = parse_ocr_float(parts[5])
            tot_val, tot_gl = parse_ocr_float(parts[6])
            line_items.append(
                ExtractedLineItem(
                    item_number=ScoredField(value=parts[0], confidence=0.95, evidence_quote=line),
                    description=ScoredField(value=parts[1], confidence=0.95, evidence_quote=line),
                    category=ScoredField(value=parts[2], confidence=0.95, evidence_quote=line),
                    quantity=ScoredField(
                        value=q_val,
                        confidence=0.60 if q_gl else 0.95,
                        evidence_quote=line,
                        flags=["OCR_DIGIT_SUBSTITUTION"] if q_gl else [],
                    ),
                    unit=ScoredField(value=parts[4], confidence=0.95, evidence_quote=line),
                    unit_price=ScoredField(
                        value=up_val,
                        confidence=0.60 if up_gl else 0.95,
                        evidence_quote=line,
                        flags=["OCR_DIGIT_SUBSTITUTION"] if up_gl else [],
                    ),
                    total_amount=ScoredField(
                        value=tot_val,
                        confidence=0.60 if tot_gl else 0.95,
                        evidence_quote=line,
                        flags=["OCR_DIGIT_SUBSTITUTION"] if tot_gl else [],
                    ),
                )
            )

    sched_m = re.search(r"SCHEDULE\s*IMPACT\s*:\s*([\+\-]?\d+)", text, re.IGNORECASE)
    sched_days = int(sched_m.group(1)) if sched_m else 0
    sched_quote = sched_m.group(0).strip() if sched_m else None

    return ChangeOrderExtraction(
        change_order_number=find_text(r"CHANGE\s*ORDER\s*NO\s*:\s*(.+)"),
        project_name=find_text(r"^PROJECT\s*:\s*(.+)"),
        project_number=find_text(r"PROJECT\s*NUMBER\s*:\s*(.+)"),
        title=find_text(r"^TITLE\s*:\s*(.+)"),
        status=find_text(r"^STATUS\s*:\s*(.+)"),
        issue_date=find_text(r"ISSUE\s*DATE\s*:\s*(.+)"),
        effective_or_approval_date=find_text(r"EFFECTIVE\s*DATE\s*:\s*(.+)"),
        reason_for_change=find_text(r"REASON\s*FOR\s*CHANGE\s*:\s*(.+)"),
        scope_of_work_summary=find_text(r"SCOPE\s*OF\s*WORK\s*:\s*(.+)"),
        owner_name=find_text(r"^OWNER\s*:\s*(.+)"),
        general_contractor_name=find_text(r"GENERAL\s*CONTRACTOR\s*:\s*(.+)"),
        subcontractor_name=find_text(r"SUBCONTRACTOR\s*:\s*(.+)"),
        schedule_impact_days=ScoredField(
            value=sched_days, confidence=0.95, evidence_quote=sched_quote
        ),
        cost_summary=CostSummary(
            subtotal=find_amount(r"SUBTOTAL\s*:\s*(.+)"),
            overhead_and_profit=find_amount(r"OVERHEAD\s*AND\s*PROFIT\s*:\s*(.+)"),
            tax_amount=find_amount(r"SALES\s*TAX\s*:\s*(.+)"),
            total_change_order_amount=find_amount(r"TOTAL\s*CHANGE\s*ORDER\s*AMOUNT\s*:\s*(.+)"),
        ),
        contract_reconciliation=ContractSumReconciliation(
            original_contract_sum=find_amount(r"ORIGINAL\s*CONTRACT\s*SUM\s*:\s*(.+)"),
            net_change_by_previous_change_orders=find_amount(
                r"NET\s*CHANGE\s*BY\s*PREVIOUS\s*CHANGE\s*ORDERS\s*:\s*(.+)"
            ),
            contract_sum_prior_to_this_change_order=find_amount(
                r"CONTRACT\s*SUM\s*PRIOR\s*TO\s*THIS\s*CHANGE\s*ORDER\s*:\s*(.+)"
            ),
            this_change_order_amount=find_amount(r"THIS\s*CHANGE\s*ORDER\s*AMOUNT\s*:\s*(.+)"),
            new_contract_sum_including_this_change_order=find_amount(
                r"NEW\s*CONTRACT\s*SUM\s*INCLUDING\s*THIS\s*CHANGE\s*ORDER\s*:\s*(.+)"
            ),
        ),
        line_items=line_items,
    )


def extract_with_provider(
    doc: IngestedDocument, provider: str = "auto"
) -> tuple[ChangeOrderExtraction, str]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if provider == "gemini" or (provider == "auto" and api_key):
        return extract_with_gemini(doc, api_key), "gemini"
    return extract_offline(doc), "offline-hybrid"
