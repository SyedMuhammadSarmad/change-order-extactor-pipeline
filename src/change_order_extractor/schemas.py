from typing import Generic, Optional, TypeVar, Any
from pydantic import BaseModel, Field

T = TypeVar("T")

class ConfidenceSignals(BaseModel):
    llm_self_confidence:float = Field(...,ge = 0.0, le = 1.0)
    grounding_score:float = Field(...,ge = 0.0, le = 1.0)
    consistency_score:float = Field(...,ge = 0.0, le = 1.0)
    document_quality_score:float = Field(...,ge = 0.0, le = 1.0)

class ScoredField(BaseModel, Generic[T]):
    value:Optional[T] = None
    confidence: float = Field(...,ge = 0.0, le = 1.0)
    evidence_quote:Optional[str] = None
    source_page:int = 1
    signals:Optional[ConfidenceSignals] = None
    flags:list[str] = Field(default_factory=list)

class ExtractedLineItem(BaseModel):
    item_number:ScoredField[str]
    description:ScoredField[str]
    category:ScoredField[str]
    quantity:ScoredField[float]
    unit:ScoredField[str]
    unit_price:ScoredField[float]
    total_amount:ScoredField[float]
    row_confidence:float = 0.0

class CostSummary(BaseModel):
    subtotal:ScoredField[float]
    overhead_and_profit:ScoredField[float]
    tax_amount:ScoredField[float]
    total_change_order_amount:ScoredField[float]

class ContractSumReconciliation(BaseModel):
    original_contract_sum: ScoredField[float]
    net_change_by_previous_change_orders:ScoredField[float]
    contract_sum_prior_to_this_change_order:ScoredField[float]
    this_change_order_amount:ScoredField[float]
    new_contract_sum_including_this_change_order:ScoredField[float]

class ChangeOrderExtraction(BaseModel):
    change_order_number:ScoredField[str]
    project_name:ScoredField[str]
    project_number:ScoredField[str]
    title:ScoredField[str]
    status:ScoredField[str]
    effective_or_approval_date:ScoredField[str]
    issue_date:ScoredField[str]
    reason_for_change:ScoredField[str]
    scope_of_work_summary:ScoredField[str]
    owner_name:ScoredField[str]
    general_contractor_name:ScoredField[str]
    subcontractor_name:ScoredField[str]
    schedule_impact_days:ScoredField[int]
    cost_summary:CostSummary
    contract_reconciliation:ContractSumReconciliation
    line_items:list[ExtractedLineItem]=Field(default_factory=list)


class DocumentQualityReport(BaseModel):
    source_filename: str
    source_type: str
    page_count: int = 1
    total_characters: int = 0
    estimated_ocr_noise_ratio:float = 0.0
    document_quality_score: float = 1.0
    quality_notes: list[str] = Field(default_factory=list)


class ValidationAnomaly(BaseModel):
    code:str
    severity:str #warining, error or critical
    field_paths:list[str]
    message:str
    expected_value:Optional[Any] = None
    actual_value: Optional[Any] = None

class ValidationReport(BaseModel):
    is_valid:bool
    line_items_math_valid:bool
    cost_reconciliation_valid:bool
    contract_rollforward_valid:bool
    anomalies:list[ValidationAnomaly]= Field(default_factory=list)

class ExtractionPipelineResult(BaseModel):
    provider_used:str
    overall_confidence:float
    needs_human_review:bool
    review_reasons:list[str]= Field(default_factory=list)
    document_quality: DocumentQualityReport
    validation: ValidationReport
    data:ChangeOrderExtraction