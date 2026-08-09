from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import Base, module_schema

# ForeignKey targets need the schema qualifier too once users' table moves out of
# the default schema — see modules/products/README.md for why this FK exists at
# all despite the module-boundary rule.
_USERS_TABLE = f"{module_schema('users')}.users" if module_schema("users") else "users"


class Product(Base):
    """Product entity — linked to the user who created it via a foreign key (no cross-module join)."""

    __tablename__ = "products"
    __table_args__ = {"schema": module_schema("products")}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Ownership reference — cross-module queries go through UserPublicApi, never a JOIN
    created_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{_USERS_TABLE}.id", ondelete="CASCADE"), nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} name={self.name!r}>"
