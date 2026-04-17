from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship, Mapped, mapped_column
from typing import Optional, List
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
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)
    high_val: Mapped[float] = mapped_column(Float)
    low_val: Mapped[float] = mapped_column(Float)
    signal: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="SIGNAL")
    entry_price: Mapped[Optional[float]] = mapped_column(Float)
    exit_price: Mapped[Optional[float]] = mapped_column(Float)
    buy_stop_loss: Mapped[Optional[float]] = mapped_column(Float, default=None)
    buy_take_profit: Mapped[Optional[float]] = mapped_column(Float, default=None)
    sell_stop_loss: Mapped[Optional[float]] = mapped_column(Float, default=None)
    sell_take_profit: Mapped[Optional[float]] = mapped_column(Float, default=None)
    calc_stop_loss: Mapped[Optional[float]] = mapped_column(Float, default=None)  # Calculated stop loss
    calc_take_profit: Mapped[Optional[float]] = mapped_column(Float, default=None)
    profit: Mapped[float] = mapped_column(Float, default=0.0)
    exit_reason: Mapped[Optional[str]] = mapped_column(String, default=None)  # e.g., "stop_loss", "take_profit", "max_hold_time"

    session: Mapped["TradeSession"] = relationship("TradeSession", back_populates="trade_records")
    ohlc_data: Mapped[Optional["PriceData"]] = relationship("PriceData", viewonly=True,
                             primaryjoin="and_(TradeRecord.symbol == foreign(PriceData.symbol), "
                             "TradeRecord.trade_time == foreign(PriceData.time))"
    )


class RealtimeData(Base):
    __tablename__ = "realtime_data"
    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    time: Mapped[datetime] = mapped_column(DateTime)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    realtime_last_sync_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)
    history_last_sync_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)

class SchwabOrders(Base):
    __tablename__ = "schwab_orders"
    open_order_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    close_order_id: Mapped[str] = mapped_column(String, index=True)
    open_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    close_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, default=None)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, default=None)
    entry_price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    option_entry_price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    option_exit_price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    open_status: Mapped[str] = mapped_column(String, default="OPEN")
    close_status: Mapped[Optional[str]] = mapped_column(String, default=None)  # e.g., "CLOSED", "CANCELLED"
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    profit: Mapped[Optional[float]] = mapped_column(Float, default=None)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(String, default="")  # Additional notes for the order