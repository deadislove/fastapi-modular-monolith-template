from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.facades.order_facade import order_facade
from app.modules.orders.errors import OrderNotFoundError
from app.modules.orders.public_api import order_public_api
from app.modules.orders.schemas import OrderCreateRequest, OrderResponse
from app.modules.products.errors import InsufficientStockError, ProductNotFoundError
from app.modules.users.errors import UserNotFoundError
from app.shared.errors import ConflictError, NotFoundError
from app.shared.security import get_current_user_id

router = APIRouter(prefix="/orders", tags=["Orders"])


def _map_order_error(err: object) -> HTTPException:
    """Map domain errors to HTTP responses — presentation layer concern only."""
    if isinstance(err, (OrderNotFoundError, UserNotFoundError, ProductNotFoundError, NotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err.message)
    if isinstance(err, (InsufficientStockError, ConflictError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err.message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


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
    current_user_id: int = Depends(get_current_user_id),
) -> OrderResponse:
    result = await order_facade.place_order(current_user_id, body.product_id, body.quantity)
    if result.is_err():
        raise _map_order_error(result.err())
    return OrderResponse.model_validate(result.ok())


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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your order")
    return OrderResponse.model_validate(order)
