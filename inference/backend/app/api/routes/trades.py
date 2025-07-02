from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from torch import seed
from app.db import models, schemas
from app.api.deps import get_db
from typing import List, Dict
from app.db.schemas import Coverage, CoverageResponse
from trading_functions.inference.inf_functions import (
    make_random_candles
)
import numpy as np
from app.utility.seed_random_ohlc_data import seed_random_ohlc_data

router = APIRouter()


@router.get("/random_candles")
def get_random_candles():
    message = seed_random_ohlc_data()
    return {
        "message": message
    }


@router.get("/ohlc/coverage", response_model = CoverageResponse)
def get_ohlc_data_coverage(
    symbol: str,
    db: Session = Depends(get_db)
):
    # First get the date range for the symbol
    date_range_query = """
        SELECT 
        DATE(MIN(time)) AS min_date, 
        DATE(MAX(time)) AS max_date
        FROM price_data 
        WHERE symbol = :symbol
    """

    date_range = db.execute(text(date_range_query), {"symbol": symbol}).mappings().fetchone()

    if not date_range or not date_range["min_date"] or not date_range["max_date"]:
        return {
            "start": None,
            "end": None,
            "coverage": []
        }
    
    min_date = date_range["min_date"]
    max_date = date_range["max_date"]

    # Get dates that have data
    existing_dates_query = """
        SELECT DISTINCT DATE(time) AS date
        FROM price_data 
        WHERE symbol = :symbol
        ORDER BY DATE(time)
    """
    existing_dates = db.execute(text(existing_dates_query), {"symbol": symbol}).mappings().fetchall()
    existing_dates = [row["date"] for row in existing_dates]

    #Convert existing dates to coverage intervals
    coverage = []
    if not existing_dates:
        return {
            "start": min_date,
            "end": max_date,
            "coverage": []
        }
    current_range_start = existing_dates[0]

    for i in range(1, len(existing_dates)):
        if (existing_dates[i] - existing_dates[i - 1]).days > 1:
            # End of current coverage
            coverage.append({
                "start": datetime.combine(current_range_start, datetime.min.time()),
                "end": datetime.combine(existing_dates[i - 1], datetime.max.time())
            })
            current_range_start = existing_dates[i]

    # Add the last range
    coverage.append({
        "start": datetime.combine(current_range_start, datetime.min.time()),
        "end": datetime.combine(existing_dates[-1], datetime.max.time())
    })

    # Get actual start and end times
    start_time_query = """
        SELECT MIN(time) AS start_time, MAX(time) AS end_time
        FROM price_data 
        WHERE symbol = :symbol
    """
    start_end = db.execute(text(start_time_query), {"symbol": symbol}).mappings().fetchone()

    return {
        "start": start_end["start_time"],
        "end": start_end["end_time"],
        "coverage": coverage
    }



def get_ohlc_gaps_backup(
    symbol: str, 
    db: Session = Depends(get_db)
):
    
    query = """
    WITH ordered_data AS (
        SELECT symbol,
            time,
            LAG(time) OVER (PARTITION BY symbol ORDER BY time) AS prev_dt,
            LEAD(time) OVER (PARTITION BY symbol ORDER BY time) AS next_dt
        FROM price_data WHERE symbol = :symbol
    ),
    gaps AS(
        SELECT symbol,
        time AS gap_start,
        next_dt AS gap_end,
        EXTRACT(EPOCH FROM next_dt - time) AS gap_seconds
        FROM ordered_data
        WHERE next_dt IS NOT NULL AND EXTRACT(EPOCH FROM next_dt - time) > 60
    ),
    range_gaps AS (
        SELECT 'SPY' AS symbol, NULL AS gap_start, MIN(time) AS gap_end, NULL::float AS gap_seconds
        FROM price_data WHERE symbol = :symbol

        UNION ALL
            
        SELECT 'SPY' AS symbol, MAX(time) AS gap_start, NULL AS gap_end, NULL::float AS gap_seconds
        FROM price_data WHERE symbol = :symbol
    )
    SELECT * FROM gaps
    UNION ALL
    SELECT * FROM range_gaps;
    """
    result = db.execute(text(query), {"symbol": symbol}).mappings().fetchall()

    start_end_query = """
        SELECT MIN(time) AS start_time, MAX(time) AS end_time
        FROM price_data WHERE symbol = :symbol
    """
    start_end = db.execute(text(start_end_query), {"symbol": symbol}).mappings().fetchone()

    return {
        "start": start_end["start_time"],
        "end": start_end["end_time"],
        "gaps": [
            {
                "gap_start": row["gap_start"],
                "gap_end": row["gap_end"],
            }
            for row in result
        ]
    }

