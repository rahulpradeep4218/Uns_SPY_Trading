import random
import datetime
from datetime import timedelta
from trading_functions.db.session import SessionLocal
from trading_functions.db.models import PriceData
from trading_functions.inference.inf_functions import (
    download_artifacts,
    get_model_from_mlflow,
    get_maximum_period,
    get_prediction
)
from sqlalchemy.orm import Session
from sqlalchemy import desc
import numpy as np
import pandas as pd
import os
import yaml
from typing import Dict, Any


def get_inf_config():
    inf_config_path = os.getenv('CONFIG_PATH', 'NO_PATH')
    if not inf_config_path or not os.path.exists(inf_config_path):
        raise FileNotFoundError(f"Configuration file not found at {inf_config_path}")
    
    with open(inf_config_path, 'r') as file:
        inf_config = yaml.safe_load(file)
    
    return inf_config


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
        PriceData.time <= current_candle['time'],
    ).order_by(desc(PriceData.time)).limit(max_period)

    # Convert to pandas series (Columns)
    candles_columns = candles_query.all()
    if len(candles_columns) < max_period:
        return {"status": "NO_ENOUGH_LAGGING_DATA",
                "message": f"Not enough lagging data for symbol {symbol} to run simulation.",
                "data": [0,0]
               }
    gap = current_candle['time'] - candles_columns[-1].time
    if gap > timedelta(days=max_gap_days_allowed):
        return {"status": "LAGGING_DATA_GAP_TOO_LARGE",
                "message": f"Current candle time {current_candle['time']} is more than {max_gap_days_allowed} of the last lagging candle using max period : {max_period} ,  {candles_columns[-1].time} for symbol {symbol}.",
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
    # Calculate short-term momentum as the difference between the current close and the close 'period' bars ago
    df['momentum_short'] = df['close'] - df['close'].shift(period)
    # Calculate short-term velocity as the change in momentum over the same period
    df['velocity_short'] = df['momentum_short'] - df['momentum_short'].shift(period)
    return df


def get_data(symbol: str, date_to_get: datetime.datetime, db: Session):
    """
    Fetches all the 1 minute candle data for the given date and symbol for the whole day
    also includes the prediction date - high and low values in 2 separate columns
    """
    slope_column_numbers = [3,9,39,99]
    inf_config = get_inf_config()

    scalers, training_config, model_high, model_low = get_data_for_model_inference(inf_config)



    rl_lookback_period = inf_config['rl']['max_period_lookback']
    # Get the previous date
    previous_date = date_to_get.date() - datetime.timedelta(days=1)
    start_prev = datetime.datetime.combine(previous_date, datetime.time(0, 0))
    end_prev = start_prev + datetime.timedelta(days=1)

    # Query the previous day's data and get the last 25 rows
    prev_day_query = db.query(PriceData).filter(
        PriceData.symbol == symbol,
        PriceData.time >= start_prev,
        PriceData.time < end_prev
    ).order_by(PriceData.time).all()

    prev_day_rows = []
    if prev_day_query:
        prev_day_rows = [{
            'time': entry.time,
            'open': entry.open,
            'high': entry.high,
            'low': entry.low,
            'close': entry.close,
            'volume': entry.volume,
        } for entry in prev_day_query[-rl_lookback_period:]]  # last rl_lookback_period rows

    start_datetime = datetime.datetime.combine(date_to_get.date(), datetime.time(0, 0))
    end_datetime = start_datetime + datetime.timedelta(days=1)

    price_data_query = db.query(PriceData).filter(
        PriceData.symbol == symbol,
        PriceData.time >= start_datetime,
        PriceData.time < end_datetime
    ).order_by(PriceData.time).all()

    if not price_data_query:
        return pd.DataFrame()  # Return empty DataFrame if no data found

    df = pd.DataFrame([{
        'time': entry.time,
        'open': entry.open,
        'high': entry.high,
        'low': entry.low,
        'close': entry.close,
        'volume': entry.volume,
    } for entry in price_data_query])
    # Add pred_high and pred_low columns initialized with NaN

    if prev_day_rows:
        prev_df = pd.DataFrame(prev_day_rows)
        # Normalize prev_df OHLC by the gap between last prev_df close and first df open
        gap = df.iloc[0]['open'] - prev_df.iloc[-1]['close']
        prev_df[['open', 'high', 'low', 'close']] = prev_df[['open', 'high', 'low', 'close']] + gap
        df = pd.concat([prev_df, df], ignore_index=True)

    df['pred_high'] = np.nan
    df['pred_low'] = np.nan

    for idx in range(len(prev_day_rows), len(df)):
        current_row = df.iloc[idx]
        pred_res = get_prediction_for_candle(
            symbol=symbol,
            db=db,
            current_candle=current_row,
            training_config=training_config,
            model_high=model_high,
            model_low=model_low,
            scalers=scalers
        )

        df.at[idx, 'pred_high'] = pred_res['data'][0]
        df.at[idx, 'pred_low'] = pred_res['data'][1]
        # Calculate slopes for last 2, 5, 10, and 20 close values
        for window in slope_column_numbers:
            col_name = f'slope_last{window}close'
            if idx - window + 1 >= 0:
                close_slice = df.loc[idx - window + 1:idx, 'close']
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


        n = 10  # You can set n to any window size you want
        if idx - n + 1 >= 0:
            highest_pred_high = df.loc[idx - n + 1:idx, 'high'].max()
            lowest_pred_low = df.loc[idx - n + 1:idx, 'low'].min()
            pred_high_error = df.at[idx, 'pred_high'] - highest_pred_high
            pred_low_error = df.at[idx, 'pred_low'] - lowest_pred_low
        else:
            pred_high_error = np.nan
            pred_low_error = np.nan

        df.at[idx, 'pred_high_error'] = pred_high_error
        df.at[idx, 'pred_low_error'] = pred_low_error

        df = add_momentum_and_velocity_short(df, period=14)
        # After all calculations, keep only the current day's records (exclude prev_day_rows)
        if prev_day_rows:
            df = df.iloc[len(prev_day_rows):].reset_index(drop=True)

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

