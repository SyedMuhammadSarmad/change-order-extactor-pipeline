# Construction Change-Order Extraction Pipeline

A modular document-extraction pipeline that converts messy construction Change Order PDFs and raw OCR text into strictly validated JSON with **calibrated per-field confidence scores** and deterministic accounting reconciliation.

---

## 1. Architecture & Approach

Construction change orders (AIA G701, PCOs, field directives) frequently arrive as degraded scans containing OCR character substitutions (`$4,5OO.OO` instead of `$4,500.00`), missing metadata, or contractor arithmetic errors. Rather than relying on raw LLM self-reported confidence (which is notoriously overconfident on hallucinations and silent math fixes), this pipeline separates **extraction**, **deterministic verification**, and **multi-signal confidence calibration** into four stages:

```text
PDF / Text Input
  │
  ▼
[1. Ingestor (ingestor.py)]
  ├── Extracts text layers + renders 2x DPI page PNGs via PyMuPDF (fitz)
  └── Estimates OCR noise ratio & document_quality_score (detecting $O/0, I/1, [illegible])
  │
  ▼
[2. Structured Extractor (llm_extractor.py)]
  ├── Primary: Gemini 2.5 Flash multimodal (text + page images) with strict JSON Schema
  ├── Fallback: Deterministic regex + OCR-glitch-aware hybrid parser (offline mode)
  └── Prompt enforces verbatim extraction (never silently fixing contractor math errors)
  │
  ▼
[3. Accounting Validator (validator.py)]
  ├── Check 1 (Line-Item Math): quantity × unit_price == total_amount
  ├── Check 2 (Subtotal Roll-up): sum(line_items.total_amount) == cost_summary.subtotal
  ├── Check 3 (Cost Summary): subtotal + overhead_and_profit + tax_amount == total_change_order_amount
  ├── Check 4 (Contract Roll-forward): original + previous_changes == prior_sum; prior_sum + this_co == new_sum
  └── Check 5 (Cross-Section Consistency): cost_summary.total == contract_reconciliation.this_co
  │
  ▼
[4. Multi-Signal Confidence Calibrator (confidence.py)]
  ├── Combines 4 signals per field into a calibrated [0.0, 1.0] score
  └── Sets needs_human_review = True if any critical financial field < 0.80 or math validation fails
```

### Multi-Signal Per-Field Confidence Formula

Every extracted attribute is wrapped in `ScoredField[T]`, containing `value`, `confidence`, `evidence_quote`, `source_page`, `signals`, and `flags`. Final confidence is computed as:

$$\text{Confidence} = 0.30 \cdot S_{\text{llm}} + 0.30 \cdot S_{\text{grounding}} + 0.25 \cdot S_{\text{consistency}} + 0.15 \cdot S_{\text{doc\_quality}}$$

- **$S_{\text{llm}}$ (30%)**: Raw extractor confidence, penalized when OCR character substitutions (`O`/`0`, `I`/`1`) are detected.
- **$S_{\text{grounding}}$ (30%)**: Verifies whether the `evidence_quote` and normalized value actually appear in the source document text (`1.0` exact quote match, `0.85` normalized value match, `0.40` unverified quote).
- **$S_{\text{consistency}}$ (25%)**: Starts at `1.0`; drops to `0.35` if any `MATH_*` anomaly flag is attached by the accounting validator, or `0.55` if an `OCR_*` glitch flag is present.
- **$S_{\text{doc\_quality}}$ (15%)**: Document-level scan quality score derived from OCR noise density.
- **Hard Caps**: Any field with a `MATH_*` mismatch flag is hard-capped at `<= 0.45` confidence, and any field with an `OCR_*` substitution flag is capped at `<= 0.65`, guaranteeing that arithmetic errors and OCR ambiguities always trigger human review.

---

## 2. Where It Breaks (Failure Modes & Limitations)

1. **Multi-Page Split Tables & Complex Nested Sub-Tables**
   - *Where it breaks*: Change orders spanning 5+ pages where line-item tables break mid-row across page boundaries, or include nested T&M (Time & Materials) labor breakdown appendices alongside summary rows.
   - *Impact*: The extractor may double-count sub-schedule items along with summary rows, causing `MATH_SUBTOTAL_MISMATCH` false positives.
2. **Handwritten Field Directives & Strikethrough Redlines**
   - *Where it breaks*: Project managers often cross out unit prices by hand and initial a new number in the margin on jobsite PCOs.
   - *Impact*: PyMuPDF's text layer misses handwriting completely, and vision models occasionally extract both the struck-through number and the handwritten number or confuse which one is active. Furthermore, `compute_grounding_score` penalizes visual-only extractions when the PDF text layer is empty or corrupted.
3. **Lump-Sum / Percentage Unit Conventions & Retention/Deducts**
   - *Where it breaks*: Construction tables often list `1 LS` (Lump Sum), percentage markups (`15%` in the quantity column), or deductive change orders formatted with accounting parentheses `($1,200.00)` or trailing `CR` (Credit).
   - *Impact*: Naive `quantity * unit_price == total_amount` validation fails when `quantity` represents a percentage (`15`) rather than a multiplier (`0.15`), or when credit notation `CR` is parsed as a positive float.
4. **Implicit Markups Not Captured in `CostSummary` Fixed Buckets**
   - *Where it breaks*: General contractors frequently add tiered markups (Bond & Insurance `1.5%`, GC Fee `5%`, Subguard `1.2%`) between Subtotal and Total Change Order Amount.
   - *Impact*: Because `CostSummary` currently models `subtotal`, `overhead_and_profit`, and `tax_amount`, unmodeled fee lines either get dropped or lumped together, breaking Check 3 (`subtotal + O&P + tax == total`).

---

## 3. Quickstart & Usage

### Prerequisites
- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/)
- Optional: `GEMINI_API_KEY` in `.env` for live multimodal Gemini extraction (falls back to offline hybrid parser if omitted)

### Install Dependencies & Generate Sample PDFs
```bash
uv sync
uv run python scripts/generate_samples.py
```

### Run the CLI
```bash
# Interactive mode (prompts to choose [1] Gemini API or [2] Offline Hybrid)
uv run python -m change_order_extractor.cli samples/co_01_clean.pdf

# Directly specify provider ('gemini', 'offline', or 'auto')
uv run python -m change_order_extractor.cli samples/co_01_clean.pdf --provider gemini
uv run python -m change_order_extractor.cli samples/co_02_ocr_scan.pdf --provider gemini
uv run python -m change_order_extractor.cli samples/co_03_math_error.pdf --provider gemini
```
Validated JSON outputs are printed to stdout and automatically saved to `outputs/<sample_name>.json`.

### Run Automated Tests
```bash
uv run pytest -v
```

---

## 4. Sample Scenarios Included

| Sample File | Scenario | Validated Output | Overall Confidence | Human Review |
| :--- | :--- | :--- | :---: | :---: |
| `samples/co_01_clean.pdf` | Clean AIA-style structural steel CO | `outputs/co_01_clean.json` | `1.000` | `False` |
| `samples/co_02_ocr_scan.pdf` | Noisy scan with `$4,5OO.OO`, `2O LF`, `[illegible]` | `outputs/co_02_ocr_scan.json` | `0.896` | `True` (OCR glitches & illegible subcontractor) |
| `samples/co_03_math_error.pdf` | Contractor math error (`40 * $85 = $3,800` instead of `$3,400`) | `outputs/co_03_math_error.json` | `0.955` (Total capped at `0.45`) | `True` (`MATH_LINE_ITEM_MISMATCH`, `MATH_SUBTOTAL_MISMATCH`) |

