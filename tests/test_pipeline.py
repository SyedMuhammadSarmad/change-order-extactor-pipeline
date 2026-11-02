from change_order_extractor.pipeline import ChangeOrderPipeline


def test_clean_change_order() -> None:
    sample = """
    CHANGE ORDER NO: CO-004
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
    SCHEDULE IMPACT: 4 DAYS
    """
    pipeline = ChangeOrderPipeline(provider="offline")
    res = pipeline.extract_text(sample)

    assert res.validation.is_valid is True
    assert res.needs_human_review is False
    assert res.overall_confidence >= 0.90
    assert res.data.cost_summary.total_change_order_amount.value == 8800.0


def test_ocr_corrupted_change_order() -> None:
    sample = """
    CHANGE ORDER NO: PCO-019
    PROJECT: Oakridge Medical
    01 | Excavator | EQUIPMENT | 2O | HR | $225.00 | $4,5OO.00
    SUBTOTAL: $4,5OO.00
    OVERHEAD AND PROFIT: $0.00
    SALES TAX: $0.00
    TOTAL CHANGE ORDER AMOUNT: $4,500.00
    """
    pipeline = ChangeOrderPipeline(provider="offline")
    res = pipeline.extract_text(sample)

    assert res.data.cost_summary.subtotal.value == 4500.0
    assert res.data.cost_summary.subtotal.confidence < 0.70
    assert res.needs_human_review is True


def test_math_error_change_order() -> None:
    sample = """
    CHANGE ORDER NO: CO-108
    PROJECT: Harborview Lofts
    01 | Framing Labor | LABOR | 40 | HR | $85.00 | $3,800.00
    SUBTOTAL: $3,800.00
    OVERHEAD AND PROFIT: $380.00
    SALES TAX: $0.00
    TOTAL CHANGE ORDER AMOUNT: $4,580.00
    """
    pipeline = ChangeOrderPipeline(provider="offline")
    res = pipeline.extract_text(sample)

    assert res.validation.is_valid is False
    assert res.data.line_items[0].total_amount.confidence < 0.50
    assert res.needs_human_review is True