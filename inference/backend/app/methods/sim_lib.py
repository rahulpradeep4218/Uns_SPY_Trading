from sqlalchemy.exc import IntegrityError
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any
from datetime import timedelta
from sqlalchemy import desc
from trading_functions.db.schemas import SimulationOptions
from trading_functions.db.models import TradeSession, TradeRecord, PriceData
from sqlalchemy.orm import Session
from trading_functions.inference.inf_functions import (
    get_maximum_period,
    get_prediction
)

import pandas as pd
import logging
logger = logging.getLogger(__name__)

class SimulationManager:
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: int):
        await websocket.accept()
        self.active_connections[session_id] = websocket

    def disconnect(self, session_id: int):
        if session_id in self.active_connections:
            del self.active_connections[session_id]

    async def send_message(self, session_id: int, message: Dict[str, Any]):
        if session_id in self.active_connections:
            websocket = self.active_connections[session_id]
            try:
                await websocket.send_json(message)
            except WebSocketDisconnect:
                self.disconnect(session_id)
        else:
            print(f"No active connection for session {session_id}")

async def get_prediction_for_candle(
    db: Session,
    session: TradeSession,
    current_candle: PriceData,
    training_config,
    SimulationOptions: SimulationOptions,
    model_high: Any,
    model_low: Any,
    scalers: Dict[str, Any]
):
    max_period = get_maximum_period(training_config)
    
    candles_query = db.query(PriceData).filter(
        PriceData.symbol == session.symbol,
        PriceData.time <= current_candle.time
    ).order_by(desc(PriceData.time)).limit(max_period)

    # Convert to pandas series (Columns)
    candles_columns = candles_query.all()
    if len(candles_columns) < max_period:
        return {"status": "NO_ENOUGH_LAGGING_DATA",
                "message": f"Not enough lagging data for symbol {session.symbol} to run simulation."
               }
    gap = current_candle.time - candles_columns[-1].time
    if gap > timedelta(days=SimulationOptions.max_gap_days_allowed):
        return {"status": "LAGGING_DATA_GAP_TOO_LARGE",
                "message": f"Current candle time {current_candle.time} is more than {SimulationOptions.max_gap_days_allowed} of the last lagging candle using max period : {max_period} ,  {candles_columns[-1].time} for symbol {session.symbol}."
               }

    data = pd.DataFrame([
        {
            "Date": candle.time,
            "Open": candle.open,
            "High": candle.high,
            "Low": candle.low,
            "Close": candle.close,
            "Volume": candle.volume
        } for candle in candles_columns
    ])

    pred_dict = get_prediction(
        data=data,
        model_high=model_high,
        model_low=model_low,
        training_config=training_config,
        scalers=scalers
    )
    buy_take, sell_take, buy_stop, sell_stop = float(pred_dict["buy_take"]), float(pred_dict["sell_take"]), float(pred_dict["buy_stop"]), float(pred_dict["sell_stop"])
    current_close = current_candle.close
    sell_or_buy_threshold = SimulationOptions.sell_or_buy_threshold
    risk_threshold = SimulationOptions.risk_threshold

    buy_diff = buy_take - current_close
    sell_diff = current_close - sell_take

    buy_risk = current_close - buy_stop
    sell_risk = sell_stop - current_close

    # --- Risk Ratios (unchanged logic, just safe divide) ---
    buy_risk_ratio = buy_risk / buy_diff if buy_diff != 0 else 0
    sell_risk_ratio = sell_risk / sell_diff if sell_diff != 0 else 0

    # --- Sell/Buy Ratio with bearish boost & denominator smoothing ---
    if buy_diff < 0:
        # If buy TP is below price (bearish), boost sell signal
        sell_buy_ratio = (abs(buy_diff) + 1) * sell_diff
    else:
        # Otherwise, calculate normally but smooth denominator with +1
        sell_buy_ratio = sell_diff / (buy_diff + 1) if buy_diff != 0 else 0

    # --- Buy/Sell Ratio with bullish boost & denominator smoothing ---
    if sell_diff < 0:
        # If sell TP is above price (bullish), boost buy signal
        buy_sell_ratio = (abs(sell_diff) + 1) * buy_diff
    else:
        # Otherwise, calculate normally but smooth denominator with +1
        buy_sell_ratio = buy_diff / (sell_diff + 1) if sell_diff != 0 else 0

    # --- Final Signals ---
    buy_signal = buy_sell_ratio > sell_or_buy_threshold and buy_sell_ratio > sell_buy_ratio and buy_risk_ratio < risk_threshold
    sell_signal = sell_buy_ratio > sell_or_buy_threshold and sell_buy_ratio > buy_sell_ratio and sell_risk_ratio < risk_threshold

    signal = 1 if buy_signal else -1 if sell_signal else 0

    return {
        "status": "OK",
        "buy_take": buy_take,
        "sell_take": sell_take,
        "buy_stop": buy_stop,
        "sell_stop": sell_stop,
        "signal": signal,
        "current_close": current_close,
    }

def calculate_atr(db: Session, symbol: str, atr_period: int, current_candle: PriceData):
    candles = (
        db.query(PriceData).filter(
        PriceData.symbol == symbol,
        PriceData.time <= current_candle.time
        ).order_by(desc(PriceData.time)
        ).limit(atr_period + 1).all()
    )

    if len(candles) < 2:
        return None
    
    candles = list(reversed(candles))  # Reverse to have oldest first
    trs = []
    for i in range(1, len(candles)):
        high = candles[i].high
        low = candles[i].low
        prev_close = candles[i - 1].close
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    atr = sum(trs[-atr_period:]) / atr_period if len(trs) >= atr_period else None
    return atr

async def create_trade_for_candle(
    db: Session,
    session: TradeSession,
    current_candle: PriceData,
    SimulationOptions: SimulationOptions,
    pred_dict: Dict[str, Any],
    isRealtime: bool = False,
    inf_config: Dict[str, Any] = {}
    ):

    buy_take = pred_dict["buy_take"]
    sell_take = pred_dict["sell_take"]
    buy_stop = pred_dict["buy_stop"]
    sell_stop = pred_dict["sell_stop"]  
    signal = pred_dict["signal"]  
    current_close = current_candle.close
    end_of_day_cutoff_hour = inf_config.get("inference").get("end_of_day_cutoff_hour", 15)
    end_of_day_cutoff_minute = inf_config.get("inference").get("end_of_day_cutoff_minute", 40)
    if current_candle.time.hour >= end_of_day_cutoff_hour and current_candle.time.minute >= end_of_day_cutoff_minute:
        cutoff_passed = True
    else:
        cutoff_passed = False

    def open_trade_or_not():
        
        if signal != 0 and not SimulationOptions.allow_multiple_open_trades:
            existing_trade = db.query(TradeRecord).filter(
                TradeRecord.session_id == session.id,
                TradeRecord.status == "OPEN"
            ).first()
            if existing_trade:
                return False
            return True
        elif SimulationOptions.allow_multiple_open_trades and signal != 0:
            return True
        return False
    
    open_trade = True if isRealtime else open_trade_or_not()
    if open_trade and signal != 0 and not cutoff_passed:
        status = "OPEN"
        entry_price = current_close
    else:
        status = "SIGNAL"
        entry_price = None
    if status != "SIGNAL":
        if SimulationOptions.sl_type == "atr" or SimulationOptions.tp_type == "atr":
            atr_period = inf_config.get("inference").get("atr", {}).get("period", 0)
            atr_value = calculate_atr(
                db=db,
                symbol=session.symbol,
                atr_period=atr_period,
                current_candle=current_candle
            )

        # Calculate calc_stop_loss
        if SimulationOptions.sl_type == "abs" and SimulationOptions.sl_value is not None:
            calc_stop_loss = entry_price - SimulationOptions.sl_value if signal == 1 else entry_price + SimulationOptions.sl_value
        elif SimulationOptions.sl_type == "percent" and SimulationOptions.sl_value is not None:
            calc_stop_loss = entry_price - ((buy_take - entry_price) * SimulationOptions.sl_value) if signal == 1 else entry_price + ((entry_price - sell_take) * SimulationOptions.sl_value)
        elif SimulationOptions.sl_type == "atr" and atr_value is not None:
            sl_multiplier = inf_config.get("inference").get("atr", {}).get("sl_multiplier", 1.5)
            calc_stop_loss = entry_price - (atr_value * sl_multiplier) if signal == 1 else entry_price + (atr_value * sl_multiplier)
        else:
            calc_stop_loss = sell_stop if signal == -1 else buy_stop

        # Calculate calc_take_profit
        if SimulationOptions.tp_type == "abs" and SimulationOptions.tp_value is not None:
            logger.info(f"Using fixed TP value : {SimulationOptions.tp_value}, signal: {signal}")
            calc_take_profit = entry_price + SimulationOptions.tp_value if signal == 1 else entry_price - SimulationOptions.tp_value
        elif SimulationOptions.tp_type == "atr" and atr_value is not None:
            tp_multiplier = inf_config.get("inference").get("atr", {}).get("tp_multiplier", 2.5)
            calc_take_profit = entry_price + (atr_value * tp_multiplier) if signal == 1 else entry_price - (atr_value * tp_multiplier)
        else:
            logger.info(f"Using dynamic TP values, buy_take: {buy_take}, sell_take: {sell_take}, signal: {signal}")
            calc_take_profit = buy_take if signal == 1 else sell_take
    else:
        calc_stop_loss = None
        calc_take_profit = None

    new_trade_record = TradeRecord(
        session_id=session.id,
        symbol=session.symbol,
        trade_time=current_candle.time,
        high_val=current_candle.high,
        low_val=current_candle.low,
        signal=signal,
        status=status,
        entry_price=entry_price,
        buy_stop_loss=buy_stop,
        buy_take_profit=buy_take,
        sell_stop_loss=sell_stop,
        sell_take_profit=sell_take,
        profit=0.0,
        calc_stop_loss=calc_stop_loss,
        calc_take_profit=calc_take_profit,
        exit_reason=None  # This will be updated later if the trade is closed
    )
    try:
        db.add(new_trade_record)
        db.commit()
        db.refresh(new_trade_record)
    except IntegrityError as e:
        db.rollback()
        print("Duplicate trade record detected, updating existing record.")
        db.merge(new_trade_record)
        db.commit()
        print(f"Updated existing record for session {session.id} and symbol {session.symbol} at time {current_candle.time}")

    return new_trade_record

async def check_trade_exit(
    trade: TradeRecord,
    current_candle: PriceData,
    SimulationOptions: SimulationOptions,
    current_signal: int = 0
):
    current_close = current_candle.close
    calc_stop_loss = trade.calc_stop_loss
    calc_take_profit = trade.calc_take_profit
    if trade.signal == 1:
        
        # if SimulationOptions.tp_type == "fixed" and SimulationOptions.tp_value is not None:
        #     calc_take_profit = trade.entry_price + SimulationOptions.tp_value
        # else:
        #     calc_take_profit = trade.buy_take_profit

        # if SimulationOptions.sl_type == "fixed" and SimulationOptions.sl_value is not None:
        #     calc_stop_loss = trade.entry_price - SimulationOptions.sl_value
        # elif SimulationOptions.sl_type == "percent" and SimulationOptions.sl_value is not None:
        #     calc_stop_loss = trade.entry_price - (( calc_take_profit - trade.entry_price) * SimulationOptions.sl_value)
        # else:
        #     calc_stop_loss = trade.buy_stop_loss
        
        if current_candle.low <= calc_stop_loss:
            trade.profit = calc_stop_loss - trade.entry_price
            trade.status = "CLOSED"
            trade.exit_price = calc_stop_loss
            trade.exit_reason = "STOP_LOSS"
        elif current_candle.high >= calc_take_profit:
            trade.profit = calc_take_profit - trade.entry_price
            trade.status = "CLOSED"
            trade.exit_price = calc_take_profit
            trade.exit_reason = "TAKE_PROFIT"
        elif SimulationOptions.close_using_signal and current_signal == -1:
            trade.profit = current_close - trade.entry_price
            trade.status = "CLOSED"
            trade.exit_price = current_close
            trade.exit_reason = "OPPOSITE_SIGNAL"
        elif trade.trade_time + timedelta(minutes=SimulationOptions.max_hold_time) < current_candle.time:
            trade.profit = current_close - trade.entry_price
            trade.status = "CLOSED"
            trade.exit_price = current_close
            trade.exit_reason = "MAX_HOLD_TIME"
        # Check if End of day reached
        elif current_candle.time.hour >= 15 and current_candle.time.minute >= 40 and SimulationOptions.close_at_eod:
            trade.profit = current_close - trade.entry_price
            trade.status = "CLOSED"
            trade.exit_price = current_close
            trade.exit_reason = "END_OF_DAY"
        else:
            trade.profit = current_close - trade.entry_price

    elif trade.signal == -1:

        if current_candle.high >= calc_stop_loss:
            trade.profit = trade.entry_price - calc_stop_loss
            trade.status = "CLOSED"
            trade.exit_price = calc_stop_loss
            trade.exit_reason = "STOP_LOSS"
        elif current_candle.low <= calc_take_profit:
            trade.profit = trade.entry_price - calc_take_profit
            trade.status = "CLOSED"
            trade.exit_price = calc_take_profit
            trade.exit_reason = "TAKE_PROFIT"
        elif SimulationOptions.close_using_signal and current_signal == 1:
            trade.profit = trade.entry_price - current_close
            trade.status = "CLOSED"
            trade.exit_price = current_close
            trade.exit_reason = "OPPOSITE_SIGNAL"
        elif trade.trade_time + timedelta(minutes=SimulationOptions.max_hold_time) < current_candle.time:
            trade.profit = trade.entry_price - current_close
            trade.status = "CLOSED"
            trade.exit_price = current_close
            trade.exit_reason = "MAX_HOLD_TIME"
        elif current_candle.time.hour >= 15 and current_candle.time.minute >= 40 and SimulationOptions.close_at_eod:
            trade.profit = current_close - trade.entry_price
            trade.status = "CLOSED"
            trade.exit_price = current_close
            trade.exit_reason = "END_OF_DAY"
        else:
            trade.profit = trade.entry_price - current_close
    return trade.status
    

async def run_simulation_one_candle(
        db: Session, 
        session: TradeSession, 
        training_config, 
        current_candle: PriceData, 
        SimulationOptions: SimulationOptions,
        model_high: Any,
        model_low: Any,
        scalers: Dict[str, Any],
        inf_config: Dict[str, Any] = {}
):
    pred_dict = await get_prediction_for_candle(
        db=db,
        session=session,
        current_candle=current_candle,
        training_config=training_config,
        SimulationOptions=SimulationOptions,
        model_high=model_high,
        model_low=model_low,
        scalers=scalers
    )
    if pred_dict["status"] != "OK":
        pred_dict['buy_take'] = 0.0
        pred_dict['sell_take'] = 0.0
        pred_dict['buy_stop'] = 0.0
        pred_dict['sell_stop'] = 0.0
        pred_dict['signal'] = 0
        pred_dict['current_close'] = current_candle.close
        new_trade_record = await create_trade_for_candle(
            db=db,
            session=session,
            current_candle=current_candle,
            SimulationOptions=SimulationOptions,
            pred_dict=pred_dict,
            isRealtime=False,
            inf_config=inf_config
        )
        return {
            "status": pred_dict["status"],
            "message": pred_dict["message"]
        }
    buy_take = pred_dict["buy_take"]
    sell_take = pred_dict["sell_take"]
    buy_stop = pred_dict["buy_stop"]
    sell_stop = pred_dict["sell_stop"]
    signal = pred_dict["signal"]
    current_close = current_candle.close

    ############# Update existing trade record #####################
    open_trades = db.query(TradeRecord).filter(
        TradeRecord.session_id == session.id,
        TradeRecord.status == "OPEN"
    ).all()

    for trade in open_trades:
        await check_trade_exit(
            trade=trade,
            current_candle=current_candle,
            SimulationOptions=SimulationOptions,
            current_signal=signal
        )
    db.commit()  # Commit the changes to the database
    #db.refresh(TradeRecord)  # Refresh the session to get the latest data
    

    new_trade_record = await create_trade_for_candle(
        db=db,
        session=session,
        current_candle=current_candle,
        SimulationOptions=SimulationOptions,
        pred_dict=pred_dict,
        isRealtime=False,
        inf_config=inf_config
    )

    return {
        "status": "OK",
        "message": "Trade record updated or created successfully.",
    }
    

async def run_realtime_one_candle(
        db: Session, 
        session: TradeSession, 
        training_config, 
        current_candle: PriceData, 
        SimulationOptions: SimulationOptions,
        model_high: Any,
        model_low: Any,
        scalers: Dict[str, Any],
        inf_config: Dict[str, Any] = {}
):
    pred_dict = await get_prediction_for_candle(
        db=db,
        session=session,
        current_candle=current_candle,
        training_config=training_config,
        SimulationOptions=SimulationOptions,
        model_high=model_high,
        model_low=model_low,
        scalers=scalers
    )

    if pred_dict["status"] != "OK":
        return {
            "status": pred_dict["status"],
            "message": pred_dict["message"]
        }
    
    new_trade_record = await create_trade_for_candle(
        db=db,
        session=session,
        current_candle=current_candle,
        SimulationOptions=SimulationOptions,
        pred_dict=pred_dict,
        isRealtime=True,
        inf_config=inf_config
    )
    if pred_dict["signal"] != 0 and new_trade_record.status == "OPEN":
        ahead_candles = db.query(PriceData).filter(
            PriceData.symbol == session.symbol,
            PriceData.time > current_candle.time
        ).order_by(PriceData.time.asc()).all()
        for ahead_candle in ahead_candles:
            trade_status = await check_trade_exit(
                trade=new_trade_record,
                current_candle=ahead_candle,
                SimulationOptions=SimulationOptions
            )
            if trade_status == "CLOSED":
                break   
        db.commit()
        



