from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

REASONS = ["fit_too_small", "fit_too_large", "fabric_quality", "damaged", "wrong_item", "colour_mismatch", "changed_mind", "delivery_issue", "other", "insufficient_information", "not_return"]
COLORS = ["Blue", "Red", "Green", "Black", "White", "Yellow", "Pink", "Purple", "Brown", "Grey", "Orange", "Beige", "Multicolour", "Unknown"]
FABRICS = ["Cotton", "Polyester", "Viscose", "Linen", "Silk", "Denim", "Wool", "Blend", "Unknown"]
SIZES = ["XS", "S", "M", "L", "XL", "XXL", "XXXL", "One Size", "Vendor Specific", "Unknown"]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class ReturnDecision(StrictModel):
    primary_reason: Literal["fit_too_small", "fit_too_large", "fabric_quality", "damaged", "wrong_item", "colour_mismatch", "changed_mind", "delivery_issue", "other", "insufficient_information", "not_return"]
    secondary_reasons: list[Literal["fit_too_small", "fit_too_large", "fabric_quality", "damaged", "wrong_item", "colour_mismatch", "changed_mind", "delivery_issue", "other"]]
    evidence: str
    confidence: float = Field(ge=0, le=1)
    needs_review: bool
    explanation: str

class CatalogueDecision(StrictModel):
    colour_family: Literal["Blue", "Red", "Green", "Black", "White", "Yellow", "Pink", "Purple", "Brown", "Grey", "Orange", "Beige", "Multicolour", "Unknown"]
    colour_shade: str
    fabric: Literal["Cotton", "Polyester", "Viscose", "Linen", "Silk", "Denim", "Wool", "Blend", "Unknown"]
    fabric_detail: str
    size_label: Literal["XS", "S", "M", "L", "XL", "XXL", "XXXL", "One Size", "Vendor Specific", "Unknown"]
    confidence: float = Field(ge=0, le=1)
    needs_review: bool
    explanation: str

class ReturnInput(StrictModel):
    message_id: str = Field(min_length=1, max_length=100)
    source: Literal["whatsapp", "app", "support"]
    case_id: str = Field(max_length=100)
    order_id: str = Field(max_length=100)
    sku: str = Field(max_length=100)
    text: str = Field(max_length=4000)

class CatalogueInput(StrictModel):
    sku: str = Field(min_length=1, max_length=100)
    vendor_id: str = Field(min_length=1, max_length=100)
    product_name: str = Field(max_length=250)
    colour_raw: str = Field(max_length=250)
    fabric_raw: str = Field(max_length=250)
    size_raw: str = Field(max_length=100)
    size_chart_id: str = Field(max_length=100)
    chest_cm: str = Field(max_length=100)
