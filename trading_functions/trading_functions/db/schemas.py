from datetime import datetime
from pydantic import BaseModel
f


class PriceDataBase(BaseModel):
    symbol: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int