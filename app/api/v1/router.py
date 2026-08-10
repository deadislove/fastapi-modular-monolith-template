from fastapi import APIRouter

from app.api.v1.orders import router as orders_router
from app.api.v1.products import router as products_router
from app.api.v1.users import router as users_router

# Aggregate all v1 module routers under /api/v1
api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(users_router)
api_v1_router.include_router(products_router)
api_v1_router.include_router(orders_router)
