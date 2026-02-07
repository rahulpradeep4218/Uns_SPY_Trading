
from trading_functions.training.utility import get_columns_mapping, get_all_training_features
from trading_functions.common.logging_config import logger
from trading_functions.common.transform import normalize_timegaps_inference, close_diff_transform
from trading_functions.common.indicators import add_all_indicators, get_fourier_columns
import mlflow
from mlflow.tracking import MlflowClient
import os
import shutil
import joblib
import pandas as pd
import numpy as np
import yaml
from datetime import datetime, timezone
import talib
from dotenv import load_dotenv

load_dotenv()

def scale_for_inference(data, config, scalers):
    scale_cfg = config['scaling']

    minmax_features = get_columns_mapping(scale_cfg['minmax']['columns'], config)
    standard_features = get_columns_mapping(scale_cfg['standard']['columns'], config)
    robust_features = get_columns_mapping(scale_cfg['robust']['columns'], config)

    fourier_columns = get_fourier_columns(config)

    if scalers['minmax'] is not None and len(minmax_features) > 0:
        if 'fourier' in minmax_features:
            minmax_features = [f for f in minmax_features if f != 'fourier'] + fourier_columns
        logger.debug(f"Applying Transform Min-Max scaling to features: {minmax_features}")
        data[minmax_features] = scalers['minmax'].transform(data[minmax_features])
    else:
        logger.debug("No Min-Max scaler found or no features to scale.")
    #Standard scaling
    if scalers['standard'] is not None and len(standard_features) > 0:
        if 'fourier' in standard_features:
            standard_features = [f for f in standard_features if f != 'fourier'] + fourier_columns
        logger.debug(f"Applying Transform Standard scaling to features: {standard_features}")
        data[standard_features] = scalers['standard'].transform(data[standard_features])
    else:
        logger.debug("No Standard scaler found or no features to scale.")
    #Robust Scaling
    if scalers['robust'] is not None and len(robust_features) > 0:
        if 'fourier' in robust_features:
            robust_features = [f for f in robust_features if f != 'fourier'] + fourier_columns
        logger.debug(f"Applying Transform Robust scaling to features: {robust_features}")
        data[robust_features] = scalers['robust'].transform(data[robust_features])
    else:
        logger.debug("No Robust scaler found or no features to scale.")

def get_model_from_mlflow(config, model_name="", model_version=None):
    mlflow.set_tracking_uri(config['mlflow']['tracking_uri'])
    model = mlflow.pyfunc.load_model(
        f"models:/{model_name}/{model_version}"
    )
    return model



def download_artifacts(config, alias="dev", mlflow_uri=None):

    if mlflow_uri:
        logger.info(f"Setting MLflow tracking URI to {mlflow_uri}")
        mlflow.set_tracking_uri(mlflow_uri)
    else:
        logger.info(f"Using default MLflow tracking URI from config : {config['mlflow']['tracking_uri']}")
        mlflow.set_tracking_uri(config['mlflow']['tracking_uri'])

    ml_client = MlflowClient()
    high_model_name = config['mlflow']['high_model_name']
 
    logger.info(f"Using model alias: {alias} for model: {high_model_name}")
    artifact_download_path = config['mlflow']['artifact_download_path']

    mv_alias = ml_client.get_model_version_by_alias(
        name=high_model_name, 
        alias=alias
    )
    run_id = mv_alias.run_id
    scaler_artifact_path = "run_model/scalers.pkl"
    config_artifact_path = f"run_model/{config['training_details']['mlflow_config_artifact_name']}"
    #scaler_artifact_uri = f"runs:/{run_id}/model/scalers.pkl"
    #config_artifact_uri = f"runs:/{run_id}/model/{config['training_details']['mlflow_config_artifact_name']}"
    logger.info(f"scaler path: {scaler_artifact_path}")
    logger.info(f"config artifact path: {config_artifact_path}")
    logger.info(f"Run ID: {run_id}")

    # If scaler local download directory already exist, delete it
    if os.path.exists(artifact_download_path):
        logger.info(f"Deleting existing scaler directory: {artifact_download_path}")
        shutil.rmtree(artifact_download_path)
    os.makedirs(artifact_download_path, exist_ok=True)
    for a in ml_client.list_artifacts(run_id, path="run_model"):
        print(f"{a.path}  (dir: {a.is_dir})")
    logger.info(f"Downloading artifacts to {artifact_download_path}")
    #Download scalers
    scaler_local_path = ml_client.download_artifacts(
        run_id=run_id,
        path=scaler_artifact_path,
        dst_path=artifact_download_path
    )

    # scaler_local_path = mlflow.artifacts.download_artifacts(
    #     artifact_uri=scaler_artifact_uri, 
    #     dst_path=artifact_download_path
    # )
    logger.info(f"Scalers downloaded to {scaler_local_path}")

    scalers = joblib.load(scaler_local_path)
    logger.info(f"Scalers loaded: {scalers.keys()}")

    #Download config
    config_local_path = ml_client.download_artifacts(
        run_id=run_id,
        path=config_artifact_path,
        dst_path=artifact_download_path
    )

    # config_local_path = mlflow.artifacts.download_artifacts(
    #     artifact_uri=config_artifact_uri, 
    #     dst_path=artifact_download_path
    # )
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
    logger.info(f"Initial data shape: {data.shape}")
    # Make datetime column a pd.datetime object
    data['Date'] = pd.to_datetime(data['Date'])
    logger.debug("Converted 'Date' column to datetime.")

    # Normalize time gaps
    data = normalize_timegaps_inference(data, config)
    logger.debug("Normalized time gaps in the data.")
    logger.info(f"Data shape after time gap normalization: {data.shape}")
    # Add indicators if needed
    data, selected_indicators = add_all_indicators(data, config)
    logger.debug(f"Added indicators to the data : {selected_indicators}")
    logger.info(f"Data shape after adding indicators: {data.shape}")
    #print(f"Shape after adding indicators: {data.shape}")
    #print("Columns after adding indicators:", data.columns.tolist())
    # Close difference transformation
    data, close_diff_features = close_diff_transform(data, config)
    logger.debug(f"Applied close difference transformation on features: {close_diff_features}")

    logger.info(f"Data shape before scaling: {data.shape}")

    # Scale features
    scale_for_inference(data, config, scalers)

    logger.debug("Data transformation for inference completed.")
    return data


def get_prediction(data, model_high, model_low, training_config, scalers):
    """
    Get predictions from the high and low models.
    """
    max_period = get_maximum_period(training_config)
    # Filter last max period rows
    data = data.tail(max_period+1)
    #print(f"Shape : {data.shape}")
    #print(data)
    data = transform_for_inference(data=data, config=training_config, scalers=scalers)
    data_lastrow = data.iloc[[-1]]
    all_features = get_all_training_features(training_config)
    current_close = data_lastrow['Close'].values[0]
    features_row = data_lastrow[all_features]
    buy_vals = model_high.predict(features_row)
    sell_vals = model_low.predict(features_row)

    buy_take, sell_take = buy_vals[0][0], sell_vals[0][0]
    buy_stop, sell_stop = sell_vals[0][1], buy_vals[0][1]
    label_scaling_multiplier = training_config['common_config']['label_scaling_multiplier']

    buy_take = buy_take * current_close / label_scaling_multiplier
    buy_take = buy_take + current_close

    sell_take = sell_take * current_close / label_scaling_multiplier
    sell_take = current_close - sell_take

    buy_stop = buy_stop * current_close / label_scaling_multiplier
    buy_stop = current_close - buy_stop

    sell_stop = sell_stop * current_close / label_scaling_multiplier
    sell_stop = sell_stop + current_close
    return {
        "buy_take": buy_take,
        "buy_stop": buy_stop,
        "sell_take": sell_take,
        "sell_stop": sell_stop,
        "current_close": current_close
    }


def get_bulk_prediction(data, model_high, model_low, training_config, scalers):
    """
    Get predictions from the high and low models for all rows in the data.
    """
    data = transform_for_inference(data=data.copy(), config=training_config, scalers=scalers)
    all_features = get_all_training_features(training_config)
    
    current_closes = data['Close'].values
    features = data[all_features]
    
    buy_vals = model_high.predict(features)
    sell_vals = model_low.predict(features)
    
    buy_takes = buy_vals[:, 0]
    sell_takes = sell_vals[:, 0]
    buy_stops = sell_vals[:, 1]
    sell_stops = buy_vals[:, 1]
    
    label_scaling_multiplier = training_config['common_config']['label_scaling_multiplier']
    
    buy_takes = (buy_takes * current_closes / label_scaling_multiplier) + current_closes
    sell_takes = current_closes - (sell_takes * current_closes / label_scaling_multiplier)
    buy_stops = current_closes - (buy_stops * current_closes / label_scaling_multiplier)
    sell_stops = (sell_stops * current_closes / label_scaling_multiplier) + current_closes

    data['pred_high'] = buy_takes
    data['pred_low'] = sell_takes
    
    return data

def calculate_ATR_Standalone(data, atr_period, atr_ma):

    data['ATR'] = talib.ATR(data['High'], data['Low'], data['Close'], timeperiod=atr_period)
    data['ADJATR'] = talib.SMA(data['ATR'], timeperiod=atr_ma)
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
    config_path = os.environ['CONFIG_PATH']
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
        alias_info_map = {}
        version_alias_map = {}

        versions = client.search_model_versions(f"name='{model}'")
        for v in versions:
            mv = client.get_model_version(name=model, version=v.version)
            if mv.aliases:
                for alias in mv.aliases:
                    if alias not in version_alias_map:
                        version_alias_map[alias] = []
                    version_alias_map[alias].append(mv.version)
        
        for alias, versions in version_alias_map.items():
            if versions:
                numeric_versions = [int(v) for v in versions]
                latest_version = max(numeric_versions)
                mv = client.get_model_version(name=model, version=latest_version)
                tags = mv.tags if mv.tags else {}
                alias_info_map[alias] = {
                    "version": latest_version,
                    "training_start": tags.get('training_start', ''),
                    "training_end": tags.get('training_end', ''),
                }

        result[model] = alias_info_map
    return result


def get_maximum_period(config):
    """
    Get the maximum period for inference from the config.
    """
    max_period = 0
    for ind_key in config['indicators']['parameters']:
        ind = config['indicators']['parameters'][ind_key]
        if 'period' in ind and isinstance(ind['period'], int):
            if ind['period'] > max_period:
                max_period = ind['period']
    return max_period


def calculate_fields(trade, price, sell_or_buy_threshold, risk_threshold):
    """Calculates buy_diff, sell_diff, risks, ratios, and signals for one trade record."""
    current_close = price.close if price else None

    if current_close is None:
        return None  # Skip if no price data is found

    buy_take = trade.buy_take_profit or 0
    sell_take = trade.sell_take_profit or 0
    buy_stop = trade.buy_stop_loss or 0
    sell_stop = trade.sell_stop_loss or 0

    # --- Base calculations ---
    buy_diff = buy_take - current_close
    sell_diff = current_close - sell_take
    buy_risk = current_close - buy_stop
    sell_risk = sell_stop - current_close

    # --- Ratios ---
    buy_risk_ratio = buy_risk / buy_diff if buy_diff != 0 else 0
    sell_risk_ratio = sell_risk / sell_diff if sell_diff != 0 else 0

    # --- Sell/Buy Ratio ---
    if buy_diff < 0:
        sell_buy_ratio = (abs(buy_diff) + 1) * sell_diff
    else:
        sell_buy_ratio = sell_diff / (buy_diff + 1) if buy_diff != 0 else 0

    # --- Buy/Sell Ratio ---
    if sell_diff < 0:
        buy_sell_ratio = (abs(sell_diff) + 1) * buy_diff
    else:
        buy_sell_ratio = buy_diff / (sell_diff + 1) if sell_diff != 0 else 0

    # --- Signals ---
    buy_signal = buy_sell_ratio > sell_or_buy_threshold and buy_sell_ratio > sell_buy_ratio and buy_risk_ratio < risk_threshold
    sell_signal = sell_buy_ratio > sell_or_buy_threshold and sell_buy_ratio > buy_sell_ratio and sell_risk_ratio < risk_threshold
    signal = 1 if buy_signal else -1 if sell_signal else 0

    return {
        "current_close": current_close,
        "buy_diff": buy_diff,
        "sell_diff": sell_diff,
        "buy_risk": buy_risk,
        "sell_risk": sell_risk,
        "buy_risk_ratio": buy_risk_ratio,
        "sell_risk_ratio": sell_risk_ratio,
        "buy_sell_ratio": buy_sell_ratio,
        "sell_buy_ratio": sell_buy_ratio,
        "buy_signal": buy_signal,
        "sell_signal": sell_signal,
        "signal": signal
    }