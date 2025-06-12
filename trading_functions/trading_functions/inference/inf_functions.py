from pyexpat import model
from trading_functions.training.utility import get_columns_mapping
from trading_functions.common.logging_config import logger
from trading_functions.common.transform import normalize_timegaps, close_diff_transform
from trading_functions.common.indicators import add_all_indicators
import mlflow
import os
import shutil
import joblib
import pandas as pd

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


def download_scalers_artifact(config, dev=False, mlflow_uri=None):
    if mlflow_uri:
        logger.info(f"Setting MLflow tracking URI to {mlflow_uri}")
        mlflow.set_tracking_uri(mlflow_uri)
    else:
        logger.info("Using default MLflow tracking URI from config.")
        mlflow.set_tracking_uri(config['mlflow']['tracking_uri'])
    high_model_name = config['mlflow']['high_model_name']
    low_model_name = config['mlflow']['low_model_name']
    alias = 'dev' if dev else 'prod'
    artifact_download_path = config['mlflow']['scaler_artifact_download_path']
    model_uri_high = f"models:/{high_model_name}@{alias}"
    model_uri_low = f"models:/{low_model_name}@{alias}"
    scalers_high_artifact_uri = f"{model_uri_high}/{config['mlflow']['scaler_artifact_path']}"
    logger.info(f"Downloading scalers from {scalers_high_artifact_uri}")

    # If scaler local download directory already exist, delete it
    if os.path.exists(artifact_download_path):
        logger.info(f"Deleting existing scaler directory: {artifact_download_path}")
        shutil.rmtree(artifact_download_path)
    os.makedirs(artifact_download_path, exist_ok=True)

    #Download scalers

    local_path = mlflow.artifacts.download_artifacts(
        artifact_uri=scalers_high_artifact_uri, 
        dst_path=artifact_download_path
    )
    logger.info(f"Scalers downloaded to {local_path}")
    
    scalers = joblib.load(local_path)
    logger.info(f"Scalers loaded: {scalers.keys()}")
    return scalers

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




