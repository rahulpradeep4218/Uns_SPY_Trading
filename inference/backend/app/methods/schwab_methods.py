import base64
from multiprocessing import connection
from tracemalloc import stop
import requests
from inference.backend.app.api.routes import schwab
from ruamel.yaml import YAML
from datetime import datetime, timezone
import os
import pandas as pd
from dateutil import tz
from app.utility.time_utilities import to_epoch_ms_est
from trading_functions.db.models import PriceData, RealtimeData, SchwabOrders
from sqlalchemy.orm import Session
from trading_functions.db.session import SessionLocal
from trading_functions.db.models import RealtimeData
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func
import logging
from time import time
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


yaml = YAML()
config_path_env = os.getenv('CONFIG_PATH', '')

def update_schwab_config(config_name: str, config_value, config_path: str = None):
    if config_path is None:
        config_path = config_path_env
    with open(config_path, 'r') as file:
        config = yaml.load(file)
    config['inference']['schwab'][config_name] = config_value

    with open(config_path, 'w') as file:
        yaml.dump(config, file)

def get_schwab_config(config_path: str = None) -> dict:
    if config_path is None:
        config_path = config_path_env
    with open(config_path, 'r') as file:
        config = yaml.load(file)
    return config['inference']['schwab']

def get_inf_config():
    inf_config_path = os.getenv('CONFIG_PATH', 'NO_PATH')
    if not inf_config_path or not os.path.exists(inf_config_path):
        raise FileNotFoundError(f"Configuration file not found at {inf_config_path}")
    
    with open(inf_config_path, 'r') as file:
        inf_config = yaml.load(file)
    
    return inf_config


def exchange_code_for_token(auth_code: str, schwab_config: dict) -> str:
    """
    Exchange the provided authorization code for an access token.

    Returns a dict containing access_token, refresh_token, expires_in, and scope.
    """
    # Prepare Basic Auth header
    client_id = schwab_config.get("client_id")
    client_secret = schwab_config.get("client_secret")
    redirect_uri = schwab_config.get("redirect_uri")
    token_url = schwab_config.get('base_oauth_url') + schwab_config.get('token_url_add')
    credentials = f"{client_id}:{client_secret}".encode("utf-8")
    basic_auth = base64.b64encode(credentials).decode("utf-8")
    #print(f"Basic Auth: {basic_auth}")
    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "scope": "readonly"
    }
    #print(f"Data : {data}")
    response = requests.post(url=token_url, headers=headers, data=data)
    if response.status_code != 200:
        print(f"Error fetching Schwab token using code: {auth_code} HTTP {response.status_code}")
        print("Response body:", response.text)
        return response.json()
    #print(f"Response: {response.json()}")
    return response.json()


def exchange_code_for_token_account(auth_code: str, schwab_config: dict) -> str:
    """
    Exchange the provided authorization code for an access token.

    Returns a dict containing access_token, refresh_token, expires_in, and scope.
    """
    # Prepare Basic Auth header
    client_id = schwab_config.get("client_id_account")
    client_secret = schwab_config.get("client_secret_account")
    redirect_uri = schwab_config.get("redirect_uri_account")
    token_url = schwab_config.get('base_oauth_url') + schwab_config.get('token_url_add')
    credentials = f"{client_id}:{client_secret}".encode("utf-8")
    basic_auth = base64.b64encode(credentials).decode("utf-8")
    #print(f"Basic Auth: {basic_auth}")
    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "scope": "readonly"
    }
    #print(f"Data : {data}")
    response = requests.post(url=token_url, headers=headers, data=data)
    if response.status_code != 200:
        print(f"Error fetching Schwab token using code: {auth_code} HTTP {response.status_code}")
        print("Response body:", response.text)
        return response.json()
    #print(f"Response: {response.json()}")
    return response.json()

async def update_access_token_using_refresh_token(schwab_config: dict) -> dict:
    """
    Refresh the access token using the provided refresh token.

    Returns a dict containing access_token, expires_in, and scope.
    """
    client_id = schwab_config.get("client_id")
    client_secret = schwab_config.get("client_secret")
    refresh_token = schwab_config.get("refresh_token")
    credentials = f"{client_id}:{client_secret}".encode("utf-8")
    basic_auth = base64.b64encode(credentials).decode("utf-8")
    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": "readonly"
    }
    token_url = schwab_config.get('base_oauth_url') + schwab_config.get('token_url_add')
    print(f"Trying to refresh access token using url {token_url}")

    response = requests.post(url=token_url, headers=headers, data=data)
    if response.status_code != 200:
        logger.error(f"Error fetching access token using refresh token: HTTP {response.status_code}")
        if response.status_code == 401 or response.status_code == 400:
            logger.warning("Unauthorized request. Refresh token needs to be updated")
            return {
                "status": "UPDATE_REFRESH_TOKEN", 
                "message": "Refresh token needs to be updated.",
                "reauth_link": await get_schwab_url_for_auth_code(schwab_config)
            }
        return {"status": "CONNECTION_ERROR", "message": f"Error fetching access token using refresh token: HTTP {response.status_code}"}
    update_schwab_config("access_token", response.json().get("access_token"))
    return {"status": "SUCCESS", "message": "Access token refreshed successfully."}



async def account_update_access_token_using_refresh_token(schwab_config: dict) -> dict:
    """
    Refresh the access token using the provided refresh token.

    Returns a dict containing access_token, expires_in, and scope.
    """
    client_id = schwab_config.get("client_id_account")
    client_secret = schwab_config.get("client_secret_account")
    refresh_token = schwab_config.get("refresh_token_account")
    credentials = f"{client_id}:{client_secret}".encode("utf-8")
    basic_auth = base64.b64encode(credentials).decode("utf-8")
    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": "readonly"
    }
    token_url = schwab_config.get('base_oauth_url') + schwab_config.get('token_url_add')
    logger.info(f"Trying to refresh access token using url {token_url} for Account")

    response = requests.post(url=token_url, headers=headers, data=data)
    if response.status_code != 200:
        logger.error(f"Error fetching access token using refresh token: HTTP {response.status_code}")
        if response.status_code == 401 or response.status_code == 400:
            logger.warning("Unauthorized request. Refresh token needs to be updated for Account")
            return {
                "status": "UPDATE_REFRESH_TOKEN", 
                "message": "Refresh token needs to be updated.",
                "reauth_link": await get_schwab_url_for_auth_code_account(schwab_config)
            }
        return {"status": "CONNECTION_ERROR", "message": f"Error fetching access token using refresh token for account: HTTP {response.status_code}"}
    update_schwab_config("access_token_account", response.json().get("access_token"))
    return {"status": "SUCCESS", "message": "Access token refreshed successfully."}



async def get_schwab_url_for_auth_code(schwab_config: dict) -> str:
    """
    Generate the URL for Schwab OAuth authorization code flow.
    """
    client_id = schwab_config.get("client_id")
    redirect_uri = schwab_config.get("redirect_uri")
    auth_url = schwab_config.get('base_oauth_url') + schwab_config.get('auth_url_add')
    
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "readonly"
    }
    
    url = f"{auth_url}?{requests.compat.urlencode(params)}"
    return url


async def get_schwab_url_for_auth_code_account(schwab_config: dict) -> str:
    """
    Generate the URL for Schwab OAuth authorization code flow.
    """
    client_id = schwab_config.get("client_id_account")
    redirect_uri = schwab_config.get("redirect_uri_account")
    auth_url = schwab_config.get('base_oauth_url') + schwab_config.get('auth_url_add')
    
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "readonly"
    }
    
    url = f"{auth_url}?{requests.compat.urlencode(params)}"
    return url



async def check_schwab_connection(schwab_config: dict) -> dict:
    """
    Check if the Schwab API is reachable and the access token is valid.
    """
    access_token = schwab_config.get("access_token")
    if not access_token:
        return {"status": "NO_ACCESS_TOKEN", "message": "Access token is missing."}
    symbol = schwab_config.get("symbol", "SPY")
    check_price_response = await get_price_history(
        symbol=symbol, 
        access_token=access_token, 
        period=1, 
        frequency=1, 
        period_type="day", 
        frequency_type="minute",
        schwab_config=schwab_config,
        use_period=True
    )

    if check_price_response.status_code == 200:
        return {"status": "SUCCESS", "message": "Connection successful."}
    elif check_price_response.status_code == 401:
        logger.warning("Unauthorized request. Access token needs to be updated.")
        logger.warning("Trying to use refresh token to get new access token...")
        update_response = await update_access_token_using_refresh_token(schwab_config)
        return update_response
    else:
        logger.error("Problem with network connection")
        return {"status": "NETWORK_ERROR", "message": "Network connection issue."}


async def check_schwab_account_connection(schwab_config: dict, response) -> dict:
    """
    Check if the Schwab API is reachable and the access token is valid.
    """
    access_token_account = schwab_config.get("access_token_account")
    if not access_token_account:
        return {"status": "NO_ACCESS_TOKEN", "message": "Access token is missing."}
    symbol = schwab_config.get("symbol", "SPY")

    if response.status_code == 200:
        return {"status": "SUCCESS", "message": "Connection successful."}
    elif response.status_code == 401 or response.status_code == 400:
        logger.warning("Unauthorized request. Access token needs to be updated.")
        logger.warning("Trying to use refresh token to get new access token...")
        update_response = await account_update_access_token_using_refresh_token(schwab_config)
        return update_response
    else:
        logger.error("Problem with network connection")
        return {"status": "NETWORK_ERROR", "message": "Network connection issue."}


async def get_est_string_for_utc_time(utc_time: datetime) -> str:
    """
    Convert UTC datetime to EST string.
    """
    if utc_time.tzinfo is None:
        utc_time = utc_time.replace(tzinfo=timezone.utc)
    est_time = utc_time.astimezone(ZoneInfo("America/New_York"))
    return est_time.strftime("%Y-%m-%d %H:%M:%S")


async def get_schwab_connection_info_from_db(symbol: str) -> dict:
    """
    Get the Schwab connection information.
    """
    db: Session = SessionLocal()
    connection_info = db.query(RealtimeData).filter(RealtimeData.symbol == symbol).first()
    if not connection_info:
        return {"status": "ERROR", "message": "No RealtimeData Record found in DB."}
    time_val = connection_info.time
    realtime_sync_time = connection_info.realtime_last_sync_time
    history_sync_time = connection_info.history_last_sync_time
    time_val_str = await get_est_string_for_utc_time(time_val)
    realtime_sync_time_str = await get_est_string_for_utc_time(realtime_sync_time)
    history_sync_time_str = await get_est_string_for_utc_time(history_sync_time)
    schwab_config = get_schwab_config()
    realtime_enabled = schwab_config.get("enable_realtime", 0)
    realtime_enabled = 'True' if realtime_enabled else 'False'
    reauth_link = await get_schwab_url_for_auth_code(schwab_config)
    return {
        "status": "SUCCESS",
        "symbol": symbol,
        "last_candle_time": time_val_str,
        "last_realtime_sync": realtime_sync_time_str,
        "last_history_sync": history_sync_time_str,
        "sync_enabled": realtime_enabled,
        "reauth_link": reauth_link
    }




async def get_price_history(
        symbol: str, 
        access_token: str, 
        period: int, 
        frequency: int, 
        period_type: str = "day",
        frequency_type: str = "minute",
        start_date_time: str = "2010-01-01T00:00:00", 
        end_date_time: str = datetime.now(tz.gettz("America/New_York")).strftime("%Y-%m-%d %H:%M:%S"),
        schwab_config: dict = {},
        use_period: bool = True
    ) -> pd.DataFrame:
    """
    Fetch historical price data for a given symbol between start_date and end_date.
    Returns a DataFrame with the historical prices.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "accept": "application/json"
    }
    quote_url = schwab_config.get('market_data_url', '')
    url = f"{quote_url}/pricehistory"
    start_time_utc = to_epoch_ms_est(start_date_time)
    end_time_utc = to_epoch_ms_est(end_date_time)
    params = {
        "symbol": symbol,
        "frequencyType": frequency_type,
        "frequency": frequency,
        "needPreviousClose": True,
        "needExtendedHoursData": False
    }
    if use_period:
        params['period'] = period
        params['periodType'] = period_type
        params['endDate'] = int(time()*1000)  # Use current time as end time
    else:
        params["startDate"] = start_time_utc
        params["endDate"] = end_time_utc
        
    #print(f"params = {params} , headers = {headers}")

    response = requests.get(url=url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"Error fetching price history: HTTP {response.status_code}")
        print("Response body:", response.text)
        #response.raise_for_status()

    return response
    #return pd.DataFrame(data['candles'])

async def handle_schwab_connection_error(response, schwab_config: dict):
    logger.error(f"Error fetching real-time quote: HTTP {response.status_code}")
    logger.error("Response body: %s", response.text)
    logger.info("Trying to check and fix schwab connection...")
    connection_status = await check_schwab_connection(schwab_config)
    if connection_status.get("status", "") != "SUCCESS":
        logger.error("Not able to connect to Schwab API, message: %s", connection_status.get("message", ""))
        if connection_status.get("status", "") == "UPDATE_REFRESH_TOKEN":
            logger.error("Refresh token needs to be updated, so disabling realtime temporarily. To enable back, update in config")
            update_schwab_config("enable_realtime", 0)

async def handle_schwab_account_connection_error(response, schwab_config: dict):
    logger.error(f"Error fetching real-time account trading data: HTTP {response.status_code}")
    logger.error("Response body: %s", response.text)
    logger.info("Trying to check and fix schwab account connection...")
    connection_status = await check_schwab_account_connection(schwab_config= schwab_config, response=response)
    if connection_status.get("status", "") != "SUCCESS":
        logger.error("Not able to connect to Schwab API, message: %s", connection_status.get("message", ""))
        if connection_status.get("status", "") == "UPDATE_REFRESH_TOKEN":
            logger.error("Refresh token needs to be updated, so disabling realtime temporarily. To enable back, update in config")
            update_schwab_config("enable_realtime_account", 0)


async def get_realtime_quote(symbol: str, schwab_config: dict) -> dict:
    """
    Fetch the latest real-time quote for a given symbol.
    Returns a DataFrame with the latest quote.
    """
    access_token = schwab_config.get("access_token")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "accept": "application/json"
    }
    quote_url = schwab_config.get('market_data_url', '')
    url = f"{quote_url}/quotes"
    params = {
        "symbols": symbol
    }

    response = requests.get(url=url, headers=headers, params=params)
    if response.status_code != 200:
        await handle_schwab_connection_error(response, schwab_config)
        return None
    quote_data = response.json().get(symbol, {}).get("quote", {})
    last_price = quote_data.get("mark")
    time_data = quote_data.get("quoteTime")
    return_res = {
        "symbol": symbol,
        "price": last_price,
        "time": time_data
    }
    return return_res


async def get_realtime_price_from_db(db: Session, symbol: str):
    realtime_row = db.query(RealtimeData).filter(RealtimeData.symbol == symbol).first()
    if not realtime_row:
        return None
    price = realtime_row.price
    return price


async def parse_option_symbol(symbol: str) -> dict:
    """
    Parse Schwab-style option symbol into components.
    
    Example:
        "SPY   250807C00631000" ->
        {
            "underlying": "SPY",
            "expiration_date": "2025-08-07",
            "type": "CALL",
            "strike_price": 631.0
        }
    """
    # Trim and split underlying from the rest
    underlying = symbol[:6].strip()  # First 6 chars contain underlying padded with spaces
    date_part = symbol[6:12]         # YYMMDD
    type_part = symbol[12]           # C or P
    strike_part = symbol[13:]        # Strike price as 8 digits

    # Convert expiration date
    year = 2000 + int(date_part[0:2])
    month = int(date_part[2:4])
    day = int(date_part[4:6])
    expiration_date = f"{year:04d}-{month:02d}-{day:02d}"

    # Type mapping
    opt_type = "CALL" if type_part.upper() == "C" else "PUT"

    # Strike price conversion
    strike_price = int(int(strike_part) / 1000)  # because 00631000 → 631.000

    return {
        "underlying": underlying,
        "expiration_date": expiration_date,
        "type": opt_type,
        "strike_price": strike_price
    }



async def get_schwab_orders_df(schwab_config: dict) -> pd.DataFrame:
    """
    Fetch all Schwab orders and return as a DataFrame.
    """
    access_token_account = schwab_config.get("access_token_account")
    account_id = schwab_config.get("encrypted_account_id")
    account_url = schwab_config.get("account_data_url", "")
    headers = {
        "Authorization": f"Bearer {access_token_account}",
        "accept": "application/json"
    }
    orders_url = f"{account_url}/{account_id}/orders"
    params = {
        "maxResults": 100
    }
    response = requests.get(url=orders_url, headers=headers, params=params)
    if response.status_code != 200 or response.status_code != 201:
        await handle_schwab_account_connection_error(response, schwab_config)
        return pd.DataFrame()
    logger.info(f"Fetched {len(response.json().get('orders', []))} orders from Schwab API.")

    orders_data = response.json()
    return pd.DataFrame(orders_data)


async def sync_realtime_price_history(
        symbol: str, 
        schwab_config: dict) -> pd.DataFrame:
    db: Session = SessionLocal()
    access_token = schwab_config.get("access_token")
    periodDays = schwab_config.get("realtime_period_days", 1)
    if not access_token:
        print("Access token is missing.")
        return pd.DataFrame()
    print("Period days : ", periodDays)
    res = await get_price_history(
        symbol=symbol, 
        access_token=access_token, 
        period=periodDays, 
        frequency=1, 
        period_type="day", 
        frequency_type="minute",
        schwab_config=schwab_config,
        use_period=True
    )
    if res.status_code != 200:
        logger.error(f"Error fetching price history: HTTP {res.status_code}")
        await handle_schwab_connection_error(res, schwab_config)
        return pd.DataFrame()

    data = res.json()
    df = pd.DataFrame(data['candles'])
    df['time'] = (
        pd.to_datetime(df['datetime'], unit="ms", utc=True)
        .dt.tz_convert("America/New_York")
        .dt.strftime("%Y-%m-%d %H:%M:%S")
    )
    df['time'] = pd.to_datetime(df['time'], format="%Y-%m-%d %H:%M:%S")
    first_record_time = df['time'].iloc[0]
    logger.info(f"First record time for {symbol} is {first_record_time}")
    logger.info(f"Last record time for {symbol} is {df['time'].iloc[-1]}")
    #print("Number of rows fetched:", len(df))
    #print(df.tail())

    latest_db_time = db.query(func.max(PriceData.time)).filter(
        PriceData.symbol == symbol
    ).scalar()

    if latest_db_time:
        logger.info(f"Latest DB time for {symbol}: {latest_db_time}")
        df = df[df['time'] > latest_db_time]  # Step 3: Filter new rows only
    else:
        logger.info(f"No existing price data found for {symbol}. Inserting all candles.")
    if df.empty:
        logger.info(f"No new data to insert for {symbol}.")
        return first_record_time
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
    return first_record_time



async def round_to_next_minute(dt: datetime) -> datetime:
    """Round UTC datetime to the start of the *next* minute."""
    # Ensure it's timezone-aware UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    
    timestamp_ms = int(dt.timestamp() * 1000)  # milliseconds
    rounded_ms = (timestamp_ms // 60000) * 60000 + 60000
    return datetime.fromtimestamp(rounded_ms / 1000, tz=timezone.utc)


async def get_time_field(rt_record: RealtimeData, field: str) -> datetime:
    time_val = None
    if field == "time":
        time_val = rt_record.time
    elif field == "realtime_last_sync_time":
        time_val = rt_record.realtime_last_sync_time
    elif field == "history_last_sync_time":
        time_val = rt_record.history_last_sync_time

    if time_val is None:
        raise ValueError(f"Invalid field: {field}")
    if time_val.tzinfo is None:
        time_val = time_val.replace(tzinfo=timezone.utc)
    else:
        time_val = time_val.astimezone(timezone.utc)
    return time_val

async def should_update_time(time_val: datetime, type: str, schwab_config) -> bool:
    if type == "realtime":
        sync_frequency = schwab_config.get('realtime_schwab_sync_frequency', 20)  # Default to 20 seconds
    elif type == "history":
        sync_frequency = schwab_config.get('history_schwab_sync_frequency', 60)  # Default to 60 seconds
    else:
        raise ValueError(f"Invalid type: {type}")

    now_utc = datetime.now(timezone.utc)
    diff_seconds = (now_utc - time_val).total_seconds()
    return diff_seconds > sync_frequency


    
async def schwab_data_backend_update(symbol: str):
    """
    Background task to update Schwab data periodically.
    This function can be run as a background task in FastAPI.
    """
    logger.info("Starting Schwab data backend update...")
    inf_config = get_inf_config()
    if not inf_config['inference']['schwab'].get('enable_realtime', False):
        logger.info("Realtime data sync is disabled in the configuration.")
        return
    access_token = inf_config['inference']['schwab'].get('access_token')
    if not access_token:
        logger.error("No access token found for Schwab API.")
        return
    db: Session = SessionLocal()

    realtime_record = db.query(RealtimeData).filter(RealtimeData.symbol == symbol).first()
    if not realtime_record:
        logger.error(f"No realtime data found in the database for the symbol: {symbol}")
        return

    schwab_config = inf_config['inference']['schwab']

    realtime_last_sync_time = await get_time_field(realtime_record, "realtime_last_sync_time")
    history_last_sync_time = await get_time_field(realtime_record, "history_last_sync_time")
    if await should_update_time(realtime_last_sync_time, "realtime", schwab_config):
        logger.info("Syncing real-time data for symbol: %s", symbol)
        realtime_res = await get_realtime_quote(
            symbol=symbol,
            schwab_config=inf_config['inference']['schwab']
        )
        if not realtime_res:
            return
        schwab_time_utc = datetime.fromtimestamp(realtime_res['time'] / 1000, tz=timezone.utc)
        schwab_rounded_time = await round_to_next_minute(schwab_time_utc)
        last_time_db = await get_time_field(realtime_record, "time")
        price = realtime_res['price']
        if last_time_db != schwab_rounded_time:
            logger.info("Updating candle to next minute: %s", schwab_rounded_time)
            realtime_record.time = schwab_rounded_time
            open_price = price
            high_price = price
            low_price = price
        else:
            open_price = realtime_record.open
            high_price = max(realtime_record.high, price)
            low_price = min(realtime_record.low, price)
        
        realtime_record.open = open_price
        realtime_record.high = high_price
        realtime_record.low = low_price
        realtime_record.price = price
        realtime_record.realtime_last_sync_time = datetime.now(timezone.utc)
        db.commit()
        db.refresh(realtime_record)

    if await should_update_time(history_last_sync_time, "history", schwab_config):
        logger.info("Syncing historical data for symbol: %s", symbol)
        first_record_time = await sync_realtime_price_history(
            symbol,
            inf_config['inference']['schwab']
        ) 
        realtime_record.history_last_sync_time = datetime.now(timezone.utc)
        db.commit()
        db.refresh(realtime_record)



async def check_schwab_orders(db: Session, symbol: str):
    schwab_config = get_schwab_config()
    schwab_orders_df = await get_schwab_orders_df(schwab_config=schwab_config)

    open_schwab_orders = (
        db.query(SchwabOrders)
        .filter(
            SchwabOrders.closed == False
        )
        .all()
    )
    for order in open_schwab_orders:
        order_row = schwab_orders_df[schwab_orders_df['orderId'] == order.open_order_id]
        if not order_row.empty:
            order_row = order_row.iloc[0]
            order.open_status = order_row['status']
            
            if order_row['status'] == 'FILLED':
                option_details = await parse_option_symbol(order.symbol)
                option_type = option_details['type']
                
                logger.info(f"Order {order.open_order_id} is filled. checking condition to close order")
                current_price = await get_realtime_price_from_db(db, symbol)
                take_profit_reached = current_price > order.take_profit if option_type == "CALL" else current_price < order.take_profit
                stop_loss_reached = current_price < order.stop_loss if option_type == "CALL" else current_price > order.stop_loss
                if take_profit_reached or stop_loss_reached:
                    if stop_loss_reached:
                        
                        logger.info(f"Order {order.open_order_id} hit stop loss. Closing the order.")
                    elif take_profit_reached:
                        logger.info(f"Order {order.open_order_id} hit take profit. Closing the order.")

                order.close_time = datetime.now(timezone.utc)
                order.close_price = order_row['averagePrice']
                db.commit()
            elif order_row['status'] == 'CANCELED':
                logger.info(f"Order {order.open_order_id} is canceled. Closing the order in the database.")
                order.closed = True
                order.close_time = datetime.now(timezone.utc)
                db.commit()
        else:
            logger.warning(f"Order {order.open_order_id} not found in Schwab orders data.")



if __name__ == "__main__":
    schwab_config = get_schwab_config()
    sync_realtime_price_history(
        symbol="SPY", 
        schwab_config=schwab_config
    )