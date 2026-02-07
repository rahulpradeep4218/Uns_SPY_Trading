import random
import datetime
from datetime import timedelta

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


def get_closest_trading_date(db, symbol, target_date):

    target_dt = datetime.datetime.combine(
        target_date, datetime.time(0, 0)
    )

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

    if prev_entry is None:
        return next_entry
    if next_entry is None:
        return prev_entry

    prev_diff = abs((prev_entry.time - target_dt).total_seconds())
    next_diff = abs((next_entry.time - target_dt).total_seconds())

    return prev_entry if prev_diff <= next_diff else next_entry


def get_data(symbol: str, start_date: datetime.datetime, end_date: datetime.datetime, db: Session):
    """
    Fetches all the 1 minute candle data for the given date and symbol for the whole day
    also includes the prediction date - high and low values in 2 separate columns
    """

    # Pick 1 random date between start_date and end_date
    random_dt = random_date(start_date, end_date)

    # Find closes trading date
    trading_date_entry = get_closest_trading_date(db, symbol, random_dt)

    if trading_date_entry is None:
        return ValueError(f"No trading data found for symbol {symbol} between {start_date} and {end_date}")
    
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
        return pd.DataFrame()  # Return empty DataFrame if no data found

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

        # We are calculating the prediction for each candle using bulk prediction above
        # pred_res = get_prediction_for_candle(
        #     symbol=symbol,
        #     db=db,
        #     current_candle=current_row,
        #     training_config=training_config,
        #     model_high=model_high,
        #     model_low=model_low,
        #     scalers=scalers
        # )

        # df.at[idx, 'pred_high'] = pred_res['data'][0]
        # df.at[idx, 'pred_low'] = pred_res['data'][1]
        # Calculate slopes for last 2, 5, 10, and 20 close values
        # df.at[idx, 'pred_high_diff'] = pred_res['data'][0] - current_row['Close']
        # df.at[idx, 'pred_low_diff'] = current_row['Close'] - pred_res['data'][1]
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

    return df



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

