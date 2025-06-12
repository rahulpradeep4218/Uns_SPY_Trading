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
    cfg = config['indicators']
    selected_indicators = cfg['selected'].split(",")
    ma_periods = [int(maperiod[3:]) for maperiod in selected_indicators if maperiod.startswith('ma_')]
    ema_periods = [int(maperiod[4:]) for maperiod in selected_indicators if maperiod.startswith('ema_')]
    cfg_parameters = cfg['parameters']
    # Add all indicators to the data
    func_list = []
    if len(ma_periods) > 0:
        func_list.append(cfg['functions']['ma'])
        cfg_parameters['ma_periods'] = ma_periods
    if len(ema_periods) > 0:
        func_list.append(cfg['functions']['ema'])
        cfg_parameters['ema_periods'] = ema_periods
    rest_functions = [cfg['functions'][indicator] for indicator in selected_indicators if not indicator.startswith(('ma_', 'ema_')) ]
    func_list.extend(rest_functions)

    if func_list:
        for func_name in func_list:
            func = globals().get(func_name)
            if callable(func):
                data = func(data=data, config=cfg['parameters'], column=cfg['indicator_column'])
            else:
                print(f"Function {func_name} is not found or not callable")
    else:
        print("No function list provided, adding all indicators.")
    data.dropna(inplace=True)  # Drop rows with NaN values after adding indicators
    return data, selected_indicators



def add_bollinger_bands(data, config, column='Close'):
    config = config['bolband']
    bolband_period = config['period']
    bolband_width = config['width']
    upper, middle, lower = talib.BBANDS(data[column], timeperiod=bolband_period, nbdevup=bolband_width, nbdevdn=bolband_width, matype=0)
    data['BOLLBU'] = upper
    data['BOLLBL'] = lower
    return data

def add_donchian_bands(data, config, column='Close'):
    config = config['donchn']
    donchn_period = config['period']
    data['DONUP'] = talib.MAX(data['High'], timeperiod=donchn_period)
    data['DONLOW'] = talib.MIN(data['Low'], timeperiod=donchn_period)
    return data


def compute_fourier_df(data, config, column='Close'):
    config = config['fourier']
    period = config['period']
    n_components = (period - 2) // 2 
    for i in range(n_components):
        data[f'fourier_real_{i+1}'] = np.nan
        data[f'fourier_imag_{i+1}'] = np.nan
    
    for i in range(len(data)):
        if i >= period - 1:
            #print("entered point 1")
            close_window = data['Close'].iloc[i - period + 1: i + 1].values
            fft_result = np.fft.fft(close_window)
            real = fft_result.real
            imag = fft_result.imag

            for j in range(1, n_components+1):
                data.iloc[i, data.columns.get_loc(f'fourier_real_{j}')] = real[j]
                data.iloc[i, data.columns.get_loc(f'fourier_imag_{j}')] = imag[j]
    return data


def calculate_tchr(data, config, column='Close'):
    config = config['tchr']
    period = config['period']
    retracement = config['retracement']
    adj = config['adj']
    range = config['range']

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


def calculate_ATR(data, config, column='Close'):
    config = config['atr']
    atr_period = config['period']
    atr_ma = config['ma']
    data['ATR'] = talib.ATR(data['High'], data['Low'], data['Close'], timeperiod=atr_period)
    data['ADJATR'] = talib.SMA(data['ATR'], timeperiod=atr_ma)
    return data


def add_volatility(data, config, column='Close'):
    config = config['volatility']
    vol_window = config['window']
    # Ensure price column exists
    if column not in data.columns:
        raise ValueError(f"Column '{column}' not found in DataFrame")

    # 🔹 Compute Log Returns (for better volatility calculation)
    data['Log_Returns'] = np.log(data[column] / data[column].shift(1))

    # 🔹 Compute Rolling Volatility (Standard Deviation of Log Returns)
    data['Volatility'] = data['Log_Returns'].rolling(window=vol_window).std()

    # 🔹 Drop NaN values from rolling computations
    #data.dropna(inplace=True)
    data.drop(columns=['Log_Returns'], inplace=True)  # Drop Log Returns if not needed
    return data


def add_momentum(data, config, column='Close'):
    config = config['momentum']
    mom_window = config['window']
    data['Momentum'] = data[column].pct_change(periods=mom_window) * 100
    return data

def add_MA(data, config, column='Close'):
    ma_periods = config['ma_periods']
    for ma_period in ma_periods:
        data[f'MA{ma_period}'] = talib.SMA(data[column], timeperiod=ma_period)
    return data

def add_EMA(data, config, column='Close'):
    ema_periods = config['ema_periods']
    for ema_period in ema_periods:
        data[f'EMA{ema_period}'] = talib.EMA(data[column], timeperiod=ema_period)
    return data

def add_pivot(data, config, column='Close'):
    data['PVPT'] = (data['High'] + data['Low'] + data['Close']) / 3
    data['PVPTR1'] = (2 * data['PVPT']) - data['Low']
    data['PVPTR2'] = data['PVPT'] + data['High'] - data['Low']
    data['PVPTR3'] = data['High'] + 2 * (data['PVPT'] - data['Low'])
    data['PVPTS1'] = (2 * data['PVPT']) - data['High']
    data['PVPTS2'] = data['PVPT'] - (data['High'] - data['Low'])
    data['PVPTS3'] = data['Low'] - 2 * (data['High'] - data['PVPT'])
    return data