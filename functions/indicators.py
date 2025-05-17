import talib

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
    bolband_period = config['bolband_period']
    bolband_width = config['bolband_width']
    upper, middle, lower = talib.BBANDS(data['Close'], timeperiod=bolband_period, nbdevup=bolband_width, nbdevdn=bolband_width, matype=0)
    data['BOLLBU'] = upper
    data['BOLLBL'] = lower
    return data

def add_donchian_bands(data, config):
    donchn_period = config['donchn_period']
    data['DONUP'] = talib.MAX(data['High'], timeperiod=donchn_period)
    data['DONLOW'] = talib.MIN(data['Low'], timeperiod=donchn_period)
    return data