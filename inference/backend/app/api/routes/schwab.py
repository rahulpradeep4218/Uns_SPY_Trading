from multiprocessing import connection
from numbers import Real
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from app.methods.schwab_methods import (
    get_schwab_config, 
    exchange_code_for_token, 
    update_schwab_config,
    check_schwab_connection,
    get_price_history,
    get_realtime_quote,
    get_schwab_connection_info_from_db
)
import pandas as pd
from trading_functions.db.models import PriceData
from sqlalchemy.orm import Session
from trading_functions.db.session import SessionLocal
from sqlalchemy.dialects.postgresql import insert

router = APIRouter()

@router.get("/callback", response_class=HTMLResponse)
async def schwab_callback(request: Request):
    """
    Handle the callback from Schwab after user authorization.
    """
    try:
        # Extract the authorization code from the request
        auth_code = request.query_params.get('code')
        if not auth_code:
            raise HTTPException(status_code=400, detail="Authorization code not found in the request.")

        # Exchange the authorization code for an access token
        schwab_config = get_schwab_config()
        token_response = exchange_code_for_token(auth_code, schwab_config)
        if not token_response:
            raise HTTPException(status_code=500, detail="Failed to exchange authorization code for access token.")
        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")
        if not access_token or not refresh_token:
            raise HTTPException(status_code=500, detail="Access token or refresh token not found in the response.")

        # Update the configuration with the new tokens
        update_schwab_config("access_token", access_token)
        update_schwab_config("refresh_token", refresh_token)

        # Return a success message with the token information
        return HTMLResponse(content=f"Authorization successful!<br/> Access Token and refresh token updated in the configuration file.<br/>")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.get("/check_connection")
async def check_connection():
    """
    Check the connection to the Schwab API.
    """
    try:
        connection_info = await get_schwab_connection_info_from_db("SPY")

        return connection_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-realtime-quote")
async def get_realtime_quote_api(symbol: str):
    """
    Get the real-time quote for a specific symbol.
    """
    try:
        schwab_config = get_schwab_config()
        connection_status = await check_schwab_connection(schwab_config)
        if connection_status.get("status", "") != "SUCCESS":
            message = connection_status.get("message", "")
            raise HTTPException(status_code=500, detail=f"Not able to connect to Schwab API, message: {message}")
        res = await get_realtime_quote(
            symbol=symbol,
            schwab_config=schwab_config
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync-realtime")
async def sync_realtime(symbol: str, period: int = 1, use_period: bool = True, start_time: str = None):
    """
    Sync real-time data with the Schwab API.
    """
    try:
        db: Session = SessionLocal()
        schwab_config = get_schwab_config()
        access_token = schwab_config.get("access_token")
        connection_status = check_schwab_connection(schwab_config)
        if connection_status.get("status", "") != "SUCCESS":
            message = connection_status.get("message", "")
            raise HTTPException(status_code=500, detail=f"Not able to connect to schwab API, message : {message}")
        data_res = get_price_history(
            symbol=symbol,
            access_token=access_token,
            schwab_config=schwab_config,
            period=period,
            frequency=1,
            frequency_type="minute",
            use_period=use_period,
            start_date_time=start_time
        )
        data = data_res.json()
        df = pd.DataFrame(data['candles'])
        df['time'] = (
            pd.to_datetime(df['datetime'], unit="ms", utc=True)
            .dt.tz_convert("America/New_York")
            .dt.strftime("%Y-%m-%d %H:%M:%S")
        )
        df['time'] = pd.to_datetime(df['time'], format="%Y-%m-%d %H:%M:%S")

        rows = [
            {
                'symbol': symbol,
                'time': row['time'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume']
            }
            for _, row in df.iterrows()
        ]
        stmt = insert(PriceData).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=['symbol', 'time'])

        db.execute(stmt)
        db.commit()
        return {"status": "success", "message": "Data synced successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))