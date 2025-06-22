from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.schema import ForeignKeyConstraint
from typing import Optional, List
from datetime import datetime
from app.db.session import Base


class TradeSession(Base):
    __tablename__ = "trade_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "live", "backtest"
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    trade_start: Mapped[Optional[datetime]] = mapped_column(DateTime)
    trade_end: Mapped[Optional[datetime]] = mapped_column(DateTime)
    model_high_version: Mapped[int] = mapped_column(Integer)
    model_high_alias: Mapped[Optional[str]] = mapped_column(String)
    model_low_version: Mapped[int] = mapped_column(Integer)
    model_low_alias: Mapped[Optional[str]] = mapped_column(String)

    trade_records: Mapped[List["TradeRecord"]] = relationship("TradeRecord", back_populates="session", cascade="all, delete-orphan")


class TradeRecord(Base):
    __tablename__ = "trade_records"
    session_id: Mapped[int] = mapped_column(Integer, 
                                            ForeignKey("trade_sessions.id", ondelete="CASCADE"), 
                                            nullable=False, 
                                            primary_key=True
                            )  
    symbol: Mapped[str] = mapped_column(String, nullable=False, primary_key=True)
    trade_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, primary_key=True)
    high_val: Mapped[float] = mapped_column(Float)
    low_val: Mapped[float] = mapped_column(Float)
    signal: Mapped[int] = mapped_column(Integer, default=0)
    realized: Mapped[bool] = mapped_column(Boolean, default=False)
    entry_price: Mapped[Optional[float]] = mapped_column(Float)
    exit_price: Mapped[Optional[float]] = mapped_column(Float)
    profit: Mapped[float] = mapped_column(Float, default=0.0)

    session: Mapped["TradeSession"] = relationship("TradeSession", back_populates="trade_records")
    ohlc_data: Mapped[Optional["PriceData"]] = relationship("PriceData", viewonly=True,
                             primaryjoin="and_(TradeRecord.symbol == foreign(PriceData.symbol), "
                             "TradeRecord.trade_time == foreign(PriceData.time))"
    )

class PriceData(Base):
    __tablename__ = "price_data"
    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    time: Mapped[datetime] = mapped_column(DateTime, primary_key=True, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)