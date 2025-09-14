from sklearn.preprocessing import MinMaxScaler
from trading_functions.training.utility import get_columns_mapping

def normalize_timegaps(df, config):
    cfg = config['common_config']
    time_gap_threshold = cfg['normalize_timegap_threshold']
    df = df.copy()
    features = ['Open', 'High', 'Low', 'Close']

    # Compute time differences
    df['time_delta'] = df['Date'].diff().dt.total_seconds()
    df['time_delta'] = df['time_delta'].fillna(df['time_delta'].median())

    # Identify time gaps
    df['time_gap_flag'] = df['time_delta'] > time_gap_threshold
    gap_indices = df.index[df['time_gap_flag']].tolist()

    adjustment_factor = 1.0

    # Process backward: from newest to oldest
    for p in reversed(gap_indices):
        if p < len(df) - 1:  # ensure p+1 exists
            next_open = df.loc[p + 1, 'Open']
            this_close = df.loc[p, 'Close']
            gap_percentage = next_open / this_close

            adjustment_factor *= gap_percentage

            # Apply scaling to rows before p+1 (older data)
            df.loc[p + 1:, features] /= gap_percentage

    df.drop(columns=['time_delta', 'time_gap_flag'], inplace=True)
    return df

def normalize_timegaps_inference(df, config):
    cfg = config['common_config']
    time_gap_threshold = cfg['normalize_timegap_threshold']
    df = df.copy()
    features = ['Open', 'High', 'Low', 'Close']

    df['time_delta'] = df['Date'].diff().dt.total_seconds()
    df['time_delta'] = df['time_delta'].fillna(df['time_delta'].median())

    df['time_gap_flag'] = df['time_delta'] > time_gap_threshold
    gap_indices = df.index[df['time_gap_flag']].tolist()

    adjustment_factor = 1.0

    # Process forward: from oldest to newest
    for p in gap_indices:
        if p > 0:  # ensure p-1 exists
            prev_close = df.loc[p - 1, 'Close']
            this_open = df.loc[p, 'Open']
            gap_percentage = this_open / prev_close

            adjustment_factor *= gap_percentage

            # Apply scaling to rows before p (older data)
            df.loc[:p - 1, features] /= gap_percentage

    df.drop(columns=['time_delta', 'time_gap_flag'], inplace=True)
    return df


def close_diff_transform(df, config):
    cfg = config['common_config']
    #close_diff_features = cfg['close_transform_columns'].split(',')
    close_diff_features = get_columns_mapping(cfg['close_transform_columns'], config)
    #print(f"Applying close difference transformation on features: {close_diff_features}")
    # Transform the 'Close' column
    df[close_diff_features] = df[close_diff_features].sub(df['Close'], axis=0).div(df['Close'], axis=0)
    return df, close_diff_features


def min_max_scaling(df, inference=True, scaler=None, config=None):
    features = config['minmax_features'].split(',')
    if not inference:
        scaler = MinMaxScaler()
        df[features] = scaler.fit_transform(df[features])
        return df, scaler
    else:
        df[features] = scaler.transform(df[features])
        return df