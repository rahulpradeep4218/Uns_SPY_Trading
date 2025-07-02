from ast import In
from sqlalchemy.exc import IntegrityError
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any
from datetime import timedelta
from sqlalchemy import desc
from app.db.schemas import SimulationOptions
from app.db.models import TradeSession, TradeRecord, PriceData
from sqlalchemy.orm import Session
from trading_functions.inference.inf_functions import (
    get_maximum_period,
    get_prediction
)

import pandas as pd

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



async def run_simulation_one_candle(
        db: Session, 
        session: TradeSession, 
        training_config, 
        current_candle: PriceData, 
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

    buy_risk_ratio = buy_risk / buy_diff if buy_diff != 0 else 0
    sell_risk_ratio = sell_risk / sell_diff if sell_diff != 0 else 0

    sell_buy_ratio = sell_diff / buy_diff if buy_diff != 0 else 0
    buy_sell_ratio = buy_diff / sell_diff if sell_diff != 0 else 0

    buy_signal = buy_sell_ratio > sell_or_buy_threshold and buy_risk_ratio < risk_threshold
    sell_signal = sell_buy_ratio > sell_or_buy_threshold and sell_risk_ratio < risk_threshold

    signal = 1 if buy_signal else -1 if sell_signal else 0


    ############# Update existing trade record #####################
    open_trades = db.query(TradeRecord).filter(
        TradeRecord.session_id == session.id,
        TradeRecord.status == "OPEN"
    ).all()

    for trade in open_trades:
        if trade.signal == 1:
            
            if SimulationOptions.tp_type == "fixed" and SimulationOptions.tp_value is not None:
                calc_take_profit = trade.entry_price + SimulationOptions.tp_value
            else:
                calc_take_profit = trade.buy_take_profit

            if SimulationOptions.sl_type == "fixed" and SimulationOptions.sl_value is not None:
                calc_stop_loss = trade.entry_price - SimulationOptions.sl_value
            elif SimulationOptions.sl_type == "percent" and SimulationOptions.sl_value is not None:
                calc_stop_loss = trade.entry_price - (( calc_take_profit - trade.entry_price) * SimulationOptions.sl_value)
            else:
                calc_stop_loss = trade.buy_stop_loss

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
            elif SimulationOptions.close_using_signal and signal == -1:
                trade.profit = current_close - trade.entry_price
                trade.status = "CLOSED"
                trade.exit_price = current_close
                trade.exit_reason = "OPPOSITE_SIGNAL"
            elif trade.trade_time + timedelta(minutes=SimulationOptions.max_hold_time) < current_candle.time:
                trade.profit = current_close - trade.entry_price
                trade.status = "CLOSED"
                trade.exit_price = current_close
                trade.exit_reason = "MAX_HOLD_TIME"

            else:
                trade.profit = current_close - trade.entry_price

        elif trade.signal == -1:

            if SimulationOptions.tp_type == "fixed" and SimulationOptions.tp_value is not None:
                calc_take_profit = trade.entry_price - SimulationOptions.tp_value
            else:
                calc_take_profit = trade.sell_take_profit
            if SimulationOptions.sl_type == "fixed" and SimulationOptions.sl_value is not None:
                calc_stop_loss = trade.entry_price + SimulationOptions.sl_value
            elif SimulationOptions.sl_type == "percent" and SimulationOptions.sl_value is not None:
                calc_stop_loss = trade.entry_price + ((trade.entry_price - calc_take_profit) * SimulationOptions.sl_value)
            else:
                calc_stop_loss = trade.sell_stop_loss

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
            elif SimulationOptions.close_using_signal and signal == 1:
                trade.profit = trade.entry_price - current_close
                trade.status = "CLOSED"
                trade.exit_price = current_close
                trade.exit_reason = "OPPOSITE_SIGNAL"
            elif trade.trade_time + timedelta(minutes=SimulationOptions.max_hold_time) < current_candle.time:
                trade.profit = trade.entry_price - current_close
                trade.status = "CLOSED"
                trade.exit_price = current_close
                trade.exit_reason = "MAX_HOLD_TIME"
            else:
                trade.profit = trade.entry_price - current_close
    db.commit()  # Commit the changes to the database
    #db.refresh(TradeRecord)  # Refresh the session to get the latest data


    ############ Crreation of trade record #####################
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
        

    open_trade = open_trade_or_not()
    if open_trade and signal != 0:
        status = "OPEN"
        entry_price = current_close
    else:
        status = "SIGNAL"
        entry_price = None
    if status != "SIGNAL":
        # Calculate calc_stop_loss
        if SimulationOptions.sl_type == "fixed" and SimulationOptions.sl_value is not None:
            calc_stop_loss = entry_price - SimulationOptions.sl_value if signal == 1 else entry_price + SimulationOptions.sl_value
        elif SimulationOptions.sl_type == "percent" and SimulationOptions.sl_value is not None:
            calc_stop_loss = entry_price - ((buy_take - entry_price) * SimulationOptions.sl_value) if signal == 1 else entry_price + ((entry_price - sell_take) * SimulationOptions.sl_value)
        else:
            calc_stop_loss = sell_stop if signal == -1 else buy_stop

        # Calculate calc_take_profit
        if SimulationOptions.tp_type == "fixed" and SimulationOptions.tp_value is not None:
            calc_take_profit = entry_price + SimulationOptions.tp_value if signal == 1 else entry_price - SimulationOptions.tp_value
        else:
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


    return {
        "status": "OK",
        "message": "Trade record updated or created successfully.",
    }
    


