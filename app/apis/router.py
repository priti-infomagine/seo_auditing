from fastapi import APIRouter

from app.apis.endpoints.v1.router import router as v1_router

api_router = APIRouter()

api_router.include_router(
    v1_router,
    prefix="/api/v1",
)

# Future
# from app.api.v2.router import router as v2_router
# api_router.include_router(v2_router, prefix="/api/v2")