from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional, List

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
    realized: bool = False
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    profit: float = 0.0

class TradeRecordCreate(TradeRecordBase):
    pass

class TradeRecordResponse(TradeRecordBase):
    symbol: Optional[str]
    model_config = ConfigDict(from_attributes=True)

class TradeSessionBase(BaseModel):
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

class TradeSessionResponse(TradeSessionBase):
    id: int
    trade_records: Optional[List[TradeRecordResponse]] = []

    model_config = ConfigDict(from_attributes=True)


class Gap(BaseModel):
    gap_start: Optional[datetime]
    gap_end: Optional[datetime]

class OHLCGapsResponse(BaseModel):
    start: Optional[datetime]
    end: Optional[datetime]
    gaps: List[Gap] = []
