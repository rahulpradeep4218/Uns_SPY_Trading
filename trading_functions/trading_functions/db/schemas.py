from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Literal

class PriceDataBase(BaseModel):
    symbol: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

class PriceDataCreate(PriceDataBase):
    pass

class PriceDataResponse(PriceDataBase):
    model_config = ConfigDict( from_attributes=True )


class TradeRecordBase(BaseModel):
    session_id: int
    trade_time: datetime
    high_val: float = None
    low_val: float = None
    signal: int = None
    status: str = "SIGNAL"  # Default status is SIGNAL
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    buy_stop_loss: Optional[float] = None
    buy_take_profit: Optional[float] = None
    sell_stop_loss: Optional[float] = None
    sell_take_profit: Optional[float] = None
    calc_stop_loss: Optional[float] = None  # Calculated stop loss
    calc_take_profit: Optional[float] = None  # Calculated take profit
    profit: float = 0.0
    exit_reason: Optional[str] = None  # e.g., "stop_loss", "take_profit", "max_hold_time"

class TradeRecordCreate(TradeRecordBase):
    pass

class TradeRecordResponse(TradeRecordBase):
    symbol: Optional[str]
    model_config = ConfigDict(from_attributes=True)

class TradeSessionBase(BaseModel):
    id: Optional[int] = None
    type: str
    symbol: str
    trade_start: Optional[datetime] = None
    trade_end: Optional[datetime] = None
    model_high_version: int = None
    model_high_alias: Optional[str] = None
    model_low_version: int = None
    model_low_alias: Optional[str] = None

class TradeSessionCreate(TradeSessionBase):
    pass

class TradeSessionUpdate(BaseModel):
    type: Optional[str] = None
    symbol: Optional[str] = None
    trade_start: Optional[datetime] = None
    trade_end: Optional[datetime] = None
    model_high_version: Optional[int] = None
    model_high_alias: Optional[str] = None
    model_low_version: Optional[int] = None
    model_low_alias: Optional[str] = None

class TradeSessionResponse(TradeSessionBase):
    id: int
    trade_records: Optional[List[TradeRecordResponse]] = []

    model_config = ConfigDict(from_attributes=True)


class Coverage(BaseModel):
    start: Optional[datetime]
    end: Optional[datetime]

class CoverageResponse(BaseModel):
    start: Optional[datetime]
    end: Optional[datetime]
    coverage: List[Coverage] = []


### Simulation Schemas
class SimulationOptions(BaseModel):
    close_at_eod: bool = True
    max_hold_time: int = 120  # in minutes
    sl_type: Literal["percent", "abs", "model", "atr"] = "percent"  # "percent" or absolute or model"
    sl_value: float = 0.02  # 2% stop loss
    tp_type: Literal["percent", "abs", "model", "atr"] = "abs"  # "percent" or absolute or model
    tp_value: float = 2.0  # 5% take profit
    max_gap_days_allowed: int = 4  # Maximum gap in days allowed between current candle and last lagging candle
    sell_or_buy_threshold: float = 3
    risk_threshold: float = 0.8
    allow_multiple_open_trades: bool = False  # Allow multiple trades in the same session
    close_using_signal: bool = False  # Close trades using signal
    start_time: Optional[datetime] = None  # Start time for simulation
    end_time: Optional[datetime] = None  # End time for simulation
    speed: float = 1.0  # Speed of simulation, 1.0 is real-time, 2.0 is double speed, etc.
    starting_balance: float = 5000.0  # Starting balance for the simulation
    max_day_loss_percent: float = 3.0


class TradeStats(BaseModel):
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    winning_percentage: float = 0.0
    average_profit: float = 0.0
    total_profit: float = 0.0
    unrealized_profit: float = 0.0
    percent_complete: float = 0.0


