import base64
from operator import index
from shlex import quote
import requests
from ruamel.yaml import YAML
from datetime import datetime
import os
import pandas as pd
from dateutil import tz, parser
from app.utility.time_utilities import to_epoch_ms_est, epoch_ms_to_est
from app.db.models import PriceData
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func
import logging

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


def update_access_token_using_refresh_token(schwab_config: dict) -> dict:
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
        print(f"Error fetching access token using refresh token: HTTP {response.status_code}")
        if response.status_code == 401 or response.status_code == 400:
            print("Unauthorized request. Refresh token needs to be updated")
            return {
                "status": "UPDATE_REFRESH_TOKEN", 
                "message": "Refresh token needs to be updated.",
                "reauth_link": get_schwab_url_for_auth_code(schwab_config)
            }
        return {"status": "CONNECTION_ERROR", "message": f"Error fetching access token using refresh token: HTTP {response.status_code}"}
    update_schwab_config("access_token", response.json().get("access_token"))
    return {"status": "SUCCESS", "message": "Access token refreshed successfully."}



def get_schwab_url_for_auth_code(schwab_config: dict) -> str:
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

def check_schwab_connection(schwab_config: dict) -> dict:
    """
    Check if the Schwab API is reachable and the access token is valid.
    """
    access_token = schwab_config.get("access_token")
    if not access_token:
        return {"status": "NO_ACCESS_TOKEN", "message": "Access token is missing."}
    symbol = schwab_config.get("symbol", "SPY")
    check_price_response = get_price_history(
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
        print("Unauthorized request. Access token needs to be updated.")
        print("Trying to use refresh token to get new access token...")
        update_response = update_access_token_using_refresh_token(schwab_config)
        return update_response
    else:
        print("Problem with network connection")
        return {"status": "NETWORK_ERROR", "message": "Network connection issue."}



def get_price_history(
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
        "needPreviousClose": True
    }
    if use_period:
        params['period'] = period
        params['periodType'] = period_type
        params['endDate'] = end_time_utc
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


def get_realtime_quote(symbol: str, schwab_config: dict) -> pd.DataFrame:
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
        print(f"Error fetching real-time quote: HTTP {response.status_code}")
        print("Response body:", response.text)
        response.raise_for_status()
    quote_data = response.json().get(symbol, {}).get("quote", {})
    last_price = quote_data.get("mark")
    time_data = quote_data.get("quoteTime")
    return_res = {
        "symbol": symbol,
        "price": last_price,
        "time": time_data
    }
    return return_res


def sync_realtime_price_history(
        symbol: str, 
        schwab_config: dict) -> pd.DataFrame:
    db: Session = SessionLocal()
    access_token = schwab_config.get("access_token")
    periodDays = schwab_config.get("realtime_period_days", 1)
    if not access_token:
        print("Access token is missing.")
        return pd.DataFrame()
    print("Period days : ", periodDays)
    res = get_price_history(
        symbol=symbol, 
        access_token=access_token, 
        period=periodDays, 
        frequency=1, 
        period_type="day", 
        frequency_type="minute",
        schwab_config=schwab_config,
        use_period=True
    )

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

if __name__ == "__main__":
    schwab_config = get_schwab_config()
    sync_realtime_price_history(
        symbol="SPY", 
        schwab_config=schwab_config
    )