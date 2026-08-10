from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# --- Request schemas ---


class OrderCreateRequest(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)


# --- Response schemas ---


class OrderResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    quantity: int
    total_price: Decimal
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
