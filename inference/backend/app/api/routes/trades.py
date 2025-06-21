from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db import models, schemas
from app.api.deps import get_db
from typing import List, Dict
from app.db.schemas import Gap, OHLCGapsResponse
from trading_functions.inference.inf_functions import (
    make_random_candles
)
import numpy as np

router = APIRouter()


@router.get("/random_candles")
def get_random_candles(n: int = 100, freq_minutes: int = 1):
    """
    Generate random candles for testing purposes.
    
    Parameters:
    - n: Number of candles to generate
    - freq_minutes: Frequency in minutes for the candles
    
    Returns:
    - List of dictionaries representing the candles
    """
    candles_df = make_random_candles(n, freq_minutes)
    return {
        "xValues": (candles_df['date'].astype(np.int64) // 10**6).tolist(),
        "openValues": candles_df['open'].round(2).tolist(),
        "highValues": candles_df['high'].round(2).tolist(),
        "lowValues": candles_df['low'].round(2).tolist(),
        "closeValues": candles_df['close'].round(2).tolist()
    }


@router.get("/ohlc/gaps", response_model = OHLCGapsResponse )
def get_ohlc_gaps(
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