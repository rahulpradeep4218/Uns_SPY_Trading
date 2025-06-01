from sklearn.preprocessing import MinMaxScaler

def normalize_timegaps(df, time_gap_threshold=60):
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


def close_diff_transform(df, config, close_column='Close'):
    close_diff_features = config['Close_Diff_Features'].split(',')
    df[close_diff_features] = df[close_diff_features].sub(df[close_column], axis=0).div(df[close_column], axis=0)
    return df


def min_max_scaling(df, inference=True, scaler=None, config=None):
    features = config['minmax_features'].split(',')
    if not inference:
        scaler = MinMaxScaler()
        df[features] = scaler.fit_transform(df[features])
        return df, scaler
    else:
        df[features] = scaler.transform(df[features])
        return df