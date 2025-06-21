from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.schema import ForeignKeyConstraint
from app.db.session import Base


class TradeSession(Base):
    __tablename__ = "trade_sessions"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False)  # e.g., "live", "backtest"
    symbol = Column(String, nullable=False)
    trade_start = Column(DateTime)
    trade_end = Column(DateTime)
    model_high_version = Column(Integer)
    model_high_alias = Column(String)
    model_low_version = Column(Integer)
    model_low_alias = Column(String)

    trade_records = relationship("TradeRecord", back_populates="session", cascade="all, delete-orphan")


class TradeRecord(Base):
    __tablename__ = "trade_records"
    session_id = Column(Integer, ForeignKey("trade_sessions.id", ondelete="CASCADE"), nullable=False, primary_key=True)
    symbol = Column(String, nullable=False, primary_key=True)
    trade_time = Column(DateTime, nullable=False, primary_key=True)
    high_val = Column(Float)
    low_val = Column(Float)
    signal = Column(Integer)
    realized = Column(Boolean, default=False)
    entry_price = Column(Float)
    exit_price = Column(Float)
    profit = Column(Float)

    session = relationship("TradeSession", back_populates="trade_records")
    ohlc_data = relationship("PriceData", viewonly=True,
                             primaryjoin="and_(TradeRecord.symbol == foreign(PriceData.symbol), "
                             "TradeRecord.trade_time == foreign(PriceData.time))"
    )

class PriceData(Base):
    __tablename__ = "price_data"
    symbol = Column(String, primary_key=True, index=True)
    time = Column(DateTime, primary_key=True, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Integer)