from datetime import datetime
from pydantic import BaseModel
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

class PriceDateResponse(PriceDataBase):
    class Config:
        orm_mode = True


class TradeRecordBase(BaseModel):
    session_id: int
    trade_time: datetime
    high_val: Optional[float] = None
    low_val: Optional[float] = None
    signal: Optional[int] = None
    realized: bool = False
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    profit: Optional[float] = 0.0

class TradeRecordCreate(TradeRecordBase):
    pass

class TradeRecordResponse(TradeRecordBase):
    symbol: Optional[str]

    class Config:
        orm_mode = True

class TradeSessionBase(BaseModel):
    type: str
    symbol: str
    trade_start: Optional[datetime] = None
    trade_end: Optional[datetime] = None
    model_high_version: Optional[int] = None
    model_high_alias: Optional[str] = None
    model_low_version: Optional[int] = None
    model_low_alias: Optional[str] = None

class TradeSessionCreate(TradeSessionBase):
    pass

class TradeSessionResponse(TradeSessionBase):
    id: int
    trade_records: Optional[List[TradeRecordResponse]] = []

    class Config:
        orm_mode = True


class Gap(BaseModel):
    gap_start: Optional[datetime]
    gap_end: Optional[datetime]

class OHLCGapsResponse(BaseModel):
    start: Optional[datetime]
    end: Optional[datetime]
    gaps: List[Gap] = []
