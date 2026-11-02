# Construction Change-Order Extraction Pipeline

A modular document-extraction pipeline that converts messy construction Change Order PDFs and raw OCR text into strictly validated JSON with **calibrated per-field confidence scores** and deterministic accounting reconciliation.

---

## 1. Architecture & Approach

Construction change orders (AIA G701, PCOs, field directives) frequently arrive as degraded scans containing OCR character substitutions (`$4,5OO.OO` instead of `$4,500.00`), image-only pages with no text layer, or contractor arithmetic errors. Rather than relying on raw LLM self-reported confidence (which is notoriously overconfident on hallucinations and silent math fixes), this pipeline separates **extraction**, **deterministic verification**, and **multi-signal confidence calibration** into four stages:

```text
PDF / Text Input
  │
  ▼
[1. Ingestor (ingestor.py)]
  ├── Extracts text layers + renders 200 DPI page PNGs via PyMuPDF (fitz)
  ├── Detects image-only scanned PDFs and routes them to multimodal vision (0.90 quality score)
  ├── Estimates OCR noise ratio & document_quality_score (detecting OCR character glitches)
  │
  ▼
[2. Structured Extractor (llm_extractor.py)]
  ├── Primary: Gemini 2.5 Flash multimodal (text + page images) with strict JSON Schema
  ├── Fallback: Deterministic regex + OCR-glitch-aware hybrid parser (offline mode)
  ├── Enforces AIA G701 date semantics ('Date of Issuance' vs historical 'Contract Date')
  └── Prompt enforces verbatim extraction (never silently fixing contractor math errors)
  │
  ▼
[3. Accounting Validator (validator.py)]
  ├── Check 1 (Line-Item Math): quantity × unit_price == total_amount
  ├── Check 2 (Subtotal Roll-Up): sum(line_items.total_amount) == cost_summary.subtotal
  ├── Check 3 (Cost Summary): subtotal + overhead_and_profit + tax_amount == total_change_order_amount
  ├── Check 4 (Contract Roll-Forward): original + previous_changes == prior_sum; prior_sum + this_co == new_sum
  └── Check 5 (Cross-Section Consistency): cost_summary.total == contract_reconciliation.this_co
  │
  ▼
[4. Multi-Signal Confidence Calibrator (confidence.py)]
  ├── Combines 4 signals per field into a calibrated [0.0, 1.0] score
  ├── Blends line-item row confidences into document-level overall confidence
  ├── Caps overall confidence <= 0.55 on CRITICAL math errors (preventing overconfidence on corrupted tables)
  ├── Distinguishes unstated optional fees with IMPLICIT_ZERO_NOT_STATED (no grounding penalty)
  └── Sets needs_human_review = True if any critical financial field < 0.80 or math validation fails
```

### Multi-Signal Per-Field Confidence Formula

Every extracted attribute is wrapped in `ScoredField[T]`, containing `value`, `confidence`, `evidence_quote`, `source_page`, `signals`, and `flags`. Final confidence is computed as:

$$\text{Confidence} = 0.30 \cdot S_{\text{llm}} + 0.30 \cdot S_{\text{grounding}} + 0.25 \cdot S_{\text{consistency}} + 0.15 \cdot S_{\text{doc}}$$

- **$S_{\text{llm}}$ (30%)**: Raw extractor confidence, penalized when OCR character substitutions (`O`/`0`, `I`/`1`) are detected.
- **$S_{\text{grounding}}$ (30%)**: Verifies whether the `evidence_quote` and normalized value appear in the document text (`1.0` exact quote match, `0.90` normalized value match, `0.92` multimodal vision match on scanned image-only PDFs, `0.85` implicit zero not stated, `0.45` weak grounding).
- **$S_{\text{consistency}}$ (25%)**: Starts at `1.0`; drops to `0.30` if any `MATH_*` anomaly flag is attached by the accounting validator, or `0.55` if an `OCR_*` glitch flag is present.
- **$S_{\text{doc}}$ (15%)**: Document scan quality score derived from OCR noise density or image resolution.
- **Hard Caps**: Any field with a `MATH_*` mismatch flag is hard-capped at `<= 0.40` confidence, and any field with an `OCR_*` substitution flag is capped at `<= 0.65`. If any critical accounting check fails, `overall_confidence` is capped at `<= 0.55`, ensuring arithmetic discrepancies always trigger human review.

---

## 2. Where It Breaks (Failure Modes & Limitations)

1. **Complex Multi-Column Quantity Schedules (Civil vs. Vertical Construction)**
   - *Where it breaks*: Civil engineering change orders (e.g. municipal road/drainage projects) frequently display 9-column schedules: `[ITEM | DESCRIPTION | UNIT | BASE QTY | QTY INCREASE | QTY DECREASE | UNIT PRICE | COST INCREASE | COST DECREASE]`.
   - *Impact*: Standard vision prompts can associate the original baseline quantity with the change row instead of net change $(\Delta Q)$, or misalign blank decrease cells across wide tables. The pipeline mitigates this by enforcing `sum(line_items) == subtotal` roll-up checks, catching mismatches immediately.
2. **Multi-Page Split Tables & Complex Nested Sub-Tables**
   - *Where it breaks*: Change orders spanning 5+ pages where line-item tables break mid-row across page boundaries, or include nested T&M (Time & Materials) labor breakdown appendices alongside summary rows.
   - *Impact*: The extractor may double-count sub-schedule items along with summary rows, causing `MATH_SUBTOTAL_MISMATCH` false positives.
3. **Handwritten Field Directives & Strikethrough Redlines**
   - *Where it breaks*: Project managers often cross out unit prices by hand and initial a new number in the margin on jobsite PCOs.
   - *Impact*: Scanned digital text layers miss handwriting completely. While multimodal vision captures the pen strokes, vision models can confuse whether the struck-through number or the handwritten margin number represents the active legal value.
4. **Lump-Sum / Percentage Unit Conventions & Retention/Deducts**
   - *Where it breaks*: Construction tables often list `1 LS` (Lump Sum), percentage markups (`15%` in the quantity column), or deductive change orders formatted with accounting parentheses `($1,200.00)` or trailing `CR` (Credit).
   - *Impact*: Naive `quantity * unit_price == total_amount` validation fails when `quantity` represents a percentage (`15`) rather than a multiplier (`0.15`), or when credit notation `CR` is parsed as a positive float.
5. **Tiered Markups Outside Standard `CostSummary` Buckets**
   - *Where it breaks*: General contractors frequently add tiered markups (Bond & Insurance `1.5%`, GC Fee `5%`, Subguard `1.2%`) between Subtotal and Total Change Order Amount.
   - *Impact*: Because `CostSummary` models `subtotal`, `overhead_and_profit`, and `tax_amount`, multi-tiered markups must be consolidated into `overhead_and_profit` to satisfy `subtotal + O&P + tax == total`.

---

## 3. Quickstart & Usage

### Prerequisites
- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/)
- Optional: `GEMINI_API_KEY` in `.env` for live multimodal Gemini extraction (falls back to offline hybrid parser if omitted)

### Install Dependencies & Generate Samples
```bash
uv sync
uv run python scripts/generate_samples.py
uv run python scripts/download_samples.py
```

### Run the CLI
```bash
# Interactive mode (prompts to choose [1] Gemini API or [2] Offline Hybrid)
uv run python -m change_order_extractor.cli samples/co_01_clean.pdf

# Directly specify provider ('gemini', 'offline', or 'auto')
uv run python -m change_order_extractor.cli samples/co_01_clean.pdf --provider gemini

# Test on real-world executed change order PDFs
uv run python -m change_order_extractor.cli samples/real/aia_g701_wheaton.pdf --provider gemini
uv run python -m change_order_extractor.cli samples/real/deductive_brookline.pdf --provider gemini
uv run python -m change_order_extractor.cli samples/real/civil_table_norman.pdf --provider gemini
```
Validated JSON outputs are printed to stdout and automatically saved to `outputs/<sample_name>.json`.

### Run Automated Tests
```bash
uv run pytest -v
```

---

## 4. Benchmark Evaluation & Real-World Test Cases

### Synthetic Test Scenarios
| Sample File | Scenario | Validated Output | Overall Confidence | Human Review | Notes |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `samples/co_01_clean.pdf` | Clean AIA structural steel CO | `outputs/co_01_clean.json` | `1.000` | `False` | 100% precision on header, lines, and reconciliation. |
| `samples/co_02_ocr_scan.pdf` | Degraded scan with `$4,5OO.OO`, `2O LF` | `outputs/co_02_ocr_scan.json` | `0.889` | `True` | Caught OCR character substitutions; penalizes confidence. |
| `samples/co_03_math_error.pdf` | Contractor math error (`40 * $85 = $3,800`) | `outputs/co_03_math_error.json` | `0.932` | `True` | Total capped at `0.45`; flagged `MATH_LINE_ITEM_MISMATCH`. |

### Real-World Executed Change Orders
| Real-World Document | Origin & Document Type | Validated Output | Overall Confidence | Validation Result | Human Review |
| :--- | :--- | :--- | :---: | :---: | :---: |
| `samples/real/aia_g701_wheaton.pdf` | **Wheaton Park District**<br>Official 2-Page AIA G701 + Itemized COR ($11,885.00) | `outputs/aia_g701_wheaton.json` | `0.943` (94.3%) | **VALID** (All 3 items + O&P match) | `False` |
| `samples/real/deductive_brookline.pdf` | **Town of Brookline**<br>Executed AIA G701 Deductive Credit (-$107,965.00) | `outputs/deductive_brookline.json` | `1.000` (100.0%) | **VALID** (Contract roll-forward match) | `False` |
| `samples/real/civil_table_norman.pdf` | **City of Norman, OK**<br>Civil 9-Column Unit-Price Table ($90,749.00 net change) | `outputs/civil_table_norman.json` | `0.550` (55.0%) | **FLAGGED** (`MATH_SUBTOTAL_MISMATCH` + $2.00 source discrepancy) | `True` |


---

## 5. Engineering Assessment & Production Roadmap

### Assessment
This pipeline is an end-to-end functional prototype demonstrating practical document engineering: deterministic accounting reconciliation, multimodal vision extraction, and multi-signal confidence calibration. Benchmarking on actual executed AIA G701 forms proves strong fidelity on standard vertical building workflows (`Wheaton` 94.3%, `Brookline` 100.0%). 

However, testing against complex civil infrastructure schedules (`Norman` 55.0%) highlights that zero-shot LLM vision alone is insufficient for wide, multi-column tables with blank delta cells. The deterministic validator successfully caught and flagged the accounting mismatch (`$167k` line-item sum vs `$90.7k` net change, plus the native `$2.00` municipal sum discrepancy), preventing bad data from silently entering ERP systems.

### What is Needed for Full Commercial Production
1. **Dedicated Table Grid Reconstruction**: Integrate spatial table extraction (e.g., Table Transformer / layout-aware token bounding boxes) prior to LLM value assignment to prevent horizontal column bleed on wide civil tables.
2. **Evaluation Suite (50+ Real Documents)**: Expand regression testing to a labeled benchmark dataset with field-level Precision, Recall, and Table F1 metrics across varied contractor templates.
3. **Traceable Evidence & Provenance**: Render bounding-box coordinates on PDF image layers to provide visual audit trails for human reviewers in a web UI.
4. **Production Operations**: Wrap the pipeline in an async worker architecture (Celery/FastAPI/Redis), OpenTelemetry tracing, and encrypted credential management.
