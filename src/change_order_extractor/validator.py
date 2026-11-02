from .schemas import ChangeOrderExtraction, ValidationAnomaly, ValidationReport

def approx_equal(a:float,b:float, tol:float = 0.10) -> bool:
    return abs(a-b)<=tol
    
def validate_extraction(extraction: ChangeOrderExtraction) -> ValidationReport:
    anomalies:list[ValidationAnomaly] = []
    line_items_math_valid = True

    # Check 1: Line-Item Math (quantity * unit_price == total_amount)
    for i, item in enumerate(extraction.line_items):
        q = item.quantity.value
        up = item.unit_price.value
        tot = item.total_amount.value

        if  q is not None and up is not None and tot is not None:
            expected = round(q*up,2)
            if not approx_equal(expected,tot):
                line_items_math_valid = False
                item.total_amount.confidence = min(item.total_amount.confidence,0.35)

                item.total_amount.flags.append("MATH_LINE_ITEM_MISMATCH")
                anomalies.append(
                    ValidationAnomaly(
                        code = "MATH_LINE_ITEM_MISMATCH",
                        severity = "ERROR",
                        field_paths = [f"line_items[{i}].total_amount"],
                        message = f"Item {i+1}:{q} *{up} = {expected}, but PDF has {tot}",
                        expected_value = expected,
                        actual_value = tot,
                    )
                )

     # Check 2: Cost Summary Math (subtotal + overhead_and_profit + tax == total)
    cost_reconciliation_valid = True
    cs = extraction.cost_summary
    sub = cs.subtotal.value
    ohp = cs.overhead_and_profit.value or 0.0
    tax = cs.tax_amount.value or 0.0
    tot = cs.total_change_order_amount.value
    if sub is not None and tot is not None:
        expected_total = round(sub + ohp + tax, 2)
        if not approx_equal(expected_total, tot, tol=0.50):
            cost_reconciliation_valid = False
            cs.total_change_order_amount.confidence = min(
                cs.total_change_order_amount.confidence, 0.30
            )
            cs.total_change_order_amount.flags.append("MATH_TOTAL_MISMATCH")
            anomalies.append(
                ValidationAnomaly(
                    code="MATH_TOTAL_MISMATCH",
                    severity="CRITICAL",
                    field_paths=["cost_summary.total_change_order_amount"],
                    message=f"Subtotal ({sub}) + O&P ({ohp}) + Tax ({tax}) = {expected_total}, but total is {tot}",
                    expected_value=expected_total,
                    actual_value=tot,
                )
            )
    
    # Check 3: Contract Roll-Forward (prior_sum + this_change_order == new_contract_sum)
    contract_rollforward_valid = True
    cr = extraction.contract_reconciliation
    prior = cr.contract_sum_prior_to_this_change_order.value
    curr = cr.this_change_order_amount.value
    new_sum = cr.new_contract_sum_including_this_change_order.value

    if prior is not None and curr is not None and new_sum is not None:
        expected_new = round(prior + curr, 2)
        if not approx_equal(expected_new, new_sum, tol=1.0):
            contract_rollforward_valid = False
            cr.new_contract_sum_including_this_change_order.confidence = min(
                cr.new_contract_sum_including_this_change_order.confidence, 0.35
            )
            cr.new_contract_sum_including_this_change_order.flags.append(
                "MATH_CONTRACT_SUM_MISMATCH"
            )
            anomalies.append(
                ValidationAnomaly(
                    code="MATH_CONTRACT_SUM_MISMATCH",
                    severity="CRITICAL",
                    field_paths=["contract_reconciliation.new_contract_sum_including_this_change_order"],
                    message=f"Prior ({prior}) + Current ({curr}) = {expected_new}, but new sum is {new_sum}",
                    expected_value=expected_new,
                    actual_value=new_sum,
                )
            )

    return ValidationReport(
        is_valid=len(anomalies) == 0,
        line_items_math_valid=line_items_math_valid,
        cost_reconciliation_valid=cost_reconciliation_valid,
        contract_rollforward_valid=contract_rollforward_valid,
        anomalies=anomalies,
    )