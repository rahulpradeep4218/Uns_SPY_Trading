import gymnasium as gym
from gymnasium import spaces
import numpy as np
from rl_functions.utils import get_slope, get_data

class TradingEnv(gym.Env):

    """
    Episode : One trading day from 9:30 AM to 4:00 PM (390 minutes)
    Action Space : 4 discrete actions
        0 : Hold
        1 : Buy Call
        2 : Buy Put
        3 : Sell (Close position)
    Observation Space : Continuous values representing market data and trading state
    For reset, one random day is selected and data for that day is loaded

    """

    def __init__(self, data, initial_balance=10000, daily_trades_limit=20):
        super().__init__()
        # Storing the data
        self.initial_balance = initial_balance
        self.total_balance = initial_balance
        self.daily_trades_limit = daily_trades_limit

        self.reset()


    def reset(self):
        self.current_balance = self.initial_balance

        # Initializing the current step to 0
        self.current_step = 0
        self.max_steps = len(self.data)

        # Action and observation space
        self.action_space = spaces.Discrete(4)  # Buy Call, Buy Put, Hold, Sell
        self.observation_space = spaces.Box(low=0, high=np.inf, shape=(len(self.data.columns),), dtype=np.float32)

        
        # Day parameters
        self.minute_of_day = 9*60 + 30  # 9:30 AM
        self.minutes_remaining = 16 * 60 - self.minute_of_day

        # Trading state
        self.no_trades_completed = 0
        self.active_trade = False
        self.active_trade_direction = 0
        self.active_trade_entry_price = 0
        #self.active_trade_profit = 0
        #self.active_trade_take_profit_distance = 0
        self.active_trade_stop_loss= 0
        self.active_trade_stop_loss_distance = 0
        self.active_trade_duration = 0

        """
        These attributes will be obtained from data

        #Trade Curve parameters
        self.curve_slope_2 = 0
        self.curve_slope_5 = 0
        self.curve_slope_10 = 0
        self.curve_slope_20 = 0
        self.atr = 0

        #Prediction parameters value
        self.pred_high_distance = 0
        self.pred_low_distance = 0
        self.pred_high_error = 0
        self.pred_low_error = 0

        #prediction curve slopes
        self.pred_high_slope_2 = 0
        self.pred_high_slope_5 = 0
        self.pred_high_slope_10 = 0
        self.pred_high_slope_20 = 0
        self.pred_low_slope_2 = 0
        self.pred_low_slope_5 = 0
        self.pred_low_slope_10 = 0
        self.pred_low_slope_20 = 0
        """

        return self.data.iloc[self.current_step].values
    

    def get_observation(self):
        data_row = self.data.iloc[self.current_step]
        obs = np.array(data_row, dtype=np.float32)

    def step(self, action):
        # Implement the logic for taking a step in the environment
        done = False
        reward = 0.0
        obs = self.data.iloc[self.current_step]

        pass