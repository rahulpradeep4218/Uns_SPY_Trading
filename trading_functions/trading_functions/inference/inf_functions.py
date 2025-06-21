from pyexpat import model

from sympy import im
from torch import mode

from trading_functions.training.utility import get_columns_mapping
from trading_functions.common.logging_config import logger
from trading_functions.common.transform import normalize_timegaps, close_diff_transform
from trading_functions.common.indicators import add_all_indicators
import mlflow
from mlflow.tracking import MlflowClient
import os
import shutil
import joblib
import pandas as pd
import numpy as np
import yaml
from datetime import datetime, timezone

def scale_for_inference(data, config, scalers):
    scale_cfg = config['scaling']

    minmax_features = get_columns_mapping(scale_cfg['minmax']['columns'], config)
    standard_features = get_columns_mapping(scale_cfg['standard']['columns'], config)
    robust_features = get_columns_mapping(scale_cfg['robust']['columns'], config)

    if scalers['minmax'] is not None and len(minmax_features) > 0:
        logger.debug(f"Applying Transform Min-Max scaling to features: {minmax_features}")
        data[minmax_features] = scalers['minmax'].transform(data[minmax_features])
    else:
        logger.debug("No Min-Max scaler found or no features to scale.")
    #Standard scaling
    if scalers['standard'] is not None and len(standard_features) > 0:
        logger.debug(f"Applying Transform Standard scaling to features: {standard_features}")
        data[standard_features] = scalers['standard'].transform(data[standard_features])
    else:
        logger.debug("No Standard scaler found or no features to scale.")
    #Robust Scaling
    if scalers['robust'] is not None and len(robust_features) > 0:
        logger.debug(f"Applying Transform Robust scaling to features: {robust_features}")
        data[robust_features] = scalers['robust'].transform(data[robust_features])
    else:
        logger.debug("No Robust scaler found or no features to scale.")


def download_artifacts(config, dev=False, mlflow_uri=None):
    ml_client = MlflowClient()

    if mlflow_uri:
        logger.info(f"Setting MLflow tracking URI to {mlflow_uri}")
        mlflow.set_tracking_uri(mlflow_uri)
    else:
        logger.info("Using default MLflow tracking URI from config.")
        mlflow.set_tracking_uri(config['mlflow']['tracking_uri'])
    high_model_name = config['mlflow']['high_model_name']
    alias = 'dev' if dev else 'prod'
    logger.info(f"Using model alias: {alias} for model: {high_model_name}")
    artifact_download_path = config['mlflow']['artifact_download_path']

    mv_alias = ml_client.get_model_version_by_alias(
        name=high_model_name, 
        alias=alias
    )
    run_id = mv_alias.run_id
    scaler_artifact_uri = f"runs:/{run_id}/model/scalers.pkl"
    config_artifact_uri = f"runs:/{run_id}/model/{config['training_details']['mlflow_config_artifact_name']}"
    logger.info(f"scaler artifact_uri: {scaler_artifact_uri}")
    logger.info(f"config artifact_uri: {config_artifact_uri}")

    # If scaler local download directory already exist, delete it
    if os.path.exists(artifact_download_path):
        logger.info(f"Deleting existing scaler directory: {artifact_download_path}")
        shutil.rmtree(artifact_download_path)
    os.makedirs(artifact_download_path, exist_ok=True)

    #Download scalers
    scaler_local_path = mlflow.artifacts.download_artifacts(
        artifact_uri=scaler_artifact_uri, 
        dst_path=artifact_download_path
    )
    logger.info(f"Scalers downloaded to {scaler_local_path}")

    scalers = joblib.load(scaler_local_path)
    logger.info(f"Scalers loaded: {scalers.keys()}")

    #Download config
    config_local_path = mlflow.artifacts.download_artifacts(
        artifact_uri=config_artifact_uri, 
        dst_path=artifact_download_path
    )
    with open(config_local_path, 'r') as file:
        model_config = yaml.safe_load(file)

    logger.info(f"Config downloaded to {config_local_path}")

    return scalers, model_config

def transform_for_inference(data, config, scalers):
    """
    Apply transformations to the data for inference.
    Order of transformations:
    1. Make datetime column a pd.datetime object
    2. Normalize time gaps in the data
    3. Add indicators if needed
    4. Close difference transformation
    5. Scale features using Min-Max, Standard, and Robust scalers
    """
    logger.debug("Starting data transformation for inference.")

    # Make datetime column a pd.datetime object
    data['Date'] = pd.to_datetime(data['Date'])
    logger.debug("Converted 'Date' column to datetime.")

    # Normalize time gaps
    data = normalize_timegaps(data, config)
    logger.debug("Normalized time gaps in the data.")

    # Add indicators if needed
    data = add_all_indicators(data, config)
    logger.debug("Added indicators to the data.")

    # Close difference transformation
    data, close_diff_features = close_diff_transform(data, config)
    logger.debug(f"Applied close difference transformation on features: {close_diff_features}")

    # Scale features
    scale_for_inference(data, config, scalers)

    logger.debug("Data transformation for inference completed.")
    return data


def make_random_candles(n, freq_minutes):
    end = datetime.now(timezone.utc)
    dates = pd.date_range(end=end, periods=n, freq=f"{freq_minutes}T")
    price = 100 + np.cumsum(np.random.randn(n))
    opens = price + np.random.randn(n)*0.5
    closes = price + np.random.randn(n)*0.5
    highs = np.maximum(opens, closes) + np.random.rand(n)*1.0
    lows = np.minimum(opens, closes) - np.random.rand(n)*1.0

    return pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes
    })
# define a fixed y‐scale:

def get_config():
    """
    Load the configuration from the config.yaml file.
    """
    config_path = '../../Config/config_dev.yaml'
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file {config_path} not found.")
    
    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)
    
    return config

def mlflow_aliases(config):
    """
    Get MLflow aliases from the config.
    """
    result = {}
    mlflow_tracking = config['mlflow']['tracking_uri']
    models = [config['mlflow']['high_model_name'], config['mlflow']['low_model_name']]
    logger.info(f"Fetching MLflow aliases for models: {models} from tracking URI: {mlflow_tracking}")
    if mlflow_tracking:
        mlflow.set_tracking_uri(mlflow_tracking)

    client = MlflowClient()
    for model in models:
        aliases = set()
        versions = client.search_model_versions(f"name='{model}'")
        print(f"Versions : {versions}")
        for v in versions:
            mv = client.get_model_version(name=model, version=v.version)
            if mv.aliases:
                aliases.update(mv.aliases)

        result[model] = aliases
    return result
