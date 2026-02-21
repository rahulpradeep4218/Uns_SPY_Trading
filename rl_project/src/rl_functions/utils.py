import random
import datetime
from datetime import timedelta
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

# from rl_functions.trading_env import TradingEnv
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

from rl_functions.mlflow_sb3callback import MLflowRLCallback

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
    prev_entry = None
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

    next_entry = db.query(PriceData.time).filter(
            PriceData.symbol == symbol,
            PriceData.time >= target_dt
        ).order_by(PriceData.time.asc()).first()
    

    if prev_entry is None or only_next:
        return next_entry
    if next_entry is None:
        return prev_entry

    prev_diff = abs((prev_entry.time - target_dt).total_seconds())
    next_diff = abs((next_entry.time - target_dt).total_seconds())

    chosen = prev_entry if prev_diff <= next_diff else next_entry
    return chosen




# --- Usage Example ---
# my_balances = [1000, 1005, 1002, 1010, 1008] # Your balance list
# metrics = TradeMetrics(my_balances, freq='1min')

# print(f"Annualized Sharpe: {metrics.calculate_sharpe():.4f}")
# print(f"Annualized Sortino: {metrics.calculate_sortino():.4f}")

def get_env(config: dict, db: Session, eval_mode: bool=False, dagster_logger=None):
    """
    Creates and returns a DummyVecEnv wrapped TradingEnv instance based on the provided configuration and database session.
    If eval_mode is True, it sets up the environment for evaluation using test data; otherwise, it sets up for training using training data.
    """
    from rl_functions.trading_env import TradingEnv

    obs_features = get_observation_features(config)
    start_date_config_key = 'train_start_date' if not eval_mode else 'test_start_date'
    end_date_config_key = 'train_end_date' if not eval_mode else 'test_end_date' 
    start_date = datetime.datetime.strptime(config['rl'][start_date_config_key], "%Y-%m-%d").date()
    if not eval_mode:
        start_date_first = get_closest_trading_date(db=db, symbol='SPY', target_date=start_date, only_next=True).time.date()
        start_date = get_closest_trading_date(db=db, symbol='SPY', target_date=start_date_first + datetime.timedelta(days=1), only_next=True).time.date()
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
                            evaluation=eval_mode,
                            logger=dagster_logger
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
        next_date = start_date
        next_avail_date = get_closest_trading_date(db, symbol, next_date, only_next=True)
        if next_avail_date:
            if next_avail_date.time.date() > end_date:
                return pd.DataFrame(), "END_DATE_REACHED"
        else:
            return pd.DataFrame(), "END_DATE_REACHED"
        date_to_get = next_avail_date.time.date()
        
    else:

        # Pick 1 random date between start_date and end_date
        random_dt = random_date(start_date, end_date)

        # Find closes trading date
        trading_date_entry = get_closest_trading_date(db, symbol, random_dt, only_next=True)

        if trading_date_entry is None:
            logger.warning(f"No trading data found for symbol {symbol} between {start_date} and {end_date}")
            return pd.DataFrame(), "NO_DATA_FOR_DATE"
        
        date_to_get = trading_date_entry.time.date()

        # print(f"Selected trading date for data retrieval: {date_to_get}")

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
        # print("Previous date entry found: ", prev_date_entry.time)
        prev_date = prev_date_entry.time.date()

        start_prev = datetime.datetime.combine(prev_date, datetime.time(0, 0))
        end_prev = start_prev + datetime.timedelta(days=1)
        # print(f"Querying previous day data from {start_prev} to {end_prev}")
        prev_day_query = db.query(PriceData).filter(
            PriceData.symbol == symbol,
            PriceData.time >= start_prev,
            PriceData.time < end_prev
        ).order_by(PriceData.time).all()
        # print(f"Previous day data count: {len(prev_day_query)}")
        # print(f"1st entry: {prev_day_query[0].time if prev_day_query else 'N/A'}, Last entry: {prev_day_query[-1].time if prev_day_query else 'N/A'}")
        if prev_day_query:
            prev_day_rows = [{
                'Date': entry.time,
                'Open': entry.open,
                'High': entry.high,
                'Low': entry.low,
                'Close': entry.close,
                'Volume': entry.volume,
            } for entry in prev_day_query[-rl_lookback_period-max(slope_column_numbers)+1:]]  # last rl_lookback_period rows

    start_datetime = datetime.datetime.combine(date_to_get, datetime.time(0, 0))
    end_datetime = start_datetime + datetime.timedelta(days=1)
    # print(f"Querying price data for {symbol} from {start_datetime} to {end_datetime}")
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
    start_idx = max(slope_column_numbers)-1
    # print(f"1st entry after adding prev day rows: {df.iloc[0]['Date']}, idx {start_idx} entry: {df.iloc[start_idx]['Date'] if start_idx < len(df) else 'N/A'}")
    # print("start_idx:", start_idx)

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
        df = df.iloc[start_idx+1:].reset_index(drop=True)
    # print("Final df after removing prev rows")
    # print(df.head())
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


def get_first_directory(config, model_metadata):
    details_cfg = config['rl']
    model_id = model_metadata.get('model_id', '')
    start_date = details_cfg['train_start_date']
    end_date = details_cfg['train_end_date']
    return f"{model_id}_{start_date}_{end_date}"



def get_dagster_runs_folder_path(config):
    details_cfg = config['training_details']
    runs_folder = details_cfg['runs_folder']
    return f"{runs_folder}"

def get_dagster_run_id_rl_path(config, filename_or_foldername, model_metadata={}):
    first_directory = get_first_directory(config, model_metadata)
    runs_folder = get_dagster_runs_folder_path(config)
    return os.path.join(runs_folder, f'{first_directory}', filename_or_foldername)

############ RL functions ##############

def download_rl_mlflow_latest_version_artifact(config: dict, artifact_model_folder: str, run_id: str, model_metadata={}):
    
    client = MlflowClient()
    runs_folder = config['training_details']['runs_folder']
    first_directory = get_first_directory(config, model_metadata)
    tmp_dir = os.path.join(runs_folder, first_directory)
    os.makedirs(tmp_dir, exist_ok=True)
    model_path = client.download_artifacts(run_id=run_id, path=f"{artifact_model_folder}/artifacts/model.zip", dst_path=tmp_dir + "/model.zip")
    vec_path = client.download_artifacts(run_id=run_id, path=f"{artifact_model_folder}/artifacts/vec_normalize.pkl", dst_path=tmp_dir + "/vec_normalize.pkl")
    # model_name = config['rl']['model_name']
    # model_path = f"{local_dir}/artifacts/model.zip"
    # vec_path = f"{local_dir}/artifacts/vec_normalize.pkl"
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
    run = client.get_run(run_id)
    last_checkpoint_step = run.data.tags.get("last_checkpoint_step")
    latest_checkpoint_folder = f'checkpoint_{last_checkpoint_step}'
    return latest_checkpoint_folder


def load_checkpoint(run_id: str, env, config: dict, db: Session):
    model_path, vec_path = download_rl_mlflow_latest_version_artifact(config, db, run_id)
    model = PPO.load(model_path, env=env)
    env = VecNormalize.load(vec_path, env=env)

    return model, env


def get_latest_timestep(run_id: str):
    run = mlflow.get_run(run_id)
    latest_time_steps = run.data.metrics['timestep']
    return latest_time_steps

def get_eval_num(run_id: str):
    run = mlflow.get_run(run_id)
    eval_num = run.data.metrics.get('eval_num', 1)
    return eval_num

def get_avg_trade_duration(run_id: str):
    run = mlflow.get_run(run_id)
    avg_trade_duration = run.data.metrics.get('avg_trade_duration', 0)
    return avg_trade_duration

def make_cyclic_entropy(cycle_steps=5000, total_steps=100000):
    def cyclic_entropy(progress_remaining):
        # Calculate current step: 1.0 -> 0 steps, 0.0 -> total_steps
        current_step = (1.0 - progress_remaining) * total_steps
        
        # This creates a value from 0 to 1 that resets every 'cycle_steps'
        # 0.0 at start of cycle, 1.0 at end of cycle
        phase = (current_step % cycle_steps) / cycle_steps
        
        # High entropy (0.05) at the start of cycle, decaying to 0.01
        # We use (1 - phase) so it starts high and goes low
        decay = 0.05 * (0.5 ** (phase * 5)) # Exponential decay within the cycle
        
        return max(0.01, decay)

    return cyclic_entropy

def do_training_with_resume(config: dict, dagster_context, model_metadata: dict = {}):

    db: Session = SessionLocal()
    mlflow.set_tracking_uri(config['mlflow']['tracking_uri'])
    ml_client = MlflowClient()
    dagster_run_id = dagster_context.run_id
    eval_num = 1
    checkpoints_local_path = get_dagster_run_id_rl_path(config=config, 
                                                        filename_or_foldername="checkpoints",
                                                        model_metadata=model_metadata
                                                        )
    dagster_context.log.info(f"Checkpoints will be saved to: {checkpoints_local_path}")
    run_id = get_latest_run_id_using_tag(model_name=config['rl']['model_name'])


    env = get_env(config=config, db=db, eval_mode=False, dagster_logger=dagster_context.log)
    cyclic_update = config['rl']['cyclic_entropy_update_freq']
    total_timesteps = config['rl']['total_timesteps']
    ent_coef_fn = 0.04

    if run_id:
        dagster_context.log.info(f"Latest run id for model {config['rl']['model_name']} with IN_PROGRESS status: {run_id} , so Resuming training from checkpoint")
        mlflow.start_run(run_id=run_id)
        latest_timestep = get_latest_timestep(run_id)
        eval_num = get_eval_num(run_id)
        avg_trade_duration = get_avg_trade_duration(run_id)
        dagster_context.log.info(f"Latest timestep for run_id {run_id} is {latest_timestep}")
        # model, env = load_checkpoint(run_id, env, config, db)
        latest_artifact_folder = get_latest_model_checkpoint_folder(run_id)

        if latest_artifact_folder:
            model_path, vec_path = download_rl_mlflow_latest_version_artifact(config=config,
                                                                          artifact_model_folder=latest_artifact_folder, 
                                                                          run_id=run_id,
                                                                          model_metadata=model_metadata
                                                                         )
            model = PPO.load(model_path, 
                            env=env, 
                        )

            env = VecNormalize.load(vec_path, venv=env)

            # Set the training env in model
            model.set_env(env)
        else:
            dagster_context.log.warning(f"No checkpoint folders found for run_id {run_id}. Starting training from scratch.")
        

    else:
        dagster_context.log.info("No checkpoint found. Starting training from scratch.")
        latest_timestep = 0
        mlflow.start_run(run_name=f"RL_Training_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}", tags={"model_name": config['rl']['model_name'], "status": "IN_PROGRESS"})
        run_id = mlflow.active_run().info.run_id
        policy_kwargs = dict(net_arch=[128, 128])
        env = VecNormalize(env, norm_obs=True, norm_reward=True, clip_obs=10.)
        model = PPO(
            policy='MlpPolicy',
            env=env,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=128,
            gamma=0.98,
            gae_lambda=0.95,
            clip_range=0.2,
            verbose=1,
            policy_kwargs=policy_kwargs,
        )

    total_target_timesteps = config['rl']['total_timesteps']
    remaining_timesteps = total_target_timesteps - latest_timestep

    mlflow_callback = MLflowRLCallback(
        run_id=run_id,
        artifact_subdir=checkpoints_local_path,
        model_name=config['rl']['model_name'],
        db=db,
        config=config,
        eval_num=eval_num,
        dagster_logger=dagster_context.log
    )
    model.learn(total_timesteps=remaining_timesteps, 
                reset_num_timesteps=False,
                callback=mlflow_callback
    )
    mlflow.set_tag("status", "Done")
    db.close()

    # model.save("ppo_trading_agent")
    # env.save("vec_normalize_trading_env.pkl")



################ End of RL Functions ################