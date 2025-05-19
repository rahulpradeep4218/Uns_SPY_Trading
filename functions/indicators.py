import talib
import numpy as np

def add_all_indicators(data, config):
    """
    Add all indicators to the data DataFrame.
    Args:
        data (pd.DataFrame): DataFrame containing the stock data.
        config (dict): Configuration dictionary containing indicator parameters.
    Returns:
        pd.DataFrame: DataFrame with added indicators.
    """
    data = add_bollinger_bands(data, config)
    data = add_donchian_bands(data, config)
    return data

def add_bollinger_bands(data, config):
    config = config['bolband']
    bolband_period = config['bolband_period']
    bolband_width = config['bolband_width']
    upper, middle, lower = talib.BBANDS(data['Close'], timeperiod=bolband_period, nbdevup=bolband_width, nbdevdn=bolband_width, matype=0)
    data['BOLLBU'] = upper
    data['BOLLBL'] = lower
    return data

def add_donchian_bands(data, config):
    config = config['donchn']
    donchn_period = config['donchn_period']
    data['DONUP'] = talib.MAX(data['High'], timeperiod=donchn_period)
    data['DONLOW'] = talib.MIN(data['Low'], timeperiod=donchn_period)
    return data


def compute_fourier_df(df, config):
    period = config['fourier_period']
    n_components = (period - 2) // 2 
    for i in range(n_components):
        df[f'fourier_real_{i+1}'] = np.nan
        df[f'fourier_imag_{i+1}'] = np.nan
    
    for i in range(len(df)):
        if i >= period - 1:
            #print("entered point 1")
            close_window = df['Close'].iloc[i - period + 1: i + 1].values
            fft_result = np.fft.fft(close_window)
            real = fft_result.real
            imag = fft_result.imag

            for j in range(1, n_components+1):
                df.iloc[i, df.columns.get_loc(f'fourier_real_{j}')] = real[j]
                df.iloc[i, df.columns.get_loc(f'fourier_imag_{j}')] = imag[j]
    return df


def calculate_tchr(data, config):
    period = config['tchr_period']
    retracement = config['tchr_retracement']
    adj = config['tchr_adj']
    range = config['tchr_range']

    if range == 'highlow':
        data['TCHR_U'] = talib.MAX(data['High'], timeperiod=period) + adj
        data['TCHR_L'] = talib.MIN(data['Low'], timeperiod=period) - adj
    elif range == 'close':
        data['TCHR_U'] = talib.MAX(data['Close'], timeperiod=period) + adj
        data['TCHR_L'] = talib.MIN(data['Close'], timeperiod=period) - adj
    
    #calculate retracement
    if retracement == "long":
        data['TCHR'] = (data['Close'] - data['TCHR_L']) / (data['TCHR_U'] - data['TCHR_L'])
    elif retracement == "short":
        data['TCHR'] = (data['TCHR_U'] - data['Close']) / (data['TCHR_U'] - data['TCHR_L'])
    data.drop(['TCHR_U', 'TCHR_L'], axis=1, inplace=True)
    return data


def calculate_ATR(data, config):
    atr_period = config['atr_period']
    atr_ma = config['atr_ma']
    data['ATR'] = talib.ATR(data['High'], data['Low'], data['Close'], timeperiod=atr_period)
    data['ADJATR'] = talib.SMA(data['ATR'], timeperiod=atr_ma)
    return data


def compute_volatility_momentum(df, price_col='Close', vol_window=14, mom_window=10):
    """
    Computes rolling volatility and momentum for a given price column.

    Parameters:
        df (pd.DataFrame): DataFrame containing historical price data.
        price_col (str): Column name of the closing price.
        vol_window (int): Window size for rolling volatility calculation.
        mom_window (int): Window size for momentum calculation.

    Returns:
        pd.DataFrame: DataFrame with added 'Volatility' and 'Momentum' features.
    """

    # Ensure price column exists
    if price_col not in df.columns:
        raise ValueError(f"Column '{price_col}' not found in DataFrame")

    # 🔹 Compute Log Returns (for better volatility calculation)
    df['Log_Returns'] = np.log(df[price_col] / df[price_col].shift(1))

    # 🔹 Compute Rolling Volatility (Standard Deviation of Log Returns)
    df['Volatility'] = df['Log_Returns'].rolling(window=vol_window).std()

    # 🔹 Compute Momentum (Rate of Change in Price)
    df['Momentum'] = df[price_col].pct_change(periods=mom_window) * 100

    # 🔹 Drop NaN values from rolling computations
    #df.dropna(inplace=True)
    df.drop(columns=['Log_Returns'], inplace=True)  # Drop Log Returns if not needed
    
    return df


def add_MA(data, config, column='Close'):
    ma_periods = config['ma_periods']
    for ma_period in ma_periods:
        data[f'MA{ma_period}'] = talib.SMA(data['Close'], timeperiod=ma_period)
    return data

def add_EMA(data, config, column='Close'):
    ema_periods = config['ema_periods']
    for ema_period in ema_periods:
        data[f'EMA{ema_period}'] = talib.EMA(data['Close'], timeperiod=ema_period)
    return data

def add_pivot(data):
    data['PVPT'] = (data['High'] + data['Low'] + data['Close']) / 3
    data['PVPTR1'] = (2 * data['PVPT']) - data['Low']
    data['PVPTR2'] = data['PVPT'] + data['High'] - data['Low']
    data['PVPTR3'] = data['High'] + 2 * (data['PVPT'] - data['Low'])
    data['PVPTS1'] = (2 * data['PVPT']) - data['High']
    data['PVPTS2'] = data['PVPT'] - (data['High'] - data['Low'])
    data['PVPTS3'] = data['Low'] - 2 * (data['High'] - data['PVPT'])