WITH constants AS (
    SELECT
        2.0 AS sell_or_buy_threshold,
        2.0 AS risk_threshold
),
computed AS (
    SELECT 
        t.trade_time,
        t.session_id,
        t.buy_take_profit,
        t.sell_take_profit,
        t.buy_stop_loss,
        t.sell_stop_loss,
        p.close AS current_close,

        -- Diffs
        t.buy_take_profit - p.close AS buy_diff,
        p.close - t.sell_take_profit AS sell_diff,

        -- Risk Ratios
        CASE
            WHEN (t.buy_take_profit - p.close) != 0
            THEN (p.close - t.buy_stop_loss) / (t.buy_take_profit - p.close)
            ELSE 0
        END AS buy_risk_ratio,

        CASE
            WHEN (p.close - t.sell_take_profit) != 0
            THEN (t.sell_stop_loss - p.close) / (p.close - t.sell_take_profit)
            ELSE 0
        END AS sell_risk_ratio,

        -- Diff Ratios
        CASE
            WHEN (t.buy_take_profit - p.close) != 0
            THEN (p.close - t.sell_take_profit) / (t.buy_take_profit - p.close)
            ELSE 0
        END AS sell_buy_ratio,

        CASE
            WHEN (p.close - t.sell_take_profit) != 0
            THEN (t.buy_take_profit - p.close) / (p.close - t.sell_take_profit)
            ELSE 0
        END AS buy_sell_ratio
    FROM 
        public.trade_records AS t
    INNER JOIN 
        public.price_data AS p 
        ON t.trade_time = p.time
)

SELECT 
    c.trade_time,
    c.buy_diff,
    c.sell_diff,
    c.buy_risk_ratio,
    c.sell_risk_ratio,
    c.buy_sell_ratio,
    c.sell_buy_ratio,

    CASE 
        WHEN c.buy_sell_ratio > consts.sell_or_buy_threshold 
             AND c.buy_risk_ratio < consts.risk_threshold 
        THEN true ELSE false 
    END AS buy_signal,

    CASE 
        WHEN c.sell_buy_ratio > consts.sell_or_buy_threshold 
             AND c.sell_risk_ratio < consts.risk_threshold 
        THEN true ELSE false 
    END AS sell_signal

FROM 
    computed AS c
CROSS JOIN 
    constants AS consts
WHERE 
    c.session_id = 2
ORDER BY 
    buy_signal DESC;
