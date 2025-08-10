from sqlalchemy.orm import Session
from trading_functions.db import models, schemas
from typing import Optional
from datetime import datetime

def get_trade_session(db: Session, session_id: int) -> schemas.TradeSessionResponse:
    return db.query(models.TradeSession).filter(models.TradeSession.id == session_id).first()

def get_trade_sessions(db: Session, skip: int = 0, limit: int = 100, type: str = None) -> list[schemas.TradeSessionResponse]:
    query = db.query(models.TradeSession)
    if type:
        query = query.filter(models.TradeSession.type == type)
    query = query.offset(skip).limit(limit)
    return query.all()

def create_trade_session(db: Session, session: schemas.TradeSessionCreate) -> schemas.TradeSessionResponse:
    db_session = models.TradeSession(**session.model_dump())
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session

def update_trade_session(db: Session, session_id: int, session: schemas.TradeSessionUpdate) -> schemas.TradeSessionResponse:
    db_session = db.query(models.TradeSession).filter(models.TradeSession.id == session_id).first()
    if db_session:
        for key, value in session.model_dump(exclude_unset=True).items():
            setattr(db_session, key, value)
        print("Updated session data:", db_session)
        db.commit()
        db.refresh(db_session)
    return db_session

def delete_trade_session(db: Session, session_id: int)-> bool:
    db_session = db.query(models.TradeSession).filter(models.TradeSession.id == session_id).first()
    if db_session:
        db.delete(db_session)
        db.commit()
        return True
    return False


# PRICE DATA
def get_price_data_by_symbol(db: Session, symbol: str, start_time: Optional[datetime], end_time: Optional[datetime], limit: Optional[int]) -> list[schemas.PriceDataResponse]:
    query = db.query(models.PriceData).filter(models.PriceData.symbol == symbol)

    if start_time:
        query = query.filter(models.PriceData.time >= start_time)
    if end_time:
        query = query.filter(models.PriceData.time <= end_time)
    query = query.order_by(models.PriceData.time)
    if limit:
        query = query.limit(limit)
    return query.all()

