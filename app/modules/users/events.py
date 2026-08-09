from dataclasses import dataclass

from app.shared.events import DomainEvent


@dataclass(frozen=True)
class UserRegistered(DomainEvent):
    """Published after a user's registration transaction has committed."""

    user_id: int
    email: str
