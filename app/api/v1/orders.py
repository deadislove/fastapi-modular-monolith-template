import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from app.facades.order_facade import order_facade
from app.modules.orders.errors import OrderForbiddenError, OrderNotFoundError
from app.modules.orders.public_api import order_public_api
from app.modules.orders.schemas import OrderCreateRequest, OrderResponse
from app.modules.products.errors import InsufficientStockError, ProductNotFoundError
from app.modules.users.errors import UserNotFoundError
from app.shared.errors import ConflictError, DomainError, NotFoundError
from app.shared.security import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["Orders"])


async def _notify_fulfillment(order_id: int, product_id: int, quantity: int) -> None:
    """Runs after the response is already sent — see docs/cross-module-communication.md
    for why this isn't just done through the EventBus. Stands in for a real call to a
    fulfillment/warehouse system or notification provider."""
    try:
        await asyncio.sleep(0.05)  # simulated external call
        logger.info(
            "Fulfillment notified: order_id=%s product_id=%s quantity=%s",
            order_id, product_id, quantity,
        )
    except Exception:
        logger.exception("Fulfillment notification failed for order_id=%s", order_id)


def _map_order_error(err: DomainError) -> HTTPException:
    """Map domain errors to HTTP responses — presentation layer concern only."""
    if isinstance(err, (OrderNotFoundError, UserNotFoundError, ProductNotFoundError, NotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err.as_detail())
    if isinstance(err, (InsufficientStockError, ConflictError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err.as_detail())
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err.as_detail())


@router.post(
    "/",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Product not found"},
        409: {"description": "Not enough stock"},
        500: {"description": "Internal server error"},
    },
    summary="Place an order",
)
async def place_order(
    body: OrderCreateRequest,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
) -> OrderResponse:
    result = await order_facade.place_order(current_user_id, body.product_id, body.quantity)
    if result.is_err():
        raise _map_order_error(result.err())
    order = result.ok()
    background_tasks.add_task(_notify_fulfillment, order.id, order.product_id, order.quantity)
    return OrderResponse.model_validate(order)


@router.get(
    "/my",
    response_model=list[OrderResponse],
    responses={
        401: {"description": "Not authenticated"},
        500: {"description": "Internal server error"},
    },
    summary="List orders placed by the current user",
)
async def list_my_orders(
    current_user_id: int = Depends(get_current_user_id),
    limit: int = Query(50, ge=1, le=100, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip"),
) -> list[OrderResponse]:
    result = await order_public_api.get_orders_by_user(current_user_id, limit=limit, offset=offset)
    if result.is_err():
        raise _map_order_error(result.err())
    return [OrderResponse.model_validate(o) for o in result.ok()]


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not your order"},
        404: {"description": "Order not found"},
        500: {"description": "Internal server error"},
    },
    summary="Get an order by ID (owner only)",
)
async def get_order(
    order_id: int, current_user_id: int = Depends(get_current_user_id)
) -> OrderResponse:
    result = await order_public_api.get_order_by_id(order_id)
    if result.is_err():
        raise _map_order_error(result.err())
    order = result.ok()
    if order.user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=OrderForbiddenError().as_detail()
        )
    return OrderResponse.model_validate(order)
