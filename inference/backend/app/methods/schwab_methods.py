import base64
import requests
from ruamel.yaml import YAML
from datetime import datetime, timezone, timedelta
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
import json
import math

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
        db.close()
        return {"status": "ERROR", "message": "No RealtimeData Record found in DB."}
    time_val = connection_info.time
    realtime_sync_time = connection_info.realtime_last_sync_time
    history_sync_time = connection_info.history_last_sync_time
    time_val_str = await get_est_string_for_utc_time(time_val)
    realtime_sync_time_str = await get_est_string_for_utc_time(realtime_sync_time)
    history_sync_time_str = await get_est_string_for_utc_time(history_sync_time)
    schwab_config = get_schwab_config()
    realtime_enabled = "Yes" if schwab_config.get("enable_realtime", 0) else "No"
    realtime_account_enabled = "Yes" if schwab_config.get("enable_realtime_account", 0) else "No"

    reauth_link = await get_schwab_url_for_auth_code(schwab_config)
    reauth_link_account = await get_schwab_url_for_auth_code_account(schwab_config)
    db.close()
    return {
        "status": "SUCCESS",
        "symbol": symbol,
        "last_candle_time": time_val_str,
        "last_realtime_sync": realtime_sync_time_str,
        "last_history_sync": history_sync_time_str,
        "sync_enabled": realtime_enabled,
        "sync_account_enabled": realtime_account_enabled,
        "reauth_link": reauth_link,
        "reauth_link_account": reauth_link_account
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
    return connection_status


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
        logger.error(f"No real-time data found for symbol {symbol} in the database.")
        return None
    price = realtime_row.price
    return price



async def get_option_symbol(symbol: str, option_type: str, entry_price: float, tos_config) -> str:
    # Construct the option symbol based on the underlying symbol
    position_size = tos_config.get('position_size')
    manual_exp = tos_config.get('exp_date_manual', None)
    if manual_exp:
        exp_date = datetime.strptime(manual_exp, "%Y-%m-%d")
    else:
        days_to_add = tos_config.get('exp_days_increment')
        exp_date = datetime.now() + timedelta(days=days_to_add)
        # If expiration falls on weekend, move to next Monday
        while exp_date.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            exp_date += timedelta(days=1)
    exp_date_str = exp_date.strftime("%y%m%d")  # YYMMDD format
    option_code = "C" if option_type.upper() == "CALL" else "P"
    strike_increment = tos_config.get('strike_otm_increment')

    if option_type.upper() == "CALL":
        strike_price = math.ceil(entry_price + strike_increment)
    else:  # Sell signal
        strike_price = math.floor(entry_price - strike_increment)

    # Schwab expects strike * 1000 encoded as 8 digits
    strike_thousand = int(round(strike_price * 1000))   # e.g. 631 -> 631000
    strike_field = f"{strike_thousand:08d}"                # zero-pad to 8 digits

    return f"{symbol}   {exp_date_str}{option_code}{strike_field}"



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

    def get_price(order):
        try:
            return (
                order.get("orderActivityCollection", [])[0]
                    .get("executionLegs", [])[0]
                    .get("price")
            )
        except (IndexError, AttributeError):
            return None  # or np.nan
        
    access_token_account = schwab_config.get("access_token_account")
    account_id = schwab_config.get("encrypted_account_id")
    account_url = schwab_config.get("account_data_url", "")
    headers = {
        "Authorization": f"Bearer {access_token_account}",
        "accept": "application/json"
    }
    orders_url = f"{account_url}/{account_id}/orders"
    logger.info(f"Fetching orders from Schwab API using URL: {orders_url}")
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(days=100)
    from_entered_time = from_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    to_entered_time = to_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    params = {
        "fromEnteredTime": from_entered_time,
        "toEnteredTime": to_entered_time,
        "maxResults": 100
    }
    response = requests.get(url=orders_url, headers=headers, params=params)
    if response.status_code != 200 and response.status_code != 201:
        await handle_schwab_account_connection_error(response, schwab_config)
        return pd.DataFrame()
    logger.info(f"Fetched {len(response.json())} orders from Schwab API.")

    orders_data = response.json()
    orders_data_df = pd.DataFrame(orders_data)
    orders_data_df["options_price"] = [get_price(order) for order in orders_data]
    return orders_data_df


async def sync_realtime_price_history(
        symbol: str, 
        schwab_config: dict) -> pd.DataFrame:
    db: Session = SessionLocal()
    access_token = schwab_config.get("access_token")
    periodDays = schwab_config.get("realtime_period_days", 1)
    if not access_token:
        print("Access token is missing.")
        db.close()
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
        db.close()
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
    db.close()
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
        db.close()
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
            db.close()
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
    
    db.close()


async def get_open_positions_info(schwab_config: dict, symbol: str, retries: int = 1) -> dict:
    """
    Fetch open positions for a given symbol from Schwab API.
    Returns a dict with position details.
    """
    access_token_account = schwab_config.get("access_token_account")
    account_id = schwab_config.get("encrypted_account_id")
    account_url = schwab_config.get("account_data_url", "")
    headers = {
        "Authorization": f"Bearer {access_token_account}",
        "accept": "application/json"
    }
    
    accounts_positions_url = f"{account_url}/{account_id}"
    params = {
        "fields": "positions"
    }
    
    response = requests.get(url=accounts_positions_url, headers=headers, params=params)
    
    if response.status_code != 200:
        conn_status = await handle_schwab_account_connection_error(response, schwab_config)
        if conn_status.get("status", "") != "SUCCESS":
            logger.error("Not able to connect to Schwab API for account info, message: %s", conn_status.get("message", ""))
            return {'status': 'FAILED', 'message': conn_status.get("message", "")}
        else:
            if retries <= 0:
                logger.error("Max retries reached. Unable to fetch Schwab account positions.")
                return {'status': 'FAILED', 'message': "Max retries reached. Unable to fetch Schwab account positions." }
            else:
                logger.info("Retrying to fetch Schwab account positions...")
                return await get_open_positions_info(schwab_config, symbol, retries=retries-1)

    positions_data = response.json().get('securitiesAccount', {}).get('positions', [])
    
    if len(positions_data) > 0:
        position_row = next((pos for pos in positions_data if pos['instrument']['symbol'] == symbol), None)
        if position_row:
            return {
                'symbol': symbol,
                'positions': position_row['longQuantity'],
                'profit': position_row['longOpenProfitLoss'],
                'status': 'SUCCESS'
            }
    return {
            "symbol": symbol, 
            "positions": 0,
            "profit": 0,
            "status": "SUCCESS"
        }


async def close_schwab_order_db(order_id: str, schwab_config: dict, db: Session, option_price: float, close_order_id: str = None, reason: str = ""):
    order = db.query(SchwabOrders).filter(SchwabOrders.open_order_id == order_id).first()
    cancel_reasons = schwab_config['cancel_status'].split(",")
    if order:
        order.closed = True
        current_notes = order.notes or ""
        order.close_time = datetime.now(ZoneInfo("America/New_York"))
        if reason == "FILLED":
            logger.info(f"Closing Schwab order {order_id} in the database as FILLED")
            order.close_status = "FILLED"
            order.close_order_id = close_order_id
            option_details = await parse_option_symbol(order.symbol)
            underlying_symbol = option_details['underlying']
            current_price = await get_realtime_price_from_db(db, underlying_symbol)
            order.close_price = current_price
            order.option_exit_price = option_price
            option_entry_price = order.option_entry_price
            profit = (order.option_exit_price - option_entry_price) * order.quantity * 100
            order.profit = profit
            current_notes += f"\nOrder closed as FILLED at {order.close_time} with price {current_price}."
            order.notes = current_notes
        elif reason in cancel_reasons:
            logger.info(f"Closing Schwab order {order_id} in the database as reason: {reason}")
            order.close_status = reason
            current_notes += f"\nOrder set to closed as {reason} at {order.close_time}."
            order.notes = current_notes
        
        db.commit()
        db.refresh(order)

        logger.info(f"Schwab order {order_id} closed successfully.")
    else:
        logger.error(f"Schwab order {order_id} not found.")



async def create_schwab_order(order: dict, type: str = "BUY_TO_OPEN"):
    """
    Creates a new Schwab order using Schwab API
    """
    max_tries = 2
    schwab_config = get_schwab_config()
    error_messages = ""
    for attempt in range(max_tries):
        access_token_account = schwab_config.get("access_token_account")
        account_id = schwab_config.get("encrypted_account_id")
        account_url = schwab_config.get("account_data_url", "")
        headers = {
            "Authorization": f"Bearer {access_token_account}",
            "Content-Type": "application/json"
        }

        #### If type is sell to close, then need to check if position exists
        if type == "SELL_TO_CLOSE":
            open_positions_info = await get_open_positions_info(schwab_config, order["symbol"])
            if open_positions_info.get("status", "") != "SUCCESS":
                logger.error("Failed to retrieve open positions info.")
                return {"status": "FAILED", "message": f"Failed to retrieve open positions info message: {open_positions_info.get('message', '')}"}
            if open_positions_info.get("positions", 0) < order["quantity"]:
                logger.error(f"Not enough position to sell {order['quantity']} of {order['symbol']}. Available: {open_positions_info.get('positions', 0)}")
                return {"status": "POSITION_NOT_AVAILABLE", "message": f"Not enough position to sell {order['quantity']} of {order['symbol']}. Available: {open_positions_info.get('positions', 0)}"}
        orders_url = f"{account_url}/{account_id}/orders"
        order_strategy = {
            "orderStrategyType": "SINGLE",
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderLegCollection": [
                {
                "instruction": type,
                "quantity": order["quantity"],
                    "instrument": {
                        "symbol": order["symbol"],
                        "assetType": "OPTION"
                    }
                }
            ]
        }
        response = requests.post(
                url=orders_url, 
                headers=headers, 
                data=json.dumps(order_strategy)
            )
        if response.status_code != 200 and response.status_code != 201:
            conn_status = await handle_schwab_account_connection_error(response, schwab_config)
            if conn_status.get("status", "") != "SUCCESS":
                msg = f"Not able to connect to Schwab account API, message: {conn_status.get('message', '')}, attempt: {attempt + 1}"
                logger.error(msg)
                error_messages += msg + " | \n "
                break
            else:
                logger.info("Retrying to create Schwab order...")
                continue
        else:
            logger.info(f"Successfully created Schwab order: {order['symbol']} of type {type}")

            orders_data = response.headers
            order_id = orders_data.get('Location', '').split('/')[-1]
            return {"status": "SUCCESS", "order_id": order_id}
        
    return {"status": "FAILED", "message": error_messages}




async def insert_new_schwab_order_db(symbol: str, option_type: str, db: Session, take_profit: float = 0.0, stop_loss: float = 0.0):
    current_price = await get_realtime_price_from_db(db, symbol)
    tos_config = get_inf_config()['inference']['tos']
    option_symbol = await get_option_symbol(
        symbol=symbol,
        option_type=option_type,       
        entry_price=current_price,
        tos_config=tos_config
    )
    logger.info(f"Creating new Schwab order for symbol: {symbol}, option type: {option_type}, option symbol: {option_symbol}, current price: {current_price}")
    order_dict = {
        "symbol": option_symbol,
        "quantity": tos_config.get('position_size', 1),
        "price": current_price
    }
    new_schwab_order_res = await create_schwab_order(order=order_dict, type="BUY_TO_OPEN")
    if new_schwab_order_res.get("status", "") == "SUCCESS":
        new_order_id = new_schwab_order_res.get("order_id", "")
        new_order_db = SchwabOrders(
            open_order_id=new_order_id,
            symbol=option_symbol,
            open_time=datetime.now(ZoneInfo("America/New_York")),
            quantity=tos_config.get('position_size', 1),
            take_profit=take_profit,
            stop_loss=stop_loss,
            entry_price=current_price,
            open_status="PENDING",
            profit=0.0
        )
        db.add(new_order_db)
        db.commit()
        db.refresh(new_order_db)
        return {"status": "SUCCESS", "order_id": new_order_id, "message": "Order created successfully."}
    return {
        "status": "FAILED", 
        "message": new_schwab_order_res.get("message", "Failed to create Schwab order.")
    }




async def check_schwab_orders(symbol: str):

    db: Session = SessionLocal()
    schwab_config = get_schwab_config()
    if not schwab_config['enable_realtime_account']:
        logger.info("Realtime account data sync is disabled in the configuration.")
        db.close()
        return
    cancel_statuses = schwab_config['cancel_status'].split(",")
    schwab_orders_df = await get_schwab_orders_df(schwab_config=schwab_config)
    if schwab_orders_df.empty:
        logger.info("No Schwab orders data fetched from API.")
        db.close()
        return
    else:
        logger.info(f"List of orders from schwab API : {schwab_orders_df[['orderId', 'status', 'options_price']].to_dict(orient='records')}")
    open_schwab_orders = (
        db.query(SchwabOrders)
        .filter(
            SchwabOrders.closed == False
        )
        .all()
    )
    for order in open_schwab_orders:

        order_row = schwab_orders_df[schwab_orders_df['orderId'] == int(order.open_order_id)]
        if not order_row.empty:
            order_row = order_row.iloc[0]
            #order.open_status = order_row['status']

            if order.open_status == "PENDING":
                logger.info("checking if open order is filled")
                if order_row['status'] == "FILLED":
                    logger.info(f"Open order {order.open_order_id} is filled. Updating the order in DB.")
                    order.open_status = "FILLED"
                    order.option_entry_price = float(order_row['options_price']) if pd.notna(order_row['options_price']) else 0
                    db.commit()

            elif order.close_status == "PENDING":
                close_order_row = schwab_orders_df[schwab_orders_df['orderId'] == order.close_order_id]
                if not close_order_row.empty:
                    close_order_row = close_order_row.iloc[0]
                    close_status = close_order_row['status']
                    if close_status == "FILLED":
                        logger.info(f"Close order {order.close_order_id} is filled. Updating the order in DB.")
                        await close_schwab_order_db(
                            order_id=order.id, 
                            schwab_config=schwab_config, 
                            db=db, 
                            option_price=float(order_row['options_price']) if pd.notna(order_row['options_price']) else 0, 
                            close_order_id=order.close_order_id, 
                            reason="FILLED"
                        )
                else:
                    logger.warning(f"Close order {order.close_order_id} not found in Schwab orders data.")
                    order.notes = order.notes + f"| Close order : {order.close_order_id} not found in Schwab orders data."
                    db.commit()
            
            elif order_row['status'] == 'FILLED':
                option_details = await parse_option_symbol(order.symbol)
                option_type = option_details['type']
                logger.info(f"Filled, option details : {option_details}")

                logger.info(f"Order {order.open_order_id} is filled. checking condition to close order")
                for _ in range(3):
                    current_price = await get_realtime_price_from_db(db, symbol)
                    if current_price:
                        break
                if current_price:
                    take_profit_reached = current_price > order.take_profit if option_type == "CALL" else current_price < order.take_profit
                    stop_loss_reached = current_price < order.stop_loss if option_type == "CALL" else current_price > order.stop_loss
                    logger.debug(f"Current price for {symbol} is {current_price}, take profit: {order.take_profit}, stop loss: {order.stop_loss}")
                    logger.debug(f"Take profit reached: {take_profit_reached}, Stop loss reached: {stop_loss_reached}")
                    if take_profit_reached or stop_loss_reached:
                        msg_keyword = "take profit" if take_profit_reached else "stop loss"
                        target_val = order.take_profit if take_profit_reached else order.stop_loss
                        logger.info(f"Order {order.open_order_id} hit {msg_keyword}, current price : {current_price} crossed {target_val}. Closing the order.")
                        order_dict = {
                            "symbol": order.symbol,
                            "quantity": order.quantity,
                            "price": current_price,
                        }
                        close_order_response = await create_schwab_order(order=order_dict, type="SELL_TO_CLOSE")
                        if close_order_response.get("status", "") == "SUCCESS":
                            close_order_id = close_order_response.get("order_id", "")
                            order.close_order_id = close_order_id
                            order.close_status = "PENDING"
                            order.notes = order.notes + f"| {msg_keyword.capitalize()} hit at {current_price}. Closing order with ID: {close_order_id}."                       
                            db.commit()
                        elif close_order_response.get("status", "") == "POSITION_NOT_AVAILABLE":
                            logger.info(f"As position not available to close order {order.open_order_id}, marking it closed in DB.")
                            order.close_status = "POS_NOT_AVLBL"
                            order.closed = True
                            order.close_time = datetime.now(ZoneInfo("America/New_York"))
                            order.notes = order.notes + f"| {msg_keyword.capitalize()} hit at {current_price}. But position not available to close the order. Marking it closed."                       
                            db.commit()
                        else:
                            order.notes = order.notes + "| Not able to insert a close order after " + msg_keyword + " hit, error : " + close_order_response.get("message", "")
                            db.commit()
                    
                else:
                    logger.error(f"Failed to fetch current price for symbol {symbol}. Cannot determine if order should be closed.")
                    order.notes = order.notes + "| Failed to fetch current price for symbol " + symbol + ". Cannot determine if order should be closed."
                    db.commit()

            elif order_row['status'] in cancel_statuses:
                await close_schwab_order_db(
                    order_id=order.open_order_id, 
                    schwab_config=schwab_config, 
                    db=db, 
                    option_price=0, 
                    reason=order_row['status']
                )
        else:
            logger.warning(f"Order {order.open_order_id} not found in Schwab orders data.")
    db.close()



if __name__ == "__main__":
    schwab_config = get_schwab_config()
    sync_realtime_price_history(
        symbol="SPY", 
        schwab_config=schwab_config
    )