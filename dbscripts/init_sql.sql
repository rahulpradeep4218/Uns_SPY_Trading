-- Step 2a: Create 'trades' table (parent)
CREATE TABLE IF NOT EXISTS trade_sessions (
    id SERIAL PRIMARY KEY,
    type VARCHAR(20) CHECK (type IN ('Realtime', 'Simulated')) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    trade_start TIMESTAMP NOT NULL,
    trade_end TIMESTAMP NOT NULL,
    model_high_version INTEGER,
    model_high_alias VARCHAR(50),
    model_low_version INTEGER,
    model_low_alias VARCHAR(50)
);

-- Step 2b: Create 'trade_events' table (child)
CREATE TABLE IF NOT EXISTS trade_records(
    session_id INTEGER REFERENCES trade_sessions(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    trade_time TIMESTAMP NOT NULL,
    PRIMARY KEY (session_id, symbol, trade_time),
    high_val NUMERIC(12, 4),
    low_val NUMERIC(12, 4),
    signal INTEGER,
    realized BOOLEAN,
    entry_price NUMERIC(12, 4),
    exit_price NUMERIC(12, 4),
    profit NUMERIC(12, 2)
);

CREATE TABLE IF NOT EXISTS price_data(
    symbol VARCHAR(10) NOT NULL,
    time TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, time),
    high NUMERIC(12, 4),
    low NUMERIC(12, 4),
    open NUMERIC(12, 4),
    close NUMERIC(12, 4),
    volume BIGINT
);