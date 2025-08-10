from fastapi import APIRouter, Depends, HTTPException, Query, Form
from sqlalchemy.orm import Session
from trading_functions.db import schemas, crud
from app.api.deps import get_db
from typing import Optional, List
from datetime import datetime
from app.utility.insert_excel_data_db import add_ohlc_data_from_excel

router = APIRouter()

@router.get("/{symbol}", response_model=list[schemas.PriceDataResponse])
def get_price_data(
    symbol: str,
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=10000, description="Limit the number of results returned (default is no limit)"),
    db: Session = Depends(get_db)
) -> list[schemas.PriceDataResponse]:
    """
    Retrieve price data for a specific symbol within an optional time range.
    """
    return crud.get_price_data_by_symbol(
        db, 
        symbol=symbol, 
        start_time=start_time, 
        end_time=end_time,
        limit=limit
    )


@router.post("/{symbol}/add_from_excel" )
def add_price_data_from_excel(symbol: str, 
                              start_time: str = Form(
                                  ...,
                                  example="2023-01-01T00:00:00",
                                  description="Start time in ISO 8601 format (e.g., '2023-02-01T00:00:00')"
                              ), end_time: str = Form(
                                    ...,
                                    example="2023-01-31T23:59:59",
                                    description="End time in ISO 8601 format (e.g., '2023-02-28T23:59:59')"
                              )):
    """
    Add price data for a specific symbol from an Excel file.
    """
    try:
        start_time_dt = datetime.fromisoformat(start_time)
        end_time_dt = datetime.fromisoformat(end_time)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS).")

    message = add_ohlc_data_from_excel(symbol=symbol, start_date=start_time_dt, end_date=end_time_dt)
    return {"message": message}
    