from pathlib import Path
import pymupdf as fitz

SAMPLES = {
    "co_01_clean": """CHANGE ORDER NO: CO-004
PROJECT: Apex Commercial Tower
PROJECT NUMBER: PRJ-089
TITLE: Structural Steel Reinforcement
STATUS: APPROVED
ISSUE DATE: 2026-09-15
EFFECTIVE DATE: 2026-09-22
OWNER: Horizon Partners
GENERAL CONTRACTOR: Turner Corp
SUBCONTRACTOR: Atlas Steel
REASON FOR CHANGE: Structural revision per ASI-014
SCOPE OF WORK: Furnish and weld 16 stiffener plates
01 | Steel Stiffener Plates | MATERIAL | 16 | EA | $225.00 | $3,600.00
02 | Welder Field Labor | LABOR | 40 | HR | $110.00 | $4,400.00
SUBTOTAL: $8,000.00
OVERHEAD AND PROFIT: $800.00
SALES TAX: $0.00
TOTAL CHANGE ORDER AMOUNT: $8,800.00
ORIGINAL CONTRACT SUM: $100,000.00
NET CHANGE BY PREVIOUS CHANGE ORDERS: $0.00
CONTRACT SUM PRIOR TO THIS CHANGE ORDER: $100,000.00
THIS CHANGE ORDER AMOUNT: $8,800.00
NEW CONTRACT SUM INCLUDING THIS CHANGE ORDER: $108,800.00
SCHEDULE IMPACT: 4 DAYS""",

    "co_02_ocr_scan": """CHANGE ORDER NO: PCO-019
PROJECT: Oakridge Medical
PROJECT NUMBER: OMP-11
TITLE: Storm Drain Reroute
STATUS: PENDING
ISSUE DATE: 2026-10-05
EFFECTIVE DATE: 2026-10-12
OWNER: Oakridge Health
GENERAL CONTRACTOR: Summit Builders
SUBCONTRACTOR: RedRock Civil
REASON FOR CHANGE: Unforeseen rock ledge
SCOPE OF WORK: Trenching and pipe reroute
01 | Excavator | EQUIPMENT | 2O | HR | $225.00 | $4,5OO.00
SUBTOTAL: $4,5OO.00
OVERHEAD AND PROFIT: $0.00
SALES TAX: $0.00
TOTAL CHANGE ORDER AMOUNT: $4,500.00
ORIGINAL CONTRACT SUM: $50,000.00
NET CHANGE BY PREVIOUS CHANGE ORDERS: $0.00
CONTRACT SUM PRIOR TO THIS CHANGE ORDER: $50,000.00
THIS CHANGE ORDER AMOUNT: $4,500.00
NEW CONTRACT SUM INCLUDING THIS CHANGE ORDER: $54,500.00
SCHEDULE IMPACT: 2 DAYS""",

    "co_03_math_error": """CHANGE ORDER NO: CO-108
PROJECT: Harborview Lofts
PROJECT NUMBER: HML-44
TITLE: Corridor Drywall Upgrade
STATUS: DRAFT
ISSUE DATE: 2026-10-18
EFFECTIVE DATE: 2026-10-25
OWNER: Harborview Dev
GENERAL CONTRACTOR: Pacific Coast GC
SUBCONTRACTOR: Precision Drywall
REASON FOR CHANGE: Fire marshal comment
SCOPE OF WORK: Upgrade corridor shaftwall
01 | Framing Labor | LABOR | 40 | HR | $85.00 | $3,800.00
SUBTOTAL: $3,800.00
OVERHEAD AND PROFIT: $380.00
SALES TAX: $0.00
TOTAL CHANGE ORDER AMOUNT: $4,580.00
ORIGINAL CONTRACT SUM: $80,000.00
NET CHANGE BY PREVIOUS CHANGE ORDERS: $0.00
CONTRACT SUM PRIOR TO THIS CHANGE ORDER: $80,000.00
THIS CHANGE ORDER AMOUNT: $4,580.00
NEW CONTRACT SUM INCLUDING THIS CHANGE ORDER: $84,580.00
SCHEDULE IMPACT: 1 DAYS""",
}


def main() -> None:
    out_dir = Path("samples")
    out_dir.mkdir(exist_ok=True)
    for name, text in SAMPLES.items():
        (out_dir / f"{name}.txt").write_text(text, encoding="utf-8")
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(fitz.Point(40, 50), text, fontsize=10)
        doc.save(str(out_dir / f"{name}.pdf"))
        doc.close()
    print("Generated 3 PDFs and 3 TXT files in samples/!")


if __name__ == "__main__":
    main()