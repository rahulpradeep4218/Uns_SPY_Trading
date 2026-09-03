from torch import seed

import gymnasium as gym
from gymnasium import spaces
import numpy as np
from datetime import datetime, timedelta
from rl_functions.utils import get_data
import pandas as pd


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

    def __init__(self, db, symbol, start_date, end_date, initial_balance=10000, trade_fee=0.5, max_trade_loss_percent=2.0, obs_features=None, price_multiplier=10, evaluation=False, logger=None, total_timesteps=1000000):
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
        self.winning_trades = 0
        self.losing_trades = 0
        self.global_timestep = 0
        self.total_timesteps = total_timesteps

        # Actions
        self.action_space = spaces.Discrete(4)  # Buy Call, Buy Put, Hold, Sell

        continuous_dim = len(self.obs_features) + 4

        self.observation_space = spaces.Dict({
            "continuous": spaces.Box(
                low=-10.0, high=10.0, shape=(continuous_dim,), dtype=np.float32
            ),
            "discrete": spaces.Box(
                low=-1.0, high=1.0, shape=(2,), dtype=np.float32
            ),
        })

        if self.logger:
            self.logger.info(f"Initializing TradingEnv for symbol: {self.symbol}, start_date: {self.start_date}, end_date: {self.end_date}, evaluation: {self.evaluation}")
        
        self.reset()


    def reset(self, *, seed=None, options=None):

        super().reset(seed=seed)
        # Load data for a random trading day
        if self.start_date is None or self.end_date is None:
            self.logger.warning("Start date or end date is None in TradingEnv. Data loading may fail.")
            self.data = pd.DataFrame()  # Empty DataFrame to avoid crashes, but will lead to no trading
        else:
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
        self.winning_trades = 0
        self.losing_trades = 0

        # Observation space ( Market data + agent state)
        ### Agent state components:
        # 1 active_trade (0/1),
        # 2 trade_direction (−1, 0, +1),
        # 3 time_in_trade_norm,
        # 4 distance_to_stop_norm,
        # 5 current_step

        # Trading state
        self.no_trades_completed = 0
        self.active_trade = False
        self.active_trade_direction = 0
        self.active_trade_entry_price = 0.0
        self.active_trade_duration = 0

        # Episode related
        self.episode_length = 0

        self.pnl_list = [0.0]

        self.MIN_HOLD_STEPS = 5
        self.current_min_hold = 14  # updated each call to action_masks()

        info = {}

        return self._get_observation(), info

    def set_global_timestep(self, timestep: int):
        self.global_timestep = timestep

    # def calculate_final_reward(self, final_pnl, duration_steps):
    #     base_reward = (np.sign(final_pnl) * (final_pnl ** 2)) / 100.0

    #     day_progress = self.current_step / self.max_steps if self.max_steps > 0 else 0.0

    #     MAX_HOLD = 15.0

    #     decay_weight = 1.0 - (day_progress ** 2)
    #     # Patience multiplier
    #     time_mult = 1.0 + ( min(duration_steps, MAX_HOLD) * 0.07 * decay_weight )

    #     #Sortino penalty
    #     history = np.array(self.pnl_history)
    #     downside = history[history < 0]
    #     downside_penalty = np.mean(downside**2) if len(downside) > 0 else 0.0

    #     # Final calculation
    #     if final_pnl > 0:
    #         reward = (base_reward * time_mult) - (0.03 * downside_penalty)
    #     else:
    #         loss_penalty = 1.0 + day_progress
    #         reward = (base_reward * loss_penalty) - (0.05 * downside_penalty)

    #     return reward


    def action_masks(self) -> np.ndarray:
        """
        Returns a boolean mask of valid actions for the current state.
        MaskablePPO calls this automatically each step.

        Actions:
            0 = Hold      — always valid
            1 = Buy Call  — only valid when no active trade
            2 = Buy Put   — only valid when no active trade
            3 = Close     — only valid when there IS an active trade
        """
        progress = self.global_timestep / self.total_timesteps
        if progress < 0.10:
            min_hold = 15
        elif progress < 0.20:
            min_hold = 9
        else:
            min_hold = 5
        self.current_min_hold = min_hold  # kept so step() can align hold bonus zone
        if self.active_trade:
            # Can only hold or close
            # Lock out close action until minimum hold period is reached
            can_close = self.active_trade_duration >= min_hold
            return np.array([True, False, False, can_close], dtype=bool)
        else:
            # Can hold, buy call, or buy put — cannot close nothing
            return np.array([True, True, True, False], dtype=bool)


    def calculate_final_reward(self, trade_pnl, duration_steps):
        """
        Terminal reward designed for options trading where:
        - Steps are assumed to be 1-minute bars
        - Ideal hold duration is 10-20 steps (minutes)
        - Too short (<5 min): likely noise, small bonus reduction
        - Sweet spot (10-20 min): full reward
        - Too long (>30 min): theta decay penalty grows, capped so agent still closes
        
        Completely independent of total_intermediate_given (no debt).
        """
        if trade_pnl >= 0:
            # log1p(x) = log(1+x), so log1p(0) = 0 cleanly
            # Divide by log1p(max_episode_loss) so that pnl == max_episode_loss → 0.5
            # This anchors the scale: earning back your full risk budget = 0.5 reward
            normalised_pnl = np.log1p(trade_pnl) / (2.0 * np.log1p(self.max_episode_loss))
        else:
            normalised_pnl = max(trade_pnl / self.max_episode_loss, -1.0)


        # --- 2. Duration multiplier: bell-curve peaking at sweet spot ---
        SWEET_SPOT_MIN = 12   # steps (minutes) — start of ideal window
        SWEET_SPOT_MAX = 22   # steps (minutes) — end of ideal window
        TOO_SHORT      = 8   # below this: penalise (likely noise trade)
        TOO_LONG       = 50   # above this: hard theta decay ceiling

        if duration_steps < TOO_SHORT:
            # Ramp up from 0.5 to 1.0 between 0 and TOO_SHORT
            duration_mult = (duration_steps / TOO_SHORT) ** 2

        elif duration_steps <= SWEET_SPOT_MIN:
            # Ramp from 1.0 to 1.3 between TOO_SHORT and SWEET_SPOT_MIN
            ramp = (duration_steps - TOO_SHORT) / (SWEET_SPOT_MIN - TOO_SHORT)
            duration_mult = 1.0 + 0.3 * ramp

        elif duration_steps <= SWEET_SPOT_MAX:
            # Flat peak in the ideal window
            duration_mult = 1.3

        elif duration_steps <= TOO_LONG:
            # Decay from 1.3 back to 1.0 between SWEET_SPOT_MAX and TOO_LONG
            decay = (duration_steps - SWEET_SPOT_MAX) / (TOO_LONG - SWEET_SPOT_MAX)
            duration_mult = 1.3 - 0.3 * decay

        else:
            # Beyond TOO_LONG: theta decay penalty, floor at 0.5 so agent still closes
            # rather than holding forever hoping for a miracle
            overhang = duration_steps - TOO_LONG
            duration_mult = max(0.5, 1.0 - 0.01 * overhang)

        # --- 3. Day-progress urgency: force close near end of session ---
        day_progress = self.current_step / self.max_steps if self.max_steps > 0 else 0.0
        # Linearly ramps from 1.0 at open to 1.5 at close
        # Encourages agent to close open positions as session end approaches
        eod_urgency = 1.0 + 0.5 * (day_progress ** 2)

        # --- 4. Combine ---
        if trade_pnl > 0:
            # Winning trade: full duration bonus applies
            reward = normalised_pnl * duration_mult

        else:
            # Losing trade: duration_mult still applies so agent learns
            # that a quick small loss is better than a long large loss.
            # Cap at -1.0 so it never feels catastrophic.
            reward = max(normalised_pnl * duration_mult * eod_urgency, -1.0)

        return float(reward)


    def _get_observation(self):
        # safe_step = min(self.current_step, len(self.data) - 1)
        # if safe_step < 0:
        #     market_obs = np.zeros(len(self.obs_features), dtype=np.float32)
        # else:
        market_obs = np.array(
            [self.data.iloc[self.current_step][f] for f in self.obs_features],
            dtype=np.float32,
        )

        # Continuous agent state
        total_pnl = self.pnl + self.active_pnl
        
        if total_pnl >= 0:
            loss_ratio = np.log1p(total_pnl) / (2.0 * np.log1p(self.max_episode_loss))
        else:
            loss_ratio = float(np.clip(total_pnl / self.max_episode_loss, -1.0, 0.0))

        progress = (self.current_step + 1) / self.max_steps if self.max_steps > 0 else 0.0
        
        # Normalize active trade duration to [0, 1] over a 60-minute window
        duration_norm = float(np.clip(self.active_trade_duration / 60.0, 0.0, 1.0))

        # Explicit unrealized PnL signal, separate from loss_ratio which mixes realized+unrealized
        unrealized_pnl_norm = float(np.clip(self.active_pnl / self.max_episode_loss, -1.0, 1.0)) if self.max_episode_loss > 0 else 0.0

        # Continuous part — will be normalized by VecNormalize
        continuous_obs = np.concatenate([
            market_obs,
            np.array([progress, loss_ratio, duration_norm, unrealized_pnl_norm], dtype=np.float32)
        ])

        # Discrete part — bypasses VecNormalize normalization
        # active_trade: exactly 0.0 or 1.0 every step, never drifts
        # active_trade_direction: exactly -1.0, 0.0, or 1.0
        discrete_obs = np.array([
            float(self.active_trade),
            float(self.active_trade_direction),
        ], dtype=np.float32)

        obs = {"continuous": continuous_obs, "discrete": discrete_obs}
        
        if np.isnan(continuous_obs).any() and self.logger:
            self.logger.warning(
                f"NaN values in observation at step: {self.current_step}, "
                f"evaluation: {self.evaluation}"
            )

        return obs
                              

    def step(self, action):
        # Implement the logic for taking a step in the environment
        self.global_timestep += 1
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

        # --- 0. Detect and penalise invalid actions ---
        invalid_action = (
            (action in (1, 2) and self.active_trade) or   # tried to open while in trade
            (action == 3 and not self.active_trade)         # tried to close with no trade
        )

        if invalid_action:
            step_reward = -0.01  # Small penalty for invalid actions to guide learning

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
            
            trade_profit = (
                (price - self.active_trade_entry_price) 
                * self.active_trade_direction 
                * self.price_multiplier
            )
            trade_profit -= self.trade_fee # Apply fee on exit as well

            self.pnl += trade_profit
            self.avg_trade_duration = (
                (self.avg_trade_duration * (self.no_trades_completed - 1)) 
                + self.active_trade_duration
            ) / self.no_trades_completed

            if trade_profit > 0:
                self.winning_trades += 1
            else:
                self.losing_trades += 1

            step_reward = self.calculate_final_reward(trade_profit, self.active_trade_duration)

            self.active_pnl = 0.0
            self.active_trade = False
            self.active_trade_direction = 0
            self.active_trade_entry_price = 0.0
            self.active_trade_duration = 0
            
        ### Unrealized PnL calculation
        if self.active_trade:
            self.active_pnl = (
                (price - self.active_trade_entry_price) 
                * self.active_trade_direction 
                * self.price_multiplier
            )
            self.active_trade_duration += 1

            delta_pnl = self.active_pnl - self.prev_active_pnl
            self.prev_active_pnl = self.active_pnl
            self.pnl_history.append(self.active_pnl)

            # Theta-aware time decay: penalty grows the longer the trade is open,
            # mimicking real options theta decay (starts ~0.0005, grows to ~0.002+)
            theta_penalty = 0.0005 * (1.0 + self.active_trade_duration / 30.0)

            # Hold bonus zone is anchored to current_min_hold so it stays coherent
            # with the action-masking curriculum (min_hold decays 14→9→5 over training).
            # Ramp starts at min_hold, peaks at min_hold+8, decays to 0 at min_hold+38.
            lockout = self.current_min_hold
            ramp_end = lockout + 8
            peak_end = lockout + 18
            decay_end = lockout + 38

            if self.active_trade_duration < lockout:
                holding_bonus = 0.0   # can't close yet anyway

            elif self.active_trade_duration <= ramp_end:
                holding_bonus = 0.003 * ((self.active_trade_duration - lockout) / 8.0)

            elif self.active_trade_duration <= peak_end:
                holding_bonus = 0.003   # flat peak

            elif self.active_trade_duration <= decay_end:
                decay = (self.active_trade_duration - peak_end) / 20.0
                holding_bonus = 0.003 * (1.0 - decay)

            else:
                holding_bonus = 0.0

            step_reward = (delta_pnl * 0.01) - theta_penalty + holding_bonus
            # FIX #3: do NOT accumulate into total_intermediate_given —
            # terminal reward at close is fully independent of shaping history

        elif action == 0:
            # Small penalty for passive holding
            step_reward -= 0.0002
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

        # In eval mode: don't stop on stop-loss — advance to the next test day instead
        # so PnL doesn't bleed further on the same day's remaining bars.
        eval_stop_loss_hit = terminated and self.evaluation
        if eval_stop_loss_hit:
            terminated = False

        # Survival Bonus — kept small so it doesn't dominate VecNormalize reward variance
        if truncated:
            if total_pnl > 0:
                step_reward += 0.1
            elif total_pnl > (-self.max_episode_loss * 0.5):
                step_reward += 0.02

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

        if (terminated or truncated) and not self.evaluation:
            print("Episode details for episode id : ", self.episode_id)
            print(info)
            self.episode_id += 1

        #### Logic for checking if evaluation and updating data if end of current day reached
        # Triggers on natural end-of-day OR when stop-loss is hit during eval

        if self.evaluation and (self.current_step >= (self.max_steps-1) or eval_stop_loss_hit):
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



class LiveTradingEnv(TradingEnv):
    """
    Live/Streamed Trading Environment.
    Instead of loading a full day of data, this environment updates its state
    one row at a time from the RL_Stream_Data generator.
    """
    def __init__(self, db, symbol, obs_features, streamer, **kwargs):

        self.stream_gen = None
        self.current_row = None
        self.last_timestamp = None
        self.streamer = streamer
        self.obs_features = obs_features
        self.progress = 0.0
        # We pass dummy dates because the streamer controls the timeline
        super().__init__(
            db=db, 
            symbol=symbol, 
            start_date=None, 
            end_date=None, 
            obs_features=obs_features, 
            evaluation=True, 
            **kwargs
        )
             
        if self.logger:
            self.logger.info("LiveTradingEnv initialized and ready for streaming.")

    def reset(self, *, seed=None, options=None):
        """
        Resets the environment state and restarts the data stream.
        """

        # Initialize the Gymnasium seed logic without triggering the parent's data loading
        gym.Env.reset(self, seed=seed)
        
        self.stream_gen = self.streamer.stream()
        self.logger.info("LiveTradingEnv reset: Stream generator initialized.")

        # Pull the first row to initialize the observation space
        try:
            self.current_row = next(self.stream_gen)
            #self.progress = self.current_row['step_progress'] if 'step_progress' in self.current_row else 0.0
            self.progress = 0.0
            self.logger.info(f"LiveTradingEnv reset, progress : {self.progress:.4f}")
            self.logger.info(f"First streamed row received with row: {self.current_row}")
            self.logger.info(f"Columns in streamed row: {self.current_row.index.tolist()}")
            self.last_timestamp = self.current_row['Date']
        except StopIteration:
            raise RuntimeError("Streamer yielded no data during reset.")
        
        # Reset internal trading metrics
        self.pnl = 0.0
        self.active_pnl = 0.0
        self.prev_active_pnl = 0.0
        self.balance = self.initial_balance
        self.peak_balance = self.initial_balance
        self.max_drawdown = 0.0
        self.max_episode_loss = self.balance * self.max_trade_loss_percent / 100
        
        self.current_step = 0
        self.no_trades_completed = 0
        self.active_trade = False
        self.active_trade_direction = 0 # 1 for Call, -1 for Put
        self.active_trade_entry_price = 0.0
        self.active_trade_duration = 0
        self.total_intermediate_given = 0.0
        self.winning_trades = 0
        self.losing_trades = 0
        self.pnl_history = []     
        self.pnl_list = [0.0]
        self.xg_high = 0.0
        self.xg_low = 0.0
        self.max_steps = 390

        # # Call Gymnasium's base reset for seeding
        # obs, info = super().reset(seed=seed, options=options)

        # Initialize the Streamer Generator

        obs = self._get_observation()

        info = {"timestamp": self.last_timestamp}
        
        return obs, info

    def _get_observation(self):
        """
        Constructs the observation vector using the current row from the streamer
        and the real-time agent state.
        """
        # 1. Extract Market Features from the streamed row
        #self.logger.info(f"Building observation from streamed row : {self.current_row}")
        market_obs = np.array(
            [self.current_row[f] for f in self.obs_features], 
            dtype=np.float32
        )

        # 2. Calculate Agent State
        total_pnl = self.pnl + self.active_pnl
        
        # Normalize the loss ratio relative to the stop-out limit
        loss_ratio = total_pnl / self.max_episode_loss if self.max_episode_loss != 0 else 0.0
        loss_ratio = np.clip(loss_ratio, -1.0, 1.0)
        loss_ratio = float(loss_ratio)
        agent_obs = [
            self.active_trade,
            self.active_trade_direction,
            self.progress,
            loss_ratio
        ]
        self.logger.info(f"Market obs shape: {market_obs.shape}")
        market_str = np.array2string(market_obs, precision=4, separator=',')
        self.logger.info(f"Complete market obs: {market_str}")
        self.logger.info(f"Market Obs: {market_obs}, Agent Obs: {agent_obs}")

        # 3. Concatenate
        obs = np.concatenate([market_obs, np.array(agent_obs, dtype=np.float32)])
        
        # Sanity Check
        if np.isnan(obs).any() and self.logger:
            self.logger.warning(f"NaN in Live Observation at {self.last_timestamp}")
            
        return obs

    def calculate_final_reward(self, final_pnl, duration_steps):
        base_reward = (np.sign(final_pnl) * (final_pnl ** 2)) / 100.0

        day_progress = self.progress

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


    def step(self, action):
        """
        Executes one action based on the current streamed row, 
        then pulls the NEXT row from the stream.
        """
        truncated = False
        step_reward = 0.0
        
        # Current price from the row we are CURRENTLY on
        price = self.current_row['Close']
        self.last_timestamp = self.current_row['Date']

        # --- 1. Execute Actions ---
        if action == 1 and not self.active_trade:  # Buy Call
            self.active_trade = True
            self.active_trade_direction = 1
            self.active_trade_entry_price = price
            self.active_trade_duration = 0
            self.pnl -= self.trade_fee
            self.pnl_history = [0.0]
            self.prev_active_pnl = 0.0
        
        elif action == 2 and not self.active_trade:  # Buy Put
            self.active_trade = True
            self.active_trade_direction = -1
            self.active_trade_entry_price = price
            self.active_trade_duration = 0
            self.pnl -= self.trade_fee
            self.pnl_history = [0.0]
            self.prev_active_pnl = 0.0

        elif action == 3 and self.active_trade:  # Close Position
            self.no_trades_completed += 1
            trade_profit = (price - self.active_trade_entry_price) * self.active_trade_direction * self.price_multiplier
            trade_profit -= self.trade_fee # Apply fee on exit as well
            
            self.pnl += trade_profit
            self.logger.info(f"Trade closed at {self.last_timestamp} with profit: {trade_profit:.2f}, total pnl: {self.pnl:.2f}")
            
            # Statistics
            if trade_profit > 0: self.winning_trades += 1
            else: self.losing_trades += 1
            
            # Reward Calculation
            final_reward = self.calculate_final_reward(trade_profit, self.active_trade_duration)
            step_reward = final_reward - self.total_intermediate_given
            
            # Reset Trade State
            self.total_intermediate_given = 0.0
            self.active_pnl = 0.0
            self.active_trade = False
            self.active_trade_direction = 0
            self.active_trade_entry_price = 0.0
            self.active_trade_duration = 0

        # --- 2. Update Unrealized PnL (If holding) ---
        if self.active_trade:
            self.active_pnl = (price - self.active_trade_entry_price) * self.active_trade_direction * self.price_multiplier
            self.active_trade_duration += 1
            
            # Shaping reward: change in unrealized PnL
            delta_pnl = self.active_pnl - self.prev_active_pnl
            self.prev_active_pnl = self.active_pnl
            self.pnl_history.append(self.active_pnl)
            
            step_reward = (delta_pnl * 0.01) - 0.001 # 0.001 is the time decay penalty
            self.total_intermediate_given += step_reward

        # --- 3. Update Global Metrics ---
        total_pnl = self.pnl + self.active_pnl
        current_balance = self.initial_balance + total_pnl
        
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
        
        drawdown = (self.peak_balance - current_balance) / self.peak_balance if self.peak_balance > 0 else 0.0
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown

        # --- 4. Get Next Row from Streamer ---
        try:
            self.current_row = next(self.stream_gen)
            self.progress = self.current_row['step_progress'] if 'step_progress' in self.current_row else self.progress
            self.pred_high = self.current_row['pred_high']
            self.pred_low = self.current_row['pred_low']
            self.current_step += 1
        except StopIteration:
            # Stream ended (end of simulation or market close)
            truncated = True
        
        if not truncated:
            current_ts = self.current_row['Date']
            if current_ts.date() != self.last_timestamp.date():
                self.logger.info("Next day loaded in LiveTradingEnv with timestamp : {}".format(current_ts))
                self.current_step = 0
                self.max_steps = 390
                if self.active_trade:
                    self.no_trades_completed += 1
                    trade_profit = (price - self.active_trade_entry_price) * self.active_trade_direction * self.price_multiplier
                    self.pnl = 0.0
                    self.peak_balance = 0.0
                    self.active_pnl = 0.0
                    self.active_trade = False
                    self.active_trade_direction = 0
                    self.active_trade_entry_price = 0.0
                    self.active_trade_duration = 0

        info = {
            "total_pnl": total_pnl,
            "realized_pnl": self.pnl,
            "active_trade": self.active_trade,
            "balance": current_balance,
            "max_drawdown_pct": self.max_drawdown * 100,
            "timestamp": self.last_timestamp,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades
        }

        return self._get_observation(), step_reward, False, truncated, info