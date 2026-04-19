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
    Observation Space : Dict with two keys:
        "continuous" : market features + progress + loss_ratio  (VecNormalize will normalize this)
        "discrete"   : active_trade flag + trade_direction       (bypasses VecNormalize)
    For reset, one random day is selected and data for that day is loaded
    """

    def __init__(
        self,
        db,
        symbol,
        start_date,
        end_date,
        initial_balance=10000,
        trade_fee=0.5,
        max_trade_loss_percent=2.0,
        obs_features=None,
        price_multiplier=10,
        evaluation=False,
        logger=None,
    ):
        super().__init__()

        self.obs_features = obs_features
        self.initial_balance = initial_balance
        self.max_trade_loss_percent = max_trade_loss_percent
        self.max_drawdown = 0.0
        self.peak_balance = initial_balance
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
        # total_intermediate_given removed — no longer used in reward calculation
        self.winning_trades = 0
        self.losing_trades = 0

        # Actions
        self.action_space = spaces.Discrete(4)  # Hold, Buy Call, Buy Put, Sell

        # --- FIX #1: Split observation space so VecNormalize only touches continuous part ---
        # continuous: all market features + progress + loss_ratio
        # discrete:   active_trade (0/1) + active_trade_direction (-1/0/1)
        #             these are raw booleans/ints and must NOT be normalized
        continuous_dim = len(self.obs_features) + 2
        self.observation_space = spaces.Dict({
            "continuous": spaces.Box(
                low=-10.0, high=10.0, shape=(continuous_dim,), dtype=np.float32
            ),
            "discrete": spaces.Box(
                low=-1.0, high=1.0, shape=(2,), dtype=np.float32
            ),
        })
        # When constructing VecNormalize in utils.py, pass:
        #   norm_obs_keys=["continuous"]
        # so that only the continuous part gets running-mean normalized.

        if self.logger:
            self.logger.info(
                f"Initializing TradingEnv for symbol: {self.symbol}, "
                f"start_date: {self.start_date}, end_date: {self.end_date}, "
                f"evaluation: {self.evaluation}"
            )

        self.reset()

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)

        if self.start_date is None or self.end_date is None:
            self.logger.warning(
                "Start date or end date is None in TradingEnv. Data loading may fail."
            )
            self.data = pd.DataFrame()
        else:
            self.data, status = get_data(
                symbol=self.symbol,
                start_date=self.start_date,
                end_date=self.end_date,
                db=self.db,
                evaluation=self.evaluation,
            )

        self.data.reset_index(drop=True, inplace=True)
        self.logger.info(f"Data shape : {self.data.shape}")
        if len(self.data) > 0:
            self.logger.info(
                f"Data time range : {self.data['Date'].iloc[0]} to {self.data['Date'].iloc[-1]}"
            )

        self.pnl = 0.0
        self.active_pnl = 0.0
        self.prev_active_pnl = 0.0
        self.balance = self.initial_balance
        self.peak_balance = self.initial_balance
        self.max_drawdown = 0.0
        self.max_episode_loss = self.balance * self.max_trade_loss_percent / 100

        self.current_step = 0
        self.max_steps = len(self.data)
        self.avg_trade_duration = 0.0

        self.pnl_history = []
        self.winning_trades = 0
        self.losing_trades = 0

        # Trading state
        self.no_trades_completed = 0
        self.active_trade = False
        self.active_trade_direction = 0
        self.active_trade_entry_price = 0.0
        self.active_trade_duration = 0

        # Episode related
        self.episode_length = 0
        self.pnl_list = [0.0]

        info = {}
        return self._get_observation(), info

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def build_observation_row(self, row):
        return np.array([row[f] for f in self.obs_features], dtype=np.float32)

    # ------------------------------------------------------------------
    # FIX #2 + #3: Redesigned terminal reward for options trading
    # ------------------------------------------------------------------

    def calculate_final_reward(self, trade_pnl, duration_steps):
        """
        Terminal reward optimised for options trading (1-minute bars).

        Design goals:
        - Sweet spot hold duration: 10-20 steps (minutes)
        - Too short  (<5  min): partial bonus — likely a noise trade
        - Ramp-up    (5-10 min): reward grows toward peak
        - Peak       (10-20 min): maximum duration multiplier (1.3x)
        - Decay      (20-45 min): theta decay erodes bonus back to 1.0x
        - Too long   (>45 min): multiplier continues falling, floor 0.5x
          so the agent *always* prefers closing over infinite holding

        Reward is normalised by max_episode_loss so magnitude is
        consistent regardless of price_multiplier / account size.

        Completely independent of total_intermediate_given — no debt.
        """

        # --- 1. Normalise PnL to [-1, +1] scale ---
        normalised_pnl = np.clip(
            trade_pnl / self.max_episode_loss, -1.0, 1.0
        )

        # --- 2. Duration multiplier — bell curve with flat peak ---
        TOO_SHORT      = 5
        SWEET_SPOT_MIN = 10
        SWEET_SPOT_MAX = 20
        TOO_LONG       = 45

        if duration_steps < TOO_SHORT:
            # Ramp from 0.5 → 1.0 as steps go 0 → TOO_SHORT
            duration_mult = 0.5 + 0.5 * (duration_steps / TOO_SHORT)

        elif duration_steps <= SWEET_SPOT_MIN:
            # Ramp from 1.0 → 1.3 between TOO_SHORT and SWEET_SPOT_MIN
            ramp = (duration_steps - TOO_SHORT) / (SWEET_SPOT_MIN - TOO_SHORT)
            duration_mult = 1.0 + 0.3 * ramp

        elif duration_steps <= SWEET_SPOT_MAX:
            # Flat peak — agent has full flexibility within the ideal window
            duration_mult = 1.3

        elif duration_steps <= TOO_LONG:
            # Decay from 1.3 → 1.0 between SWEET_SPOT_MAX and TOO_LONG
            decay = (duration_steps - SWEET_SPOT_MAX) / (TOO_LONG - SWEET_SPOT_MAX)
            duration_mult = 1.3 - 0.3 * decay

        else:
            # Beyond TOO_LONG: continuing decay, floor at 0.5
            # Agent must always prefer closing over holding forever
            overhang = duration_steps - TOO_LONG
            duration_mult = max(0.5, 1.0 - 0.01 * overhang)

        # --- 3. End-of-day urgency multiplier (only penalises losses) ---
        day_progress = self.current_step / self.max_steps if self.max_steps > 0 else 0.0
        # Ramps from 1.0 at open → 1.5 at close: accelerates loss penalty near EOD
        eod_urgency = 1.0 + 0.5 * (day_progress ** 2)

        # --- 4. Combine ---
        if trade_pnl > 0:
            # Winning trade: patience bonus applies, no EOD penalty
            reward = normalised_pnl * duration_mult
        else:
            # Losing trade: duration_mult still applies so that a short small
            # loss scores better than a long large loss (teaches cutting losers).
            # EOD urgency adds extra pressure near close.
            # Hard floor at -1.0 so agent never sees a catastrophic penalty
            # that makes closing feel worse than infinite holding.
            reward = max(normalised_pnl * duration_mult * eod_urgency, -1.0)

        return float(reward)

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def _get_observation(self):
        market_obs = self.build_observation_row(self.data.iloc[self.current_step])

        total_pnl = self.pnl + self.active_pnl
        loss_ratio = np.clip(
            total_pnl / self.max_episode_loss if self.max_episode_loss != 0 else 0.0,
            -1.0, 1.0
        )
        progress = self.current_step / self.max_steps if self.max_steps > 0 else 0.0

        # Continuous part — will be normalized by VecNormalize
        continuous_obs = np.concatenate([
            market_obs,
            np.array([progress, float(loss_ratio)], dtype=np.float32),
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

    # ------------------------------------------------------------------
    # Step
    # ------------------------------------------------------------------

    def step(self, action):
        terminated = False
        truncated = False
        self.episode_length += 1

        if len(self.data) > 0:
            price = self.data.iloc[self.current_step]["Close"]
        else:
            price = 0.0

        # Advance time before action logic so current_step reflects the
        # step we just consumed (used in day_progress inside reward)
        self.current_step += 1
        step_reward = 0.0

        # --- 1. Execute action ---

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

        elif action == 3 and self.active_trade:  # Close position
            self.no_trades_completed += 1

            # FIX: consistent fee application — subtract fee as flat amount
            # after the multiplied profit (matches LiveTradingEnv)
            trade_profit = (
                (price - self.active_trade_entry_price)
                * self.active_trade_direction
                * self.price_multiplier
            )
            trade_profit -= self.trade_fee  # exit fee as flat amount

            self.pnl += trade_profit
            self.avg_trade_duration = (
                (self.avg_trade_duration * (self.no_trades_completed - 1))
                + self.active_trade_duration
            ) / self.no_trades_completed

            if trade_profit > 0:
                self.winning_trades += 1
            else:
                self.losing_trades += 1

            # FIX #2 + #3: terminal reward is self-contained, no debt subtraction
            step_reward = self.calculate_final_reward(trade_profit, self.active_trade_duration)

            # Reset trade state
            self.active_pnl = 0.0
            self.active_trade = False
            self.active_trade_direction = 0
            self.active_trade_entry_price = 0.0
            self.active_trade_duration = 0

        # --- 2. Shaping reward while holding ---
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
            step_reward = (delta_pnl * 0.01) - theta_penalty
            # FIX #3: do NOT accumulate into total_intermediate_given —
            # terminal reward at close is fully independent of shaping history

        else:
            self.active_pnl = 0.0

        # --- 3. Update global metrics ---
        total_pnl = self.pnl + self.active_pnl
        current_balance = self.balance + total_pnl

        if current_balance > self.peak_balance:
            self.peak_balance = current_balance

        current_drawdown = (
            (self.peak_balance - current_balance) / self.peak_balance
            if self.peak_balance > 0
            else 0.0
        )
        if current_drawdown > self.max_drawdown:
            self.max_drawdown = current_drawdown

        self.pnl_list.append(total_pnl)

        # --- 4. Episode termination conditions ---
        if self.current_step >= (self.max_steps - 1) and not self.evaluation:
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
            "losing_trades": self.losing_trades,
        }

        if (terminated or truncated) and not self.evaluation:
            print(f"Episode details for episode id: {self.episode_id}")
            print(info)
            self.episode_id += 1

        # In evaluation mode, don't hard-terminate on drawdown — let it run
        if terminated and self.evaluation:
            terminated = False

        # --- 5. Evaluation: roll to next day when current day exhausted ---
        if self.evaluation and self.current_step >= (self.max_steps - 1):
            next_date = self.data["Date"].iloc[0].date() + timedelta(days=1)
            new_data, status = get_data(
                symbol=self.symbol,
                start_date=next_date,
                end_date=self.end_date,
                db=self.db,
                evaluation=self.evaluation,
            )

            if len(new_data) > 0:
                self.logger.info(
                    f"Evaluation day Data time range: "
                    f"{new_data['Date'].iloc[0]} to {new_data['Date'].iloc[-1]}"
                )

            if status == "END_DATE_REACHED" or new_data is None or len(new_data) == 0:
                truncated = True
            else:
                self.data = new_data
                self.data.reset_index(drop=True, inplace=True)
                self.current_step = 0
                self.max_steps = len(self.data)

                # Force-close any open trade at day boundary
                if self.active_trade:
                    self.no_trades_completed += 1
                    trade_profit = (
                        (price - self.active_trade_entry_price)
                        * self.active_trade_direction
                        * self.price_multiplier
                    )
                    self.pnl += trade_profit - self.trade_fee
                    self.avg_trade_duration = (
                        (self.avg_trade_duration * (self.no_trades_completed - 1))
                        + self.active_trade_duration
                    ) / self.no_trades_completed
                    self.peak_balance = 0.0
                    self.active_pnl = 0.0
                    self.active_trade = False
                    self.active_trade_direction = 0
                    self.active_trade_entry_price = 0.0
                    self.active_trade_duration = 0

        obs = self._get_observation()
        return obs, step_reward, terminated, truncated, info


# ==============================================================================
# LiveTradingEnv — streams one row at a time from RL_Stream_Data
# ==============================================================================

class LiveTradingEnv(TradingEnv):
    """
    Live/Streamed Trading Environment.
    Instead of loading a full day of data upfront, this environment updates
    its state one row at a time from the RL_Stream_Data generator.

    Inherits calculate_final_reward and the Dict observation space from
    TradingEnv — no reward or obs-space logic is duplicated here.
    """

    def __init__(self, db, symbol, obs_features, streamer, **kwargs):
        self.stream_gen = None
        self.current_row = None
        self.last_timestamp = None
        self.streamer = streamer
        self.obs_features = obs_features
        self.progress = 0.0

        # Pass dummy dates — the streamer controls the timeline
        super().__init__(
            db=db,
            symbol=symbol,
            start_date=None,
            end_date=None,
            obs_features=obs_features,
            evaluation=True,
            **kwargs,
        )

        if self.logger:
            self.logger.info("LiveTradingEnv initialized and ready for streaming.")

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self, *, seed=None, options=None):
        """
        Resets the environment state and restarts the data stream.
        Bypasses TradingEnv's data-loading reset via gym.Env.reset directly.
        """
        gym.Env.reset(self, seed=seed)

        # Restart the stream generator
        self.stream_gen = self.streamer.stream()
        self.logger.info("LiveTradingEnv reset: Stream generator initialized.")

        try:
            self.current_row = next(self.stream_gen)
            self.progress = 0.0
            self.logger.info(f"LiveTradingEnv reset, progress: {self.progress:.4f}")
            self.logger.info(f"First streamed row received: {self.current_row}")
            self.logger.info(f"Columns in streamed row: {self.current_row.index.tolist()}")
            self.last_timestamp = self.current_row["Date"]
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
        self.active_trade_direction = 0
        self.active_trade_entry_price = 0.0
        self.active_trade_duration = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.pnl_history = []
        self.pnl_list = [0.0]
        self.xg_high = 0.0
        self.xg_low = 0.0

        obs = self._get_observation()
        info = {"timestamp": self.last_timestamp}
        return obs, info

    # ------------------------------------------------------------------
    # Observation — uses streamed row instead of self.data DataFrame
    # ------------------------------------------------------------------

    def _get_observation(self):
        """
        Constructs the Dict observation from the current streamed row
        and the real-time agent state.
        """
        # 1. Market features from the streamed row
        market_obs = np.array(
            [self.current_row[f] for f in self.obs_features],
            dtype=np.float32,
        )

        # 2. Continuous agent state
        total_pnl = self.pnl + self.active_pnl
        loss_ratio = float(np.clip(
            total_pnl / self.max_episode_loss if self.max_episode_loss != 0 else 0.0,
            -1.0, 1.0,
        ))

        continuous_obs = np.concatenate([
            market_obs,
            np.array([self.progress, loss_ratio], dtype=np.float32),
        ])

        # 3. Discrete agent state — bypasses VecNormalize
        discrete_obs = np.array([
            float(self.active_trade),
            float(self.active_trade_direction),
        ], dtype=np.float32)

        self.logger.info(f"Market obs shape: {market_obs.shape}")
        self.logger.info(
            f"Market obs: {np.array2string(market_obs, precision=4, separator=',')}"
        )
        self.logger.info(
            f"Agent | progress={self.progress:.4f} loss_ratio={loss_ratio:.4f} "
            f"active_trade={self.active_trade} direction={self.active_trade_direction}"
        )

        obs = {"continuous": continuous_obs, "discrete": discrete_obs}

        if np.isnan(continuous_obs).any() and self.logger:
            self.logger.warning(f"NaN in Live Observation at {self.last_timestamp}")

        return obs

    # ------------------------------------------------------------------
    # Step — pulls next row from the stream
    # ------------------------------------------------------------------

    def step(self, action):
        """
        Executes one action on the current streamed row,
        then pulls the NEXT row from the stream.
        """
        truncated = False
        step_reward = 0.0

        # Price from the row we are currently acting on
        price = self.current_row["Close"]
        self.last_timestamp = self.current_row["Date"]

        # --- 1. Execute action ---

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

        elif action == 3 and self.active_trade:  # Close position
            self.no_trades_completed += 1

            # FIX: consistent fee application — flat amount after multiplied profit
            trade_profit = (
                (price - self.active_trade_entry_price)
                * self.active_trade_direction
                * self.price_multiplier
            )
            trade_profit -= self.trade_fee

            self.pnl += trade_profit

            if trade_profit > 0:
                self.winning_trades += 1
            else:
                self.losing_trades += 1

            # FIX #2 + #3: self-contained terminal reward, no debt subtraction
            step_reward = self.calculate_final_reward(trade_profit, self.active_trade_duration)

            # Reset trade state
            self.active_pnl = 0.0
            self.active_trade = False
            self.active_trade_direction = 0
            self.active_trade_entry_price = 0.0
            self.active_trade_duration = 0

        # --- 2. Shaping reward while holding ---
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

            # Theta-aware time decay: growing penalty mirrors real options theta
            theta_penalty = 0.0005 * (1.0 + self.active_trade_duration / 30.0)
            step_reward = (delta_pnl * 0.01) - theta_penalty
            # FIX #3: NOT accumulated — terminal reward is independent

        # --- 3. Update global metrics ---
        total_pnl = self.pnl + self.active_pnl
        current_balance = self.initial_balance + total_pnl

        if current_balance > self.peak_balance:
            self.peak_balance = current_balance

        drawdown = (
            (self.peak_balance - current_balance) / self.peak_balance
            if self.peak_balance > 0
            else 0.0
        )
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown

        # --- 4. Pull next row from the stream ---
        try:
            self.current_row = next(self.stream_gen)
            self.progress = (
                self.current_row["step_progress"]
                if "step_progress" in self.current_row
                else self.progress
            )
            self.pred_high = self.current_row["pred_high"]
            self.pred_low = self.current_row["pred_low"]
            self.current_step += 1
        except StopIteration:
            truncated = True

        info = {
            "total_pnl": total_pnl,
            "realized_pnl": self.pnl,
            "active_trade": self.active_trade,
            "balance": current_balance,
            "max_drawdown_pct": self.max_drawdown * 100,
            "timestamp": self.last_timestamp,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
        }

        return self._get_observation(), step_reward, False, truncated, info
