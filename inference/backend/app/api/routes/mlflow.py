from trading_functions.inference.inf_functions import (
    make_random_candles, 
    get_config,
    mlflow_aliases
)

from fastapi import APIRouter, Depends

router = APIRouter()

@router.get("/aliases")
def get_mlflow_aliases():
    """
    Get MLflow aliases for models.
    """
    config = get_config()
    aliases = mlflow_aliases(config)
    return aliases

