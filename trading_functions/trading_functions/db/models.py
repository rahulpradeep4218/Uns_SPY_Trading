from sqlalchemy import Integer, String, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column

from datetime import datetime
from trading_functions.db.session import Base

class PriceData(Base):
    __tablename__ = "price_data"
    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    time: Mapped[datetime] = mapped_column(DateTime, primary_key=True, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)