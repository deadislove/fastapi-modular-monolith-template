from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.modules.products.errors import (
    ProductForbiddenError,
    ProductNotFoundError,
)
from app.modules.products.public_api import product_public_api
from app.modules.products.schemas import (
    ProductCreateRequest,
    ProductResponse,
    ProductUpdateRequest,
)
from app.shared.errors import DomainError, ForbiddenError, NotFoundError
from app.shared.security import get_current_user_id

router = APIRouter(prefix="/products", tags=["Products"])


def _map_product_error(err: DomainError) -> HTTPException:
    """Map domain errors to HTTP responses — presentation layer concern only."""
    if isinstance(err, (ProductNotFoundError, NotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err.as_detail())
    if isinstance(err, (ProductForbiddenError, ForbiddenError)):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=err.as_detail())
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err.as_detail())


@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "Not authenticated"},
        500: {"description": "Internal server error"},
    },
    summary="Create a new product",
)
async def create_product(
    body: ProductCreateRequest,
    current_user_id: int = Depends(get_current_user_id),
) -> ProductResponse:
    result = await product_public_api.create_product(body, current_user_id)
    if result.is_err():
        raise _map_product_error(result.unwrap_err())
    return ProductResponse.model_validate(result.unwrap())


@router.get(
    "/",
    response_model=list[ProductResponse],
    responses={
        500: {"description": "Internal server error"},
    },
    summary="List all products",
)
async def list_products(
    limit: int = Query(50, ge=1, le=100, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip"),
) -> list[ProductResponse]:
    result = await product_public_api.get_all_products(limit=limit, offset=offset)
    if result.is_err():
        raise _map_product_error(result.unwrap_err())
    return [ProductResponse.model_validate(p) for p in result.unwrap()]


@router.get(
    "/my",
    response_model=list[ProductResponse],
    responses={
        401: {"description": "Not authenticated"},
        500: {"description": "Internal server error"},
    },
    summary="List products created by the current user",
)
async def list_my_products(
    current_user_id: int = Depends(get_current_user_id),
    limit: int = Query(50, ge=1, le=100, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip"),
) -> list[ProductResponse]:
    result = await product_public_api.get_products_by_user(current_user_id, limit=limit, offset=offset)
    if result.is_err():
        raise _map_product_error(result.unwrap_err())
    return [ProductResponse.model_validate(p) for p in result.unwrap()]


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    responses={
        404: {"description": "Product not found"},
        500: {"description": "Internal server error"},
    },
    summary="Get a product by ID",
)
async def get_product(product_id: int) -> ProductResponse:
    result = await product_public_api.get_product_by_id(product_id)
    if result.is_err():
        raise _map_product_error(result.unwrap_err())
    return ProductResponse.model_validate(result.unwrap())


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the product owner"},
        404: {"description": "Product not found"},
        500: {"description": "Internal server error"},
    },
    summary="Update a product (owner only)",
)
async def update_product(
    product_id: int,
    body: ProductUpdateRequest,
    current_user_id: int = Depends(get_current_user_id),
) -> ProductResponse:
    result = await product_public_api.update_product(product_id, body, current_user_id)
    if result.is_err():
        raise _map_product_error(result.unwrap_err())
    return ProductResponse.model_validate(result.unwrap())


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the product owner"},
        404: {"description": "Product not found"},
        500: {"description": "Internal server error"},
    },
    summary="Delete a product (owner only)",
)
async def delete_product(
    product_id: int,
    current_user_id: int = Depends(get_current_user_id),
) -> None:
    result = await product_public_api.delete_product(product_id, current_user_id)
    if result.is_err():
        raise _map_product_error(result.unwrap_err())
