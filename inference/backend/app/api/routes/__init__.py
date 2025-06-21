from fastapi import APIRouter
from . import trades, mlflow

router = APIRouter()
router.include_router(trades.router, prefix="/trades", tags=["trades"])
router.include_router(mlflow.router, prefix="/mlflow", tags=["mlflow"])