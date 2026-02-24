import gymnasium as gym
from gymnasium import spaces
import numpy as np
from datetime import datetime, timedelta
from rl_functions.utils import get_data


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

    def __init__(self, db, symbol, start_date, end_date, initial_balance=10000, trade_fee=0.5, max_trade_loss_percent=2.0, obs_features=None, price_multiplier=10, evaluation=False, logger=None):
        super().__init__()
        # Storing the data
        self.obs_features = obs_features
        self.initial_balance = initial_balance    # Balance
        self.max_trade_loss_percent = max_trade_loss_percent
        self.max_drawdown = 0.0
        self.peak_balance = initial_balance  # Track the highest balance reached
        self.max_episode_loss = self.initial_balance * self.max_trade_loss_percent / 100
        self.trade_fee = trade_fee
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.db = db 
        self.episode_id = 1
        self.price_multiplier = price_multiplier    
        self.evaluation = evaluation
        self.logger = logger
        self.pnl_history = []
        self.prev_active_pnl = 0.0
        self.total_intermediate_given = 0.0
        self.winning_trades = 0
        self.losing_trades = 0

        # Actions
        self.action_space = spaces.Discrete(4)  # Buy Call, Buy Put, Hold, Sell

        # Placeholder for observation space, will be defined in reset
        self.observation_space = None
        if self.logger:
            self.logger.info(f"Initializing TradingEnv for symbol: {self.symbol}, start_date: {self.start_date}, end_date: {self.end_date}, evaluation: {self.evaluation}")
        
        self.reset()


    def reset(self, *, seed=None, options=None):

        super().reset(seed=seed)
        # Load data for a random trading day
        self.data, status = get_data( symbol=self.symbol, 
                             start_date=self.start_date, 
                             end_date=self.end_date, 
                             db=self.db, 
                             evaluation=self.evaluation)
        
        self.data.reset_index(drop=True, inplace=True)
        self.logger.info(f"Data shape : {self.data.shape}")
        if len(self.data) > 0:
            self.logger.info(f"Data time range : {self.data['Date'].iloc[0]} to {self.data['Date'].iloc[-1]}")
        self.pnl = 0.0
        self.active_pnl = 0.0
        self.prev_active_pnl = 0.0
        self.balance = self.initial_balance
        self.peak_balance = self.initial_balance
        self.max_drawdown = 0.0
        self.max_episode_loss = self.balance * self.max_trade_loss_percent / 100
        # Initializing the current step to 0
        self.current_step = 0
        self.max_steps = len(self.data)
        self.avg_trade_duration = 0.0

        self.pnl_history = []

        self.total_intermediate_given = 0.0
        self.winning_trades = 0
        self.losing_trades = 0

        # Observation space ( Market data + agent state)
        ### Agent state components:
        # 1 active_trade (0/1),
        # 2 trade_direction (−1, 0, +1),
        # 3 time_in_trade_norm,
        # 4 distance_to_stop_norm,
        # 5 current_step
        agent_state_dim = 4
        obs_dim = len(self.obs_features) + agent_state_dim
        self.observation_space = spaces.Box(
            low=-10.0, 
            high=10.0, 
            shape=(obs_dim,), 
            dtype=np.float32
        )
        

        # Trading state
        self.no_trades_completed = 0
        self.active_trade = False
        self.active_trade_direction = 0
        self.active_trade_entry_price = 0.0
        self.active_trade_duration = 0

        # Episode related
        self.episode_length = 0

        self.pnl_list = [0.0]


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

        info = {}

        return self._get_observation(), info
    
    def build_observation_row(self, row):
        return np.array(
            [row[f] for f in self.obs_features],
            dtype=np.float32
        )

    def calculate_final_reward(self, final_pnl, duration_steps):
        base_reward = (np.sign(final_pnl) * (final_pnl ** 2)) / 100.0

        day_progress = self.current_step / self.max_steps if self.max_steps > 0 else 0.0

        MAX_HOLD = 15.0

        decay_weight = 1.0 - (day_progress ** 2)
        # Patience multiplier
        time_mult = 1.0 + ( min(duration_steps, MAX_HOLD) * 0.07 * decay_weight )

        #Sortino penalty
        history = np.array(self.pnl_history)
        downside = history[history < 0]
        downside_penalty = np.mean(downside**2) if len(downside) > 0 else 0.0

        # Final calculation
        if final_pnl > 0:
            reward = (base_reward * time_mult) - (0.03 * downside_penalty)
        else:
            loss_penalty = 1.0 + day_progress
            reward = (base_reward * loss_penalty) - (0.05 * downside_penalty)

        return reward


    def _get_observation(self):
        # safe_step = min(self.current_step, len(self.data) - 1)
        # if safe_step < 0:
        #     market_obs = np.zeros(len(self.obs_features), dtype=np.float32)
        # else:
        market_obs = self.build_observation_row(self.data.iloc[self.current_step])

        total_pnl = self.pnl + self.active_pnl

        loss_ratio = total_pnl / self.max_episode_loss if self.max_episode_loss != 0 else 0.0
        loss_ratio = np.clip(loss_ratio, -1.0, 1.0)
        progress = self.current_step / self.max_steps if self.max_steps > 0 else 0.0
        agent_obs = [
            self.active_trade,
            self.active_trade_direction,
            progress,
            loss_ratio
        ]

        obs =  np.concatenate(
            [market_obs, np.array(agent_obs, dtype=np.float32)]
        )
        
        if np.isnan(obs).any() and self.logger:
            self.logger.warning(f"NaN values in observation at step : {self.current_step} , evaluation : {self.evaluation}")
        return obs
                              

    def step(self, action):
        # Implement the logic for taking a step in the environment
        terminated = False
        truncated = False
        reward = 0.0
        self.episode_length += 1
        if len(self.data) > 0:
            obs = self.data.iloc[self.current_step]
            price = obs['Close']
        else:
            price = 0.0

        # --- Advance time
        self.current_step += 1
        step_reward = 0.0
        if action == 1 and not self.active_trade:  # Buy Call
            self.active_trade = True
            self.active_trade_direction = 1
            self.active_trade_entry_price = price
            self.active_trade_duration = 0
            self.pnl -= self.trade_fee
            self.pnl_history = [0.0]  # Start new trade PnL history
            self.prev_active_pnl = 0.0
        
        elif action == 2 and not self.active_trade:  # Buy Put
            self.active_trade = True
            self.active_trade_direction = -1
            self.active_trade_entry_price = price
            self.active_trade_duration = 0
            self.pnl -= self.trade_fee
            self.pnl_history = [0.0]  # Start new trade PnL history
            self.prev_active_pnl = 0.0

        elif action == 3 and self.active_trade:  # Sell (Close position)
            self.no_trades_completed += 1
            trade_profit = (price - self.active_trade_entry_price - self.trade_fee) * self.active_trade_direction * self.price_multiplier
            self.pnl += trade_profit
            self.avg_trade_duration = ((self.avg_trade_duration * (self.no_trades_completed - 1)) + self.active_trade_duration) / self.no_trades_completed
            if trade_profit > 0:
                self.winning_trades += 1
            else:
                self.losing_trades += 1
            final_reward = self.calculate_final_reward(trade_profit, self.active_trade_duration)
            step_reward = final_reward - self.total_intermediate_given
            self.total_intermediate_given = 0.0
            self.active_pnl = 0.0
            self.active_trade = False
            self.active_trade_direction = 0
            self.active_trade_entry_price = 0.0
            self.active_trade_duration = 0
            

        ### Unrealized PnL calculation
        if self.active_trade:
            self.active_pnl = (price - self.active_trade_entry_price) * self.active_trade_direction * self.price_multiplier
            self.active_trade_duration += 1
            delta_pnl = self.active_pnl - self.prev_active_pnl
            self.prev_active_pnl = self.active_pnl
            self.pnl_history.append(self.active_pnl)
            step_reward = delta_pnl * 0.01

            #Tiny time decay penalty
            step_reward -= 0.001
            self.total_intermediate_given += step_reward

        else:
            self.active_pnl = 0.0

        # ---- Reward Calculation ----
        total_pnl = self.pnl + self.active_pnl

        # self.prev_total_pnl = current_reward

        # Update balance and calculate drawdown
        current_balance = self.balance + total_pnl
        
        # Update peak if current balance is higher
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
        
        # Calculate current drawdown from peak
        current_drawdown = (self.peak_balance - current_balance) / self.peak_balance if self.peak_balance > 0 else 0.0
        
        # Update max drawdown if current is worse
        if current_drawdown > self.max_drawdown:
            self.max_drawdown = current_drawdown

        self.pnl_list.append(total_pnl)
        

        # -- Episode Termination Conditions

        if self.current_step >= (self.max_steps-1) and not self.evaluation:
            truncated = True

        if total_pnl <= -self.max_episode_loss:
            terminated = True


        info = {
            "total_pnl": total_pnl,
            "realized_pnl": self.pnl,
            "unrealized_pnl": self.active_pnl,
            "active_trade": self.active_trade,
            "no_trades_completed": self.no_trades_completed,
            "avg_trade_duration": self.avg_trade_duration,
            "Balance": current_balance,
            "episode_length": self.episode_length,
            "max_drawdown_percent": self.max_drawdown * 100,
            "peak_balance": self.peak_balance,
            "current_drawdown_percent": current_drawdown * 100,
            "episode_id": self.episode_id,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades
        }

        if terminated or truncated and not self.evaluation:
            print("Episode details for episode id : ", self.episode_id)
            print(info)
            self.episode_id += 1

        if terminated and self.evaluation:
            terminated = False

        #### Logic for checking if evaluation and updating data if end of current day reached

        if self.evaluation and self.current_step >= (self.max_steps-1):
            # Load next day data
            next_date = self.data['Date'].iloc[0].date() + timedelta(days=1)
            new_data, status = get_data(symbol=self.symbol,
                                 start_date=next_date,
                                    end_date=self.end_date,
                                    db=self.db,
                                    evaluation=self.evaluation)
            
            if len(new_data) > 0:
                self.logger.info(f"Evaluation day Data time range : {new_data['Date'].iloc[0]} to {new_data['Date'].iloc[-1]}")

            if status == "END_DATE_REACHED" or new_data is None or len(new_data) == 0:
                truncated = True
            else:
                self.data = new_data
                self.data.reset_index(drop=True, inplace=True)
                self.current_step = 0
                self.max_steps = len(self.data)
                if self.active_trade:
                    self.no_trades_completed += 1
                    trade_profit = (price - self.active_trade_entry_price) * self.active_trade_direction * self.price_multiplier
                    self.pnl += trade_profit - self.trade_fee
                    self.avg_trade_duration = ((self.avg_trade_duration * (self.no_trades_completed - 1)) + self.active_trade_duration) / self.no_trades_completed
                    self.peak_balance = 0.0
                    self.active_pnl = 0.0
                    self.active_trade = False
                    self.active_trade_direction = 0
                    self.active_trade_entry_price = 0.0
                    self.active_trade_duration = 0

        obs = self._get_observation()

        return obs, step_reward, terminated, truncated, info