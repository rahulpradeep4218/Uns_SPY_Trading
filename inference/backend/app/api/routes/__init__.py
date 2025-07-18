from fastapi import APIRouter

from . import trades, mlflow, trade_sessions, price_data, app_process, schwab

router = APIRouter()
router.include_router(trades.router, prefix="/trades", tags=["trades"])
router.include_router(mlflow.router, prefix="/mlflow", tags=["mlflow"])
router.include_router(trade_sessions.router, prefix="/trade_sessions", tags=["trade_sessions"])
router.include_router(price_data.router, prefix="/price_data", tags=["price_data"])
router.include_router(app_process.router, prefix="/process", tags=["process"])
router.include_router(schwab.router, prefix="/schwab", tags=["schwab"])