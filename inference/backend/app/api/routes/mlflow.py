from trading_functions.inference.inf_functions import (
    make_random_candles, 
    get_config,
    mlflow_aliases,
    mlflow_aliases_rl
)

from fastapi import APIRouter, Depends

router = APIRouter()

@router.get("/models_info")
def get_mlflow_model_info():
    """
    Get MLflow model information.
    """
    config = get_config()
    models_info = mlflow_aliases(config)
    return models_info


@router.get("/rl_models_info")
def get_rl_mlflow_model_info():
    """
    Get RL MLflow model information.
    """
    config = get_config()
    models_info = mlflow_aliases_rl(config)
    return models_info