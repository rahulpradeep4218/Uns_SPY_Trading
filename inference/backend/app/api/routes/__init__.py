from fastapi import APIRouter
from . import trades, mlflow, trade_sessions, price_data

router = APIRouter()
router.include_router(trades.router, prefix="/trades", tags=["trades"])
router.include_router(mlflow.router, prefix="/mlflow", tags=["mlflow"])
router.include_router(trade_sessions.router, prefix="/trade_sessions", tags=["trade_sessions"])
router.include_router(price_data.router, prefix="/price_data", tags=["price_data"])