import gymnasium as gym
from gymnasium import spaces
import numpy as np
from rl_functions.utils import get_slope

class TradingEnv(gym.Env):

    def __init__(self, data, initial_balance=10000):
        super().__init__()
        # Storing the data
        self.data = data
        self.initial_balance = initial_balance
        self.reset()


    def reset(self):
        self.current_step = 0
        self.current_balance = self.initial_balance

        # Initializing the current step to 0
        self.current_step = 0
        self.max_steps = len(self.data)

        # Action and observation space
        self.action_space = spaces.Discrete(4)  # Buy Call, Buy Put, Hold, Sell
        self.observation_space = spaces.Box(low=0, high=np.inf, shape=(len(self.data.columns),), dtype=np.float32)

        
        # Day parameters
        minute_of_day = 9*60 + 30  # 9:30 AM
        self.minutes_remaining = 16 * 60 - minute_of_day

        # Trading state
        self.no_trades_completed = 0
        self.active_trade = False
        self.active_trade_direction = 0
        self.active_trade_entry_price = 0
        self.active_trade_profit = 0
        self.active_trade_take_profit_distance = 0
        self.active_trade_stop_loss_distance = 0
        self.active_trade_duration = 0

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

        return self.data.iloc[self.current_step].values

    def step(self, action):
        # Implement the logic for taking a step in the environment
        done = False
        reward = 0.0
        obs = self.data.iloc[self.current_step]

        pass