import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta, time
from rl_functions.utils import get_data_for_model_inference_parameter_values, get_slope_values
from rl_functions.utils import get_closest_trading_date
from rl_functions.utils import add_momentum_and_velocity_short
from trading_functions.db.models import PriceData
from trading_functions.inference.inf_functions import (
    get_bulk_prediction,
    get_prediction,
    get_maximum_period
)
from trading_functions.common.indicators import calculate_ATR
import logging
import os

log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)

class RL_Stream_Data:
    def __init__(self, db, symbol, inf_config, model_high_version, model_low_version, model_high_alias, simulation_mode=True, start_time: datetime=None, end_time: datetime=None, logger=None):
        
        self.db = db
        self.symbol = symbol
        self.inf_config = inf_config
        self.simulation_mode = simulation_mode
        self.model_high_version = model_high_version
        self.model_low_version = model_low_version
        self.model_high_alias = model_high_alias
        self.current_day = start_time.date() if start_time else datetime.now().date()
        self.start_time = start_time
        self.end_time = end_time
        self.logger = logger or logging.getLogger(__name__)
        self.logger.debug("Debug mode is ON! in RLStreamer")
        self.logger.info(f"Initialized RL_Stream_Data with symbol: {self.symbol}, simulation_mode: {self.simulation_mode}, start_time: {self.start_time}, end_time: {self.end_time}")
        
        # 1. ONE-TIME SETUP: Load expensive artifacts
        self.logger.info(f"Loading models and scalers for xgboost model high version: {self.model_high_version} , model low version: {self.model_low_version} , high alias: {self.model_high_alias}")
        self.scalers, self.training_config, self.xg_model_high, self.xg_model_low = \
        get_data_for_model_inference_parameter_values(
            high_version=self.model_high_version, 
            low_version=self.model_low_version,
            high_alias=self.model_high_alias                                             
        )
        
        # self.rl_lookback = self.inf_config['rl']['max_period_lookback']
        self.rl_lookback = get_maximum_period(self.training_config)  # This function checks all the periods used in indicators and slopes and returns the maximum one, so that we can look back that many rows in history to calculate all indicators/slopes on the fly for the new row
        self.logger.info(f"Calculated rl_lookback (maximum period to look back for indicators/slopes): {self.rl_lookback}")
        self.slope_windows = [3, 9, 39, 99]
        self.clip_num = - self.rl_lookback - max(self.slope_windows) + 1 # We need at least this many rows to calculate all slopes/errors for the new row
        self.last_ts = None
        
        # 2. CACHED DATA: Store enough history to calculate slopes/ATR on the fly
        # We need at least max(slope_windows) + ATR period rows
        self.history_buffer = pd.DataFrame()
        self.rl_data_buffer = pd.DataFrame() # This will store the processed data with indicators for the current day, which we will use to feed into the model for predictions. We keep this separate from history_buffer which is raw price data, so that we don't have to recalculate indicators for the entire history every time.

        # Initialize the variables to calculate the progress for the day
        self.day_total_bars = 0.0
        self.day_current_idx = 0

    def _prepare_day_initial_state(self):
        """
        Creates an initial data buffer for current day which only includes prev day data, and not todays data. 
        We will then use this data to go through each bars of the current day
        This requires atleast 1 bar in current day to calculate the gap between the last bar of previous day
        and the current day`s 1st bar. we then use this gap to adjust the prev days values.
        """
        print("Warming up current day history buffer...")
    
        prev_date_entry = (
            self.db.query(PriceData.time)
            .filter(
                PriceData.symbol == self.symbol,
                PriceData.time < datetime.combine(self.current_day, time(0, 0))
            )
            .order_by(PriceData.time.desc())
            .first()
        )
        if prev_date_entry is None:
            raise ValueError(f"No historical data found for symbol {self.symbol} before {self.current_day}, so cannot initialize streamer. Run for a day where previous day data exists.")

        prev_date = prev_date_entry.time.date()
        self.logger.info(f"Previous date entry found: {prev_date}")

        start_prev = datetime.combine(prev_date, time(0, 0))
        end_prev = start_prev + timedelta(days=1)
        # print(f"Querying previous day data from {start_prev} to {end_prev}")
        prev_day_query = self.db.query(PriceData).filter(
            PriceData.symbol == self.symbol,
            PriceData.time >= start_prev,
            PriceData.time < end_prev
        ).order_by(PriceData.time).all()

        prev_day_rows = [{
            'Date': entry.time,
            'Open': entry.open,
            'High': entry.high,
            'Low': entry.low,
            'Close': entry.close,
            'Volume': entry.volume,
        } for entry in prev_day_query[self.clip_num:]]  # last rl_lookback_period rows
        self.last_ts = prev_day_rows[-1]['Date'] if prev_day_rows else None
        current_day_1st_row_query = self.db.query(PriceData).filter(
            PriceData.symbol == self.symbol,
            PriceData.time >= datetime.combine(self.current_day, time(0, 0))
        ).order_by(PriceData.time).first()
        if current_day_1st_row_query is not None:
            current_day_rows = [{
                'Date': current_day_1st_row_query.time,
                'Open': current_day_1st_row_query.open,
                'High': current_day_1st_row_query.high,
                'Low': current_day_1st_row_query.low,
                'Close': current_day_1st_row_query.close,
                'Volume': current_day_1st_row_query.volume,
            }]
            gap = current_day_rows[0]['Open'] - prev_day_rows[-1]['Close']
            self.history_buffer = pd.DataFrame(prev_day_rows)
            self.history_buffer[['Open', 'High', 'Low', 'Close']] += gap
            self.rl_data_buffer = get_bulk_prediction(
                data=self.history_buffer,
                model_high=self.xg_model_high,
                model_low=self.xg_model_low,
                training_config=self.training_config,
                scalers=self.scalers,
            )
            self.rl_data_buffer.reset_index(drop=True, inplace=True)
            self.logger.debug(f"clip_num: {self.clip_num}, history_buffer shape: {self.history_buffer.shape}, rl_data_buffer shape: {self.rl_data_buffer.shape}")

            self._add_observations()

            ### Setting the total bars for the day for progress tracking. We will update this after streaming starts as well, in case we started streaming before the market opened and there are no bars for the current day at the time of initialization, but bars start coming in later when market opens.
            current_day_rows_count = self.db.query(PriceData).filter(
                PriceData.symbol == self.symbol,
                PriceData.time >= datetime.combine(self.current_day, time(0, 0)),
                PriceData.time < datetime.combine(self.current_day + timedelta(days=1), time(0, 0))
            ).count()
            self.day_total_bars = current_day_rows_count
            self.day_current_idx = 0
            self.logger.info(f"Initial day_total_bars: {self.day_total_bars}")
            
        else:
            if self.simulation_mode:
                raise ValueError(f"No data found for symbol {self.symbol} on the current day {self.current_day}. Cannot initialize streamer. Please choose a day where data exists for the current day.")
            else:
                self.logger.warning(f"No data found for symbol {self.symbol} on the current day {self.current_day}. This might be expected if the market hasn't opened yet. Will try again after some time")

        
        
        # Prepare RL Data Buffer
        #df = df.reset_index(drop=True)

    def _add_observations(self, n=0):
        """Adds all the observations to the dataframe with predictions 
        Uses n to specify from which index to start adding observations, 
        so that we can add observations for just the new rows after streaming starts, 
        instead of recalculating for the entire buffer every time.
        """
        if n:
            indices_to_update = self.rl_data_buffer.index[-n:]
            self.rl_data_buffer.loc[indices_to_update, 'pred_high_diff'] = (
            self.rl_data_buffer.loc[indices_to_update, 'pred_high'] - self.rl_data_buffer.loc[indices_to_update, 'Close']
            )
            self.rl_data_buffer.loc[indices_to_update, 'pred_low_diff'] = (
            self.rl_data_buffer.loc[indices_to_update, 'Close'] - self.rl_data_buffer.loc[indices_to_update, 'pred_low']
            )
            start_idx = max(max(self.slope_windows)-1, len(self.rl_data_buffer) - n)  # Start from the index where we have enough data to calculate all slopes, or from n if it's larger
        else:
            self.rl_data_buffer['pred_high_diff'] = self.rl_data_buffer['pred_high'] - self.rl_data_buffer['Close']
            self.rl_data_buffer['pred_low_diff'] = self.rl_data_buffer['Close'] - self.rl_data_buffer['pred_low']
            start_idx = max(self.slope_windows)-1  # We need at least max(slope_windows) data points to calculate the slopes
     
        self.logger.debug(f" Start idx : {start_idx}")
        self.logger.debug(f"rl_data_buffer shape before adding observations: {self.rl_data_buffer.shape}")
        for idx in range(start_idx, len(self.rl_data_buffer)):
            #print(f"Processing row {idx+1} of {len(df)}")
            current_row = self.rl_data_buffer.iloc[idx]

            for window in self.slope_windows:
                col_name = f'slope_last{window}close'
                if idx - window + 1 >= 0:
                    self.logger.debug(f"{idx} - {window} + 1: {idx}")
                    close_slice = self.rl_data_buffer.loc[idx - window + 1:idx, 'Close']
                    slope = get_slope_values(close_slice)
                else:
                    slope = np.nan
                self.rl_data_buffer.at[idx, col_name] = slope
            for window in self.slope_windows:
                col_name = f'pred_high_slope_last{window}'
                if idx - window + 1 >= 0:
                    pred_high_slice = self.rl_data_buffer.loc[idx - window + 1:idx, 'pred_high']
                    slope = get_slope_values(pred_high_slice)
                else:
                    slope = np.nan
                self.rl_data_buffer.at[idx, col_name] = slope
            for window in self.slope_windows:
                col_name = f'pred_low_slope_last{window}'
                if idx - window + 1 >= 0:
                    pred_low_slice = self.rl_data_buffer.loc[idx - window + 1:idx, 'pred_low']
                    slope = get_slope_values(pred_low_slice)
                else:
                    slope = np.nan
                self.rl_data_buffer.at[idx, col_name] = slope

            n = self.inf_config['common_config']['num_bars_to_look_labels']  # You can set n to any window size you want
            if idx - n + 1 >= 0:
                highest_pred_high = self.rl_data_buffer.loc[idx - n + 1:idx, 'High'].max()
                lowest_pred_low = self.rl_data_buffer.loc[idx - n + 1:idx, 'Low'].min()
                pred_high_error = self.rl_data_buffer.at[idx, 'pred_high'] - highest_pred_high
                pred_low_error = self.rl_data_buffer.at[idx, 'pred_low'] - lowest_pred_low
                #print(f"pred_high_error: {pred_high_error}, pred_low_error: {pred_low_error} at index {idx}")
            else:
                pred_high_error = np.nan
                pred_low_error = np.nan

            self.rl_data_buffer.at[idx, 'pred_high_error'] = pred_high_error
            self.rl_data_buffer.at[idx, 'pred_low_error'] = pred_low_error

        self.rl_data_buffer = add_momentum_and_velocity_short(self.rl_data_buffer, period=14)
        # After all calculations, keep only the current day's records (exclude prev_day_rows)
        self.rl_data_buffer = self.rl_data_buffer.reset_index(drop=True)
        self.rl_data_buffer = calculate_ATR(self.rl_data_buffer, self.inf_config['indicators']['parameters'], column='Close')


    def _add_rl_observations_for_new_row(self, preds):
        """ Adds rl data and observations to the rl_data_buffer from history buffer latest row"""
        new_row = self.history_buffer.iloc[-1:].copy()

        new_row['pred_high'] = preds['buy_take']
        new_row['pred_low'] = preds['sell_take']
        self.rl_data_buffer = pd.concat([self.rl_data_buffer, new_row], ignore_index=True)
        self._add_observations(n=1)  # Only calculate observations for the new row

  
        
    def stream(self):
        """The generator that yields one row at a time."""
        # First, catch up to current time
        
        # If we started mid-day, yield the 'current' latest row immediately
        # if not self.history_buffer.empty:
        #     yield self.history_buffer.iloc[-1]
        closest_row = get_closest_trading_date(
                    db=self.db,
                    symbol=self.symbol,
                    target_date=self.current_day,
                    only_next=True 
            )
        self.current_day = closest_row.time.date() if closest_row else self.current_day
        self._prepare_day_initial_state()
        while True:
            if self.simulation_mode:

                next_ts_query = self.db.query(PriceData.time).filter(
                    PriceData.symbol == self.symbol,
                    PriceData.time > self.last_ts
                ).order_by(PriceData.time).first()
                if next_ts_query is not None:
                    next_ts = next_ts_query.time
                    #### If the next timestamp is on a different day, we need to prepare the initial state for that day before we can yield the next row
                    if next_ts.date() != self.current_day:
                        ### Check if we have reached the end of the simulation period
                        if next_ts.date() > self.end_time.date():
                            print("Reached end of simulation period. Ending stream.")
                            return
                        
                        ### Set current day to next day and prepare initial state for the new day
                        self.current_day = next_ts.date()
                        self._prepare_day_initial_state()

                        ### Updating next_ts to be the first timestamp of the new day, which we just loaded in _prepare_day_initial_state, so that we can yield the first row of the new day in the next step
                        next_ts_next_day_query = self.db.query(PriceData.time).filter(
                            PriceData.symbol == self.symbol,
                            PriceData.time > datetime.combine(self.current_day, time(0, 0))
                        ).order_by(PriceData.time).first()
                        next_ts = next_ts_next_day_query.time

                    #### Now we have same state for both cases - whether the same day or its next day


                    next_row_entry = self.db.query(PriceData).filter(
                        PriceData.symbol == self.symbol,
                        PriceData.time == next_ts
                    ).first()

                    next_row_df = pd.DataFrame([{
                        'Date': next_row_entry.time,
                        'Open': next_row_entry.open,
                        'High': next_row_entry.high,
                        'Low': next_row_entry.low,
                        'Close': next_row_entry.close,
                        'Volume': next_row_entry.volume,
                    }])
                    self.history_buffer = pd.concat([self.history_buffer, next_row_df], ignore_index=True)
                    self.history_buffer = self.history_buffer.iloc[self.clip_num:]
                    preds = get_prediction(
                        data=self.history_buffer,
                        model_high=self.xg_model_high,
                        model_low=self.xg_model_low,
                        training_config=self.training_config,
                        scalers=self.scalers,
                    )
                    self._add_rl_observations_for_new_row(preds)

                    yielded_row = self.rl_data_buffer.iloc[-1].copy()
                    self.day_current_idx += 1
                    progress = self.day_current_idx / self.day_total_bars if self.day_total_bars else 0.0
                    yielded_row['step_progress'] = progress

                    yield yielded_row

                    self.last_ts = next_ts
                else:
                    print("No more data available in simulation. Ending stream.")
                    return
