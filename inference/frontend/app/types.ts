export interface TradeSession {    
    id?: number,
    type?: string,
    symbol: string,
    trade_start?: string | Date,
    trade_end?: string | Date,
    model_high_version?: number,
    model_high_alias?: string,
    model_low_version?: number,
    model_low_alias?: string,
}

export interface TradeRecord {
    trade_time: string | Date;
    entry_price: number;
    high_val: number;
    low_val: number;
    buy_take_profit: number;
    buy_stop_loss: number;
    sell_take_profit: number;
    sell_stop_loss: number;
    calc_stop_loss: number; // Calculated stop loss
    calc_take_profit: number; // Calculated take profit
    signal: number;
    profit: number;
    status: string; 
    exit_reason: string;

}

export interface TradeStats {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    winning_percentage: number;
    average_profit: number;
    total_profit: number;
    unrealized_profit: number;
    percent_complete: number;
}

export interface SimulationOptions {
    close_at_eod?: boolean;
    max_hold_time?: number;
    sl_type?: "percent" | "abs" | "model";
    sl_value?: number;
    tp_type?: "abs" | "model";
    tp_value?: number;
    max_gap_days_allowed?: number;
    sell_or_buy_threshold?: number;
    risk_threshold?: number;
    allow_multiple_open_trades?: boolean;
    close_using_signal?: boolean;
    speed?: number;
}

export interface SimulationOptionsFormProps {
    onSubmit: (options: SimulationOptions) => void;
    initialValues?: Partial<SimulationOptions>;
}

export type TradeSignalOverlay = {
    time: Date;
    signal: -1 | 1;
    price: number;
    stop_loss: number;
    take_profit: number;
};

export type OHLCDataPoint = {
    time: Date;
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
}