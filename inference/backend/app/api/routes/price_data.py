from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import models, schemas, crud
from app.api.deps import get_db
from typing import Optional, List
from datetime import datetime

router = APIRouter()

@router.get("/{symbol}", response_model=list[schemas.PriceDataResponse])
def get_price_data(
    symbol: str,
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
) -> list[schemas.PriceDataResponse]:
    """
    Retrieve price data for a specific symbol within an optional time range.
    """
    return crud.get_price_data_by_symbol(
        db, 
        symbol=symbol, 
        start_time=start_time, 
        end_time=end_time
    )