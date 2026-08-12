from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# --- Request schemas ---

class ProductCreateRequest(BaseModel):
    name: str
    description: str | None = None
    price: Decimal = Field(..., gt=0, decimal_places=2)
    stock: int = Field(default=0, ge=0)


class ProductUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    stock: int | None = Field(default=None, ge=0)


# --- Response schemas ---

class ProductResponse(BaseModel):
    id: int
    name: str
    description: str | None
    price: Decimal
    stock: int
    created_by_user_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
