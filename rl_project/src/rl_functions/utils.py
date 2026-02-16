import random
import datetime
from datetime import timedelta

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from rl_functions.trading_env import TradingEnv
from trading_functions.db.session import SessionLocal
from trading_functions.db.models import PriceData
from trading_functions.inference.inf_functions import (
    download_artifacts,
    get_model_from_mlflow,
    get_maximum_period,
    get_prediction,
    get_bulk_prediction
)
from trading_functions.common.indicators import (
    calculate_ATR
)

from mlflow_sb3callback import MLflowRLCallback

from sqlalchemy.orm import Session
from sqlalchemy import desc
import numpy as np
import pandas as pd
import os
import yaml
from typing import Dict, Any
import logging
logger = logging.getLogger(__name__)
from dotenv import load_dotenv
import mlflow
from mlflow.tracking import MlflowClient
import re

load_dotenv()

def get_inf_config():
    inf_config_path = os.getenv('CONFIG_PATH', 'NO_PATH')
    if not inf_config_path or not os.path.exists(inf_config_path):
        raise FileNotFoundError(f"Configuration file not found at {inf_config_path}")
    logger.info(f"Loading inference configuration from {inf_config_path}")
    with open(inf_config_path, 'r') as file:
        inf_config = yaml.safe_load(file)
    
    return inf_config


def get_observation_features(inf_config: dict):
    slopes = inf_config['rl']['slopes']
    slope_column_numbers = [int(s) for s in slopes.split(',')]
    base_columns = ['pred_high', 'pred_low', 'pred_high_error', 'pred_low_error', 'pred_high_diff', 'pred_low_diff', 'momentum_short', 'velocity_short']
    for s in slope_column_numbers:
        base_columns.append(f'slope_last{s}close')
        base_columns.append(f'pred_high_slope_last{s}')
        base_columns.append(f'pred_low_slope_last{s}')
    return base_columns


def get_random_weekday(year, db: Session):
    """
    Returns a random date from the given year that is not a Saturday or Sunday.
    """
    # Query all dates in PriceData for the given year
    dates = db.query(PriceData.time).filter(
        PriceData.time >= datetime.date(year, 1, 1),
        PriceData.time <= datetime.date(year, 12, 31)
    ).all()
    if not dates:
        return None
    # Ignore the first date in the list
    if len(dates) <= 1:
        return None
    random_date = random.choice([d['time'] for d in dates[1:]])
    return random_date



def get_slope_values(values: pd.Series):
    if len(values) < 2:
        return 0
    x = np.arange(len(values))
    y = values.to_numpy()
    A = np.vstack([x, np.ones(len(x))]).T
    m, c = np.linalg.lstsq(A, y, rcond=None)[0]
    return m



def get_prediction_for_candle(
        symbol: str,
        db: Session,
        current_candle: pd.Series,
        training_config: dict,
        model_high: Any,
        model_low: Any,
        scalers: Dict[str, Any],
        max_gap_days_allowed: int = 3
):
    max_period = get_maximum_period(training_config)
    
    candles_query = db.query(PriceData).filter(
        PriceData.symbol == symbol,
        PriceData.time <= current_candle['Date'],
    ).order_by(desc(PriceData.time)).limit(max_period)

    # Convert to pandas series (Columns)
    candles_columns = candles_query.all()
    if len(candles_columns) < max_period:
        return {"status": "NO_ENOUGH_LAGGING_DATA",
                "message": f"Not enough lagging data for symbol {symbol} to run simulation.",
                "data": [0,0]
               }
    gap = current_candle['Date'] - candles_columns[-1].time
    if gap > timedelta(days=max_gap_days_allowed):
        return {"status": "LAGGING_DATA_GAP_TOO_LARGE",
                "message": f"Current candle time {current_candle['Date']} is more than {max_gap_days_allowed} of the last lagging candle using max period : {max_period} ,  {candles_columns[-1].time} for symbol {symbol}.",
                "data": [0,0]
               }

    data = pd.DataFrame([
        {
            "Date": candle.time,
            "Open": candle.open,
            "High": candle.high,
            "Low": candle.low,
            "Close": candle.close,
            "Volume": candle.volume
        } for candle in candles_columns
    ])

    pred_dict = get_prediction(
        data=data,
        model_high=model_high,
        model_low=model_low,
        training_config=training_config,
        scalers=scalers
    )
    buy_take, sell_take, buy_stop, sell_stop = float(pred_dict["buy_take"]), float(pred_dict["sell_take"]), float(pred_dict["buy_stop"]), float(pred_dict["sell_stop"])
    return {"status": "OK",
            "message": "Prediction successful",
            "data": [buy_take, sell_take]
           }
    

def add_momentum_and_velocity_short(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    # Normalized momentum (% change over the lookback period)
    df['momentum_short'] = (df['Close'] - df['Close'].shift(period)) / df['Close'].shift(period)
    
    # Smooth momentum using EMA to reduce noise
    df['momentum_short'] = df['momentum_short'].ewm(span=period).mean()
    
    # Velocity = first derivative of momentum (acceleration)
    df['velocity_short'] = df['momentum_short'].diff()
    return df


def random_date(start_date, end_date):
    delta_days = (end_date - start_date).days
    return start_date + datetime.timedelta(days=random.randint(0, delta_days))


def get_closest_trading_date(db, symbol, target_date, only_next=False):

    target_dt = datetime.datetime.combine(
        target_date, datetime.time(0, 0)
    )
    if not only_next:
        prev_entry = (
            db.query(PriceData.time)
            .filter(
                PriceData.symbol == symbol,
                PriceData.time <= target_dt
            )
            .order_by(PriceData.time.desc())
            .first()
        )

    next_entry = (
        db.query(PriceData.time)
        .filter(
            PriceData.symbol == symbol,
            PriceData.time >= target_dt
        )
        .order_by(PriceData.time.asc())
        .first()
    )

    if prev_entry is None or only_next:
        return next_entry
    if next_entry is None:
        return prev_entry

    prev_diff = abs((prev_entry.time - target_dt).total_seconds())
    next_diff = abs((next_entry.time - target_dt).total_seconds())

    return prev_entry if prev_diff <= next_diff else next_entry



def calculate_sharpe(returns, risk_free_rate=0.0):
    returns = np.array(returns)
    excess_returns = returns - risk_free_rate
    if excess_returns.std() == 0:
        return 0.0
    return np.sqrt(252) * excess_returns.mean() / excess_returns.std()


def get_env(config: dict, db: Session, eval_mode: bool=False):
    """
    Creates and returns a DummyVecEnv wrapped TradingEnv instance based on the provided configuration and database session.
    If eval_mode is True, it sets up the environment for evaluation using test data; otherwise, it sets up for training using training data.
    """
    obs_features = get_observation_features(config)
    start_date_config_key = 'train_start_date' if not eval_mode else 'test_start_date'
    end_date_config_key = 'train_end_date' if not eval_mode else 'test_end_date' 
    start_date = datetime.datetime.strptime(config['rl'][start_date_config_key], "%Y-%m-%d").date()
    end_date = datetime.datetime.strptime(config['rl'][end_date_config_key], "%Y-%m-%d").date()
    initial_balance = float(config['rl']['initial_balance'])
    trade_fee = float(config['rl']['trade_fee'])
    max_trade_loss_percent = float(config['rl']['max_trade_loss_percent'])
    price_multiplier = float(config['rl']['price_multiplier'])


    def make_env():
        return TradingEnv(db=db,
                          symbol='SPY',
                          start_date=start_date,
                          end_date=end_date,
                          initial_balance=initial_balance,
                          trade_fee=trade_fee,
                          max_trade_loss_percent=max_trade_loss_percent,
                          obs_features=obs_features,
                          price_multiplier=price_multiplier,
                            evaluation=eval_mode
                          )
    
    return DummyVecEnv([make_env])
   

def get_data(symbol: str, start_date: datetime.datetime, end_date: datetime.datetime, db: Session, evaluation: bool = False):
    """
    Fetches all the 1 minute candle data for the given date and symbol for the whole day
    also includes the prediction date - high and low values in 2 separate columns
    Returns the dataframe plus status code
    Status code can be:
    - OK
    - NO_DATA_FOR_DATE
    - END_DATE_REACHED (in case of evaluation and next day data not available)
    - NO_ENOUGH_LAGGING_DATA (in case there is not enough lagging data to make prediction for the day)
    """

    if evaluation:
        print("Evaluation mode: ON")
        next_date = start_date + timedelta(days=1)
        next_avail_date = get_closest_trading_date(db, symbol, next_date, only_next=True)
        if next_avail_date > end_date:
            return pd.DataFrame(), "END_DATE_REACHED"
        date_to_get = next_avail_date.time.date()
        
    else:
        # Pick 1 random date between start_date and end_date
        random_dt = random_date(start_date, end_date)

        # Find closes trading date
        trading_date_entry = get_closest_trading_date(db, symbol, random_dt)

        if trading_date_entry is None:
            logger.warning(f"No trading data found for symbol {symbol} between {start_date} and {end_date}")
            return pd.DataFrame(), "NO_DATA_FOR_DATE"
        
        date_to_get = trading_date_entry.time.date()

        print(f"Selected trading date for data retrieval: {date_to_get}")

    slope_column_numbers = [3,9,39,99]
    inf_config = get_inf_config()

    scalers, training_config, model_high, model_low = get_data_for_model_inference(inf_config)



    rl_lookback_period = inf_config['rl']['max_period_lookback']
    # Get the previous date
    # previous_date = date_to_get.date() - datetime.timedelta(days=1)
    # start_prev = datetime.datetime.combine(previous_date, datetime.time(0, 0))
    # end_prev = start_prev + datetime.timedelta(days=1)

    prev_date_entry = (
        db.query(PriceData.time)
        .filter(
            PriceData.symbol == symbol,
            PriceData.time < datetime.datetime.combine(date_to_get, datetime.time(0, 0))
        )
        .order_by(PriceData.time.desc())
        .first()
    )

    # Query the previous day's data and get the last 25 rows

    prev_day_rows = []
    if prev_date_entry:
        prev_date = prev_date_entry.time.date()

        start_prev = datetime.datetime.combine(prev_date, datetime.time(0, 0))
        end_prev = start_prev + datetime.timedelta(days=1)

        prev_day_query = db.query(PriceData).filter(
            PriceData.symbol == symbol,
            PriceData.time >= start_prev,
            PriceData.time < end_prev
        ).order_by(PriceData.time).all()

        if prev_day_query:
            prev_day_rows = [{
                'Date': entry.time,
                'Open': entry.open,
                'High': entry.high,
                'Low': entry.low,
                'Close': entry.close,
                'Volume': entry.volume,
            } for entry in prev_day_query[-rl_lookback_period:]]  # last rl_lookback_period rows

    start_datetime = datetime.datetime.combine(date_to_get, datetime.time(0, 0))
    end_datetime = start_datetime + datetime.timedelta(days=1)

    price_data_query = db.query(PriceData).filter(
        PriceData.symbol == symbol,
        PriceData.time >= start_datetime,
        PriceData.time < end_datetime
    ).order_by(PriceData.time).all()

    if not price_data_query:
        return pd.DataFrame(), "NO_DATA_FOR_DATE"  # Return empty DataFrame if no data found

    df = pd.DataFrame([{
        'Date': entry.time,
        'Open': entry.open,
        'High': entry.high,
        'Low': entry.low,
        'Close': entry.close,
        'Volume': entry.volume,
    } for entry in price_data_query])
    # Add pred_high and pred_low columns initialized with NaN

    if prev_day_rows:
        prev_df = pd.DataFrame(prev_day_rows)
        # Normalize prev_df OHLC by the gap between last prev_df close and first df open
        gap = df.iloc[0]['Open'] - prev_df.iloc[-1]['Close']
        prev_df[['Open', 'High', 'Low', 'Close']] = prev_df[['Open', 'High', 'Low', 'Close']] + gap
        df = pd.concat([prev_df, df], ignore_index=True)
        start_idx = len(prev_day_rows)
    else:
        start_idx = 0

    print("start_idx:", start_idx)

    #df['pred_high'] = np.nan
    #df['pred_low'] = np.nan

    df = get_bulk_prediction(
        data=df,
        model_high=model_high,
        model_low=model_low,
        training_config=training_config,
        scalers=scalers,
    )
    df = df.reset_index(drop=True)
    #print(df[['Date','pred_high','pred_low']].tail(10))
    df['pred_high_diff'] = df['pred_high'] - df['Close']
    df['pred_low_diff'] = df['Close'] - df['pred_low']

    for idx in range(start_idx, len(df)):
        #print(f"Processing row {idx+1} of {len(df)}")
        current_row = df.iloc[idx]

        for window in slope_column_numbers:
            col_name = f'slope_last{window}close'
            if idx - window + 1 >= 0:
                close_slice = df.loc[idx - window + 1:idx, 'Close']
                slope = get_slope_values(close_slice)
            else:
                slope = np.nan
            df.at[idx, col_name] = slope

        for window in slope_column_numbers:
            col_name = f'pred_high_slope_last{window}'
            if idx - window + 1 >= 0:
                pred_high_slice = df.loc[idx - window + 1:idx, 'pred_high']
                slope = get_slope_values(pred_high_slice)
            else:
                slope = np.nan
            df.at[idx, col_name] = slope

        for window in slope_column_numbers:
            col_name = f'pred_low_slope_last{window}'
            if idx - window + 1 >= 0:
                pred_low_slice = df.loc[idx - window + 1:idx, 'pred_low']
                slope = get_slope_values(pred_low_slice)
            else:
                slope = np.nan
            df.at[idx, col_name] = slope


        n = inf_config['common_config']['num_bars_to_look_labels']  # You can set n to any window size you want
        if idx - n + 1 >= 0:
            highest_pred_high = df.loc[idx - n + 1:idx, 'High'].max()
            lowest_pred_low = df.loc[idx - n + 1:idx, 'Low'].min()
            pred_high_error = df.at[idx, 'pred_high'] - highest_pred_high
            pred_low_error = df.at[idx, 'pred_low'] - lowest_pred_low
            #print(f"pred_high_error: {pred_high_error}, pred_low_error: {pred_low_error} at index {idx}")
        else:
            pred_high_error = np.nan
            pred_low_error = np.nan

        df.at[idx, 'pred_high_error'] = pred_high_error
        df.at[idx, 'pred_low_error'] = pred_low_error

    df = add_momentum_and_velocity_short(df, period=14)
    # After all calculations, keep only the current day's records (exclude prev_day_rows)
    if prev_day_rows:
        df = df.iloc[len(prev_day_rows):].reset_index(drop=True)
    #print(df)
    df = calculate_ATR(df, inf_config['indicators']['parameters'], column='Close')

    return df, "OK"



def get_data_for_model_inference(inf_config: dict):
    high_version = inf_config['rl']['model_high_version']
    low_version = inf_config['rl']['model_low_version']
    high_alias = inf_config['rl']['model_high_alias']

    inf_config = get_inf_config()
    scalers, training_config = download_artifacts(
        config=inf_config,
        alias=high_alias,
    )

    model_high = get_model_from_mlflow(
        config=inf_config,
        model_name=inf_config['mlflow']['high_model_name'],
        model_version=high_version
    )
    model_low = get_model_from_mlflow(
        config=inf_config,
        model_name=inf_config['mlflow']['low_model_name'],
        model_version=low_version
    )
    return scalers, training_config, model_high, model_low




############ RL functions ##############

def download_rl_mlflow_latest_version_artifact(config: dict, artifact_model_folder: str, run_id: str):
    
    client = MlflowClient()
    tmp_dir = config['rl']['model_artifact_path']
    local_dir = client.download_artifacts(run_id=run_id, path=artifact_model_folder, dst_path=tmp_dir)
    model_name = config['rl']['model_name']
    model_path = f"{local_dir}/artifacts/model.zip"
    vec_path = f"{local_dir}/artifacts/vec_normalize.pkl"
    # model_path = client.download_artifacts(run_id, "model.zip", dst_path=tmp_dir)
    # vec_path = client.download_artifacts(run_id, "vec_normalize.pkl", dst_path=tmp_dir)
    return model_path, vec_path


def get_latest_checkpoint_rl(model_name: str):
    client = MlflowClient()

    versions = client.get_latest_versions(model_name)
    if not versions:
        return None
    
    latest_version = max(versions, key=lambda v: v.version)
    run_id = latest_version.run_id

    return run_id

def get_latest_run_id_using_tag(model_name):
    runs = mlflow.search_runs(
        filter_string=f'tags.model_name = "{model_name}" AND tags.status = "IN_PROGRESS"',
        order_by=["attributes.start_time DESC"],
        max_results=1
    )
    return runs.iloc[0]['run_id'] if not runs.empty else None

def get_latest_model_checkpoint_folder(run_id: str):
    client = MlflowClient()
    artifacts = client.list_artifacts(run_id)
    step_folders = [f.path for f in artifacts if "model_step_" in f.path]

    def get_step_num(path):
        return int(re.search(r'model_step_(\d+)', path).group(1))
    
    latest_folder = max(step_folders, key=get_step_num) if step_folders else None
    return latest_folder


def load_checkpoint(run_id: str, env, config: dict, db: Session):
    model_path, vec_path = download_rl_mlflow_latest_version_artifact(config, db, run_id)
    model = PPO.load(model_path, env=env)
    env = VecNormalize.load(vec_path, env=env)

    return model, env


def get_latest_timestep(run_id: str):
    run = mlflow.get_run(run_id)
    latest_time_steps = run.data.metrics['timestep']
    return latest_time_steps


def do_training_with_resume(config: dict, db: Session, artifact_save_local_path: str):

    mlflow.set_tracking_uri(config['mlflow']['tracking_uri'])
    ml_client = MlflowClient()
    run_id = get_latest_run_id_using_tag(model_name=config['rl']['model_name'])

    env = get_env(config=config, db=db, eval_mode=False)
    if run_id:
        print(f"Resuming training from checkpoint with run_id: {run_id}")
        mlflow.start_run(run_id=run_id)
        latest_timestep = get_latest_timestep(run_id)
        # model, env = load_checkpoint(run_id, env, config, db)
        latest_artifact_folder = get_latest_model_checkpoint_folder(run_id)
        model_path, vec_path = download_rl_mlflow_latest_version_artifact(config=config,
                                                                          artifact_model_folder=latest_artifact_folder, 
                                                                          run_id=run_id)
        model = PPO.load(model_path, env=env)
        env = VecNormalize.load(vec_path, env=env)

    else:
        print("No checkpoint found. Starting training from scratch.")
        latest_timestep = 0
        mlflow.start_run(run_name=f"RL_Training_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}", tags={"model_name": config['rl']['model_name'], "status": "IN_PROGRESS"})
        run_id = mlflow.active_run().info.run_id
        model = PPO(
            policy='MlpPolicy',
            env=env,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=128,
            gamma=0.98,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
            verbose=1,
        )

    total_target_timesteps = config['rl']['total_timesteps']
    remaining_timesteps = total_target_timesteps - latest_timestep

    mlflow_callback = MLflowRLCallback(
        run_id=run_id,
        artifact_subdir=artifact_save_local_path,
        model_name=config['rl']['model_name'],
        db=db,
        config=config
    )
    model.learn(total_timesteps=remaining_timesteps, 
                reset_num_timesteps=False,
                callback=mlflow_callback
    )

    model.save("ppo_trading_agent")
    env.save("vec_normalize_trading_env.pkl")



################ End of RL Functions ################