from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import os
from app.api.deps import get_db
from trading_functions.db.schemas import SimulationOptions, TradeStats, TradeRecordResponse
from trading_functions.db.models import TradeSession, PriceData, TradeRecord, RealtimeData
import yaml
from trading_functions.inference.inf_functions import (
    download_artifacts,
    get_model_from_mlflow
)
import os
from app.methods.sim_lib import run_simulation_one_candle, run_realtime_one_candle, check_trade_exit
import time
import logging
import math
from app.methods.schwab_methods import get_time_field
logger = logging.getLogger(__name__)

load_dotenv()

router = APIRouter()

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

def serialize_candle(candle):
    return {
        'symbol': candle.symbol,
        'time': candle.time.isoformat() if isinstance(candle.time, datetime) else candle.time,
        'open': candle.open,
        'high': candle.high,
        'low': candle.low,
        'close': candle.close,
        'volume': candle.volume,
    }


def get_inf_config():
    inf_config_path = os.getenv('CONFIG_PATH', 'NO_PATH')
    if not inf_config_path or not os.path.exists(inf_config_path):
        raise FileNotFoundError(f"Configuration file not found at {inf_config_path}")
    
    with open(inf_config_path, 'r') as file:
        inf_config = yaml.safe_load(file)
    
    return inf_config


def get_data_for_model_inference(session_record: TradeSession):
    high_alias = session_record.model_high_alias
    inf_config = get_inf_config()
    scalers, training_config = download_artifacts(
        config=inf_config,
        alias=high_alias,
    )
    model_high_version = session_record.model_high_version
    model_low_version = session_record.model_low_version

    model_high = get_model_from_mlflow(
        config=inf_config,
        model_name=inf_config['mlflow']['high_model_name'],
        model_version=model_high_version
    )
    model_low = get_model_from_mlflow(
        config=inf_config,
        model_name=inf_config['mlflow']['low_model_name'],
        model_version=model_low_version
    )
    return scalers, training_config, model_high, model_low , inf_config


def generate_tos_order(trade: TradeRecord):
    inf_config = get_inf_config()
    tos_cfg = inf_config['inference']['tos']
    position_size = tos_cfg.get('position_size')
    manual_exp = tos_cfg.get('exp_date_manual', None)
    if manual_exp:
        exp_date = datetime.strptime(manual_exp, "%Y-%m-%d")
    else:
        days_to_add = tos_cfg.get('exp_days_increment')
        exp_date = datetime.now() + timedelta(days=days_to_add)

    exp_month = MONTHS[exp_date.month - 1]
    exp_day = exp_date.day
    exp_year = exp_date.strftime('%y') # 2 digit year

    strike_increment = tos_cfg.get('strike_otm_increment')
    base_price = trade.entry_price

    if trade.signal == 1:  # Buy signal
        strike_price = math.ceil(base_price + strike_increment)
        take_profit_op = "AT OR ABOVE"
        stop_loss_op = "AT OR BELOW"
        option_type = 'CALL'
    else:  # Sell signal
        strike_price = math.floor(base_price - strike_increment)
        take_profit_op = "AT OR BELOW"
        stop_loss_op = "AT OR ABOVE"
        option_type = 'PUT'
    stop_dummy_price = int(tos_cfg.get('stop_dummy_price'))
    strike_price = int(strike_price)

    take_profit = trade.calc_take_profit if trade.calc_take_profit else None
    stop_loss = trade.calc_stop_loss if trade.calc_stop_loss else None


    tos_order_code = (
        f"BUY  +{position_size} SPY 100 (Weeklys) {exp_day} {exp_month} {exp_year} {strike_price} {option_type} MKT OCO\n"
        f"SELL -{position_size} SPY 100 (Weeklys) {exp_day} {exp_month} {exp_year} {strike_price} {option_type} STP {stop_dummy_price} OCO TRG BY OCO WHEN SPY MARK {take_profit_op} {take_profit:.2f}\n"
        f"SELL -{position_size} SPY 100 (Weeklys) {exp_day} {exp_month} {exp_year} {strike_price} {option_type} STP {stop_dummy_price} OCO TRG BY OCO WHEN SPY MARK {stop_loss_op} {stop_loss:.2f}"
    )

    return tos_order_code


@router.get("/get-tos-order")
def get_tos_order(session_id: int, trade_time: str, db: Session = Depends(get_db)):
    """
    Get TOS order for a given session ID.
    """
    trade_record = db.query(TradeRecord).filter(
        TradeRecord.session_id == session_id,
        TradeRecord.trade_time == datetime.fromisoformat(trade_time)
    ).first()
    if not trade_record:
        return JSONResponse(content={"error": "Trade record not found"}, status_code=404)
    else:
        tos_order_code = generate_tos_order(trade_record)
        return JSONResponse(content={"tos_order_code": tos_order_code}, status_code=200)


@router.get("/get_simulation_options")
async def get_simulation_options(type: str = "simulation"):
    inf_config = get_inf_config()
    simulation_options_path = inf_config.get('inference', {}).get('simulation_options_config_path', 'simulation_options.yaml')
    inf_config_path = os.getenv('CONFIG_PATH', 'NO_PATH')
    config_dir = os.path.dirname(inf_config_path)
    simulation_options_path = os.path.join(config_dir, simulation_options_path)
    with open(simulation_options_path, 'r') as file:
        simulation_options = yaml.safe_load(file)

    return jsonable_encoder(simulation_options.get(type, {}))

@router.post("/set_simulation_options")
async def set_simulation_options(options: SimulationOptions, type: str = Query(default="simulation")):
    inf_config = get_inf_config()
    simulation_options_path = inf_config.get('inference', {}).get('simulation_options_config_path', 'simulation_options.yaml')
    inf_config_path = os.getenv('CONFIG_PATH', 'NO_PATH')
    config_dir = os.path.dirname(inf_config_path)
    simulation_options_path = os.path.join(config_dir, simulation_options_path)

    with open(simulation_options_path, 'r') as file:
        complete_simulation_options = yaml.safe_load(file)

    complete_simulation_options[type] = jsonable_encoder(options)

    with open(simulation_options_path, 'w') as file:
        yaml.dump(complete_simulation_options, file, default_flow_style=False)

    return {"message": "Simulation options updated successfully."}

@router.get("/get_session/{session_id}")
async def get_session(session_id: int, db: Session = Depends(get_db)):

    session = db.query(TradeSession).filter(TradeSession.id == session_id).first()
    if not session:
        return JSONResponse(content={"error": "Session not found"}, status_code=404)
    if session.trade_end is None or session.trade_start is None or session.trade_end == session.trade_start:
        schwab_config = get_inf_config()['inference']['schwab']
        trade_start, trade_end = get_first_record_time_realtime(db=db, schwab_config=schwab_config, session_record=session)
        logger.info(f"Session trade start or end is none or equal indicating that its a realtime session , so got trade_start: {trade_start} and trade_end: {trade_end}")

        trade_start_str = trade_start.strftime("%Y-%m-%d ") + "00:00:00"
        trade_end_str = trade_end.strftime("%Y-%m-%d %H:%M:%S")
    else:
        trade_start = session.trade_start
        trade_end = session.trade_end
        trade_start_str = trade_start.strftime("%Y-%m-%d %H:%M:%S")
        trade_end_str = trade_end.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Got session start and end from session record, Session trade start: {trade_start_str} and trade_end: {trade_end_str}")


    candles_query = db.query(PriceData).filter(
            PriceData.symbol == session.symbol,
            PriceData.time <= trade_end_str,
            PriceData.time >= trade_start_str
        ).all()
    all_candles_count = len(candles_query)

    last_trade_signal_row = db.query(TradeRecord).filter(
        TradeRecord.session_id == session_id,
    ).order_by(TradeRecord.trade_time.desc()).first()
    if last_trade_signal_row:
        last_trade_signal_time = last_trade_signal_row.trade_time
    else:
        last_trade_signal_time = None
    progress = 0.0
    if last_trade_signal_time:    
        candles_till_now = db.query(PriceData).filter(
            PriceData.symbol == session.symbol,
            PriceData.time <= last_trade_signal_time
        ).all()
        candle_till_now_count = len(candles_till_now)
        trade_till_now = db.query(TradeRecord).filter(
            TradeRecord.session_id == session_id,
            TradeRecord.trade_time <= last_trade_signal_time,
            TradeRecord.trade_time >= session.trade_start
        ).all()
        trade_till_now_count = len(trade_till_now)
        if all_candles_count > 0:
            progress = trade_till_now_count / all_candles_count * 100
        else:
            progress = 0.0


    all_trades, trade_stats = get_trade_and_trade_stats(
        db,
        session_id,
        progress
    )

    take_profits = get_trade_record_values(
        db=db,
        session_id=session_id,
        trade_start=trade_start,
        trade_end=trade_end
    )
    

    response = {
        "session": jsonable_encoder(session),
        "trades": jsonable_encoder(all_trades),
        "trade_stats": trade_stats.model_dump(),
        "last_trade_signal_time": last_trade_signal_time,
        "take_profits": take_profits,
    }
    return response

@router.get("/remove_all_trades/{session_id}")
async def remove_all_trades(session_id: int, db: Session = Depends(get_db)):
    db.query(TradeRecord).filter(TradeRecord.session_id == session_id).delete()
    db.commit()
    return {"message": "All trades removed successfully."}


@router.websocket("/ws/simulation/{session_id}")
async def websocket_simulation(
    websocket: WebSocket, 
    session_id: int,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time simulation updates.
    """
    await websocket.accept()
    speed = 1.0 # Default speed factor for simulation
    try:
        initial_data = await websocket.receive_json()
        sim_options = SimulationOptions(**initial_data['options'])
        logger.info(f"Received simulation options: {sim_options.model_dump()}")
        

        speed = min(sim_options.speed, 100.0)  # Cap speed to a maximum of 100x
        logger.info(f"Speed delay : {1.0 / speed}")
        session_record = db.query(TradeSession).filter(TradeSession.id == session_id).first()
        if not session_record:
            await websocket.close(code=1008, reason="Session not found")
            return
        high_alias = session_record.model_high_alias if session_record.model_high_alias else None
        if not high_alias:
            await websocket.close(code=1008, reason="Session high model alias not found")
            return
        
        scalers, training_config, model_high, model_low, inf_config = get_data_for_model_inference(session_record)

        candles_query = db.query(PriceData).filter(
            PriceData.symbol == session_record.symbol,
            PriceData.time <= session_record.trade_end,
            PriceData.time >= session_record.trade_start
        ).order_by(PriceData.time.asc())
        all_candles = candles_query.all()
        #print("Total candles to process:", len(candles))
        last_trade = db.query(TradeRecord).filter(
            TradeRecord.session_id == session_id,
        ).order_by(TradeRecord.trade_time.desc()).first()

        if last_trade:
            print(f"Resuming from last trade time : {last_trade.trade_time}")
            candles_query = candles_query.filter(
                PriceData.time > last_trade.trade_time
            )
        else:
            print("No previous trades found, starting from the beginning of the session.")
        
        candles = candles_query.all()
        print(f"Total candles to process: {len(candles)}")

        for current_candle in candles:
            # Simulate processing time based on speed factor
            await asyncio.sleep(1.0 / speed)

            result = await run_simulation_one_candle(
                db, 
                session_record, 
                training_config, 
                current_candle, 
                sim_options, 
                model_high, 
                model_low, 
                scalers,
                inf_config=inf_config
            )

            # candles_till_now = db.query(PriceData).filter(
            #     PriceData.symbol == session_record.symbol,
            #     PriceData.time <= current_candle.time,
            #     PriceData.time >= session_record.trade_start
            # ).all()
            trade_signals_till_now = db.query(TradeRecord).filter(
                TradeRecord.session_id == session_id,
                TradeRecord.trade_time <= current_candle.time,
                TradeRecord.trade_time >= session_record.trade_start
            ).all()
            trade_signals_till_now_count = len(trade_signals_till_now)
            progress = trade_signals_till_now_count / len(all_candles) * 100 if all_candles else 0
            #candles_list = [can for can in candles_till_now]
            #candle_table = jsonable_encoder(candles_list)
            await websocket.send_json({
                "type": "candle_data",
                "data": [serialize_candle(current_candle)]
            })

            all_trades, trade_stats = get_trade_and_trade_stats(
                db,
                session_id,
                progress
            )

            await websocket.send_json({
                "type": "trade_stats",
                "data": trade_stats.model_dump()
            })

            trade_table = [trade for trade in all_trades]
            trade_table = jsonable_encoder(trade_table)
            await websocket.send_json({
                "type": "trade_table",
                "data": trade_table
            })

    except WebSocketDisconnect:
        print(f"Client disconnected from session {session_id}")


def get_first_record_time_realtime(db: Session, schwab_config, session_record: TradeSession) -> datetime:
    realtime_period_days = schwab_config.get('realtime_period_days', 1)
    last_candle = db.query(PriceData).filter(
        PriceData.symbol == session_record.symbol
    ).order_by(PriceData.time.desc()).first()
    if last_candle:
        # Skip weekends when subtracting realtime_period days from trade_end
        days_added = 0
        trade_end = last_candle.time
        trade_start = trade_end
        while days_added < realtime_period_days:
            trade_start -= timedelta(days=1)
            if trade_start.weekday() < 5:  # Monday=0, Sunday=6
                days_added += 1
        return trade_start, trade_end
    else:
        return None


def get_trade_record_values(
        db: Session, 
        session_id: int, 
        trade_start: datetime, 
        trade_end: datetime
        ) -> Optional[Dict[str, List]]:
    
    trade_records = db.query(TradeRecord).filter(
        TradeRecord.session_id == session_id,
        TradeRecord.trade_time >= trade_start,
        TradeRecord.trade_time <= trade_end
    ).order_by(TradeRecord.trade_time.asc()).all()
    if not trade_records:
        return {
            "time": [],
            "sell_take_profit": [],
            "buy_take_profit": []
        }
    
    return {
        "time": [rec.trade_time for rec in trade_records],
        "sell_take_profit": [rec.sell_take_profit for rec in trade_records],
        "buy_take_profit": [rec.buy_take_profit for rec in trade_records],
    }



@router.websocket("/ws/realtime")
async def websocket_realtime(
    websocket: WebSocket, 
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time simulation updates.
    """
    session_id = 0
    await websocket.accept()
    try:
        last_history_sync_time = 0
        last_realtime_sync_time = 0
        logger.info("Waiting for initial data from client...")
        initial_data = await websocket.receive_json()
        logger.info("Session id : %d", session_id)
        sim_options = SimulationOptions(**initial_data['options'])
        session_record = db.query(TradeSession).filter(TradeSession.id == session_id).first()
        if not session_record:
            await websocket.close(code=1008, reason="Realtime Session not found")
            return
        high_alias = session_record.model_high_alias if session_record.model_high_alias else None
        if not high_alias:
            await websocket.close(code=1008, reason="Session high model alias not found")
            return
        
        scalers, training_config, model_high, model_low, inf_config = get_data_for_model_inference(session_record)
        logger.info("Scalers and models loaded successfully. Running sync realtime for once before entering loop")

        schwab_config = inf_config['inference']['schwab']
        first_record_time, last_record_time = get_first_record_time_realtime(db, schwab_config, session_record)

        #print(f"Total candles to process: {len(candles)}")
        initial_data_sent = False
        realtime_sync_frequency = history_sync_frequency = 1
        while True:
            
            candles_query = db.query(PriceData).filter(
                PriceData.symbol == session_record.symbol,
                PriceData.time >= first_record_time
            ).order_by(PriceData.time.desc())
            
            candles = candles_query.all()
            for current_candle in candles:
                # Simulate processing time based on speed factor
                #await asyncio.sleep(1.0 / speed)
                # Check already trade run for this candle
                
                now = time.time()
                if now - last_realtime_sync_time >= realtime_sync_frequency:
                    realtime_record = db.query(RealtimeData).filter(RealtimeData.symbol == session_record.symbol).first()
                    if not realtime_record:
                        logger.error(f"No realtime data found in the database for the symbol: {session_record.symbol}")
                        continue
                    last_time_db = await get_time_field(realtime_record, "time")
                    last_time_ms = int(last_time_db.timestamp() * 1000)
                    realtime_res = {
                        'time': last_time_ms,
                        'price': realtime_record.price,
                        'symbol': realtime_record.symbol,
                    }
                    await websocket.send_json({
                            "type": "realtime_data",
                            "data": realtime_res
                        })
                    last_realtime_sync_time = time.time()
                if now - last_history_sync_time >= history_sync_frequency:
                    logger.debug(f"Syncing history data for session {session_id} at {current_candle.time}")
                    first_record_time, last_record_time = get_first_record_time_realtime(db, schwab_config, session_record)

                    open_trades = db.query(TradeRecord).filter(
                        TradeRecord.session_id == session_id,
                        TradeRecord.status == "OPEN"
                    ).all()
                    for trade in open_trades:
                        if trade.trade_time < current_candle.time:
                            await check_trade_exit(trade, current_candle, sim_options)
                    db.commit()  # Commit the changes to the database
                    last_history_sync_time = time.time()
                    logger.debug(f"Last history sync time updated to {last_history_sync_time}")

                    candle_data = db.query(PriceData).filter(
                        PriceData.symbol == session_record.symbol,
                        PriceData.time >= first_record_time,
                    ).order_by(PriceData.time.asc()).all()
                    
                    trade_data = db.query(TradeRecord).filter(
                        TradeRecord.session_id == session_id,
                        TradeRecord.trade_time >= first_record_time,
                    ).order_by(TradeRecord.trade_time.asc()).all()
                    if not initial_data_sent:
                        candles_list = [can for can in candle_data]
                        candle_table = jsonable_encoder(candles_list)
                        await websocket.send_json({
                            "type": "candle_data",
                            "data": candle_table
                        })

                        take_profits = get_trade_record_values(
                            db=db,
                            session_id=session_id,
                            trade_start=first_record_time,
                            trade_end=current_candle.time
                        )
                        await websocket.send_json({
                            "type": "take_profits",
                            "data": jsonable_encoder(take_profits)
                        })

                    else:
                        last_candle = candle_data[-1] if candle_data else None
                        if last_candle:
                            await websocket.send_json({
                                "type": "candle_data",
                                "data": [serialize_candle(last_candle)]
                            })
                        trade_data = db.query(TradeRecord).filter(
                            TradeRecord.session_id == session_id,
                            TradeRecord.trade_time >= first_record_time,
                        ).order_by(TradeRecord.trade_time.asc()).all()
                        last_trade = trade_data[-1] if trade_data else None
                        if last_trade:
                            trade_time = last_trade.trade_time
                            trade_buy_take_profit = last_trade.buy_take_profit
                            trade_sell_take_profit = last_trade.sell_take_profit
                            jsonable_trade_data = {
                                "time": [trade_time],
                                "buy_take_profit": [trade_buy_take_profit],
                                "sell_take_profit": [trade_sell_take_profit]
                            }
                            await websocket.send_json({
                                "type": "trade_data",
                                "data": jsonable_encoder(jsonable_trade_data)
                            })
                    initial_data_sent = True

                

                else:
                    trade_candle = db.query(TradeRecord).filter(
                        TradeRecord.session_id == session_id,
                        TradeRecord.trade_time == current_candle.time,
                    ).first()
                    if trade_candle:
                        continue
                    try:
                        result = await run_realtime_one_candle(
                            db,
                            session_record,
                            training_config,
                            current_candle,
                            sim_options,
                            model_high,
                            model_low,
                            scalers,
                            inf_config=inf_config
                        )
                    except Exception as e:
                        logger.error(f"Error processing candle {current_candle.time}: {str(e)}")
                        raise HTTPException(status_code=500, detail=str(e))

                
                progress = 0
                all_trades, trade_stats = get_trade_and_trade_stats(
                    db,
                    session_id,
                    progress
                )

                await websocket.send_json({
                    "type": "trade_stats",
                    "data": trade_stats.model_dump()
                })

                trade_table = [trade for trade in all_trades]
                trade_table = jsonable_encoder(trade_table)
                await websocket.send_json({
                    "type": "trade_table",
                    "data": trade_table
                })
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        print(f"Client disconnected from session {session_id}")


def get_trade_and_trade_stats(db: Session, session_id: int, progress: float):
    trades_closed = db.query(TradeRecord).filter(
        TradeRecord.session_id == session_id,
        TradeRecord.status == "CLOSED",
    ).all()
    trades_open = db.query(TradeRecord).filter(
        TradeRecord.session_id == session_id,
        TradeRecord.status == "OPEN",
    ).all()
    all_trades = db.query(TradeRecord).filter(
        TradeRecord.session_id == session_id,
        TradeRecord.signal != 0,
        TradeRecord.status != "SIGNAL"
    ).order_by(TradeRecord.trade_time.desc()).all()

    # all_trade_signals = db.query(TradeRecord).filter(
    #     TradeRecord.session_id == session_id
    # ).count()

    total_profit = 0.0
    win_count = 0
    loss_count = 0
    max_drawdown_percent = 0

    for trade in trades_closed:
        total_profit += trade.profit
        if trade.profit > 0:
            win_count += 1
        else:
            loss_count += 1

    # Calculate winning percentage
    winning_percentage = (win_count / len(trades_closed) * 100) if trades_closed else 0

    # Calculate average profit
    average_profit = (total_profit / len(trades_closed)) if trades_closed else 0

    unrealized_profit = 0.0
    for trade in trades_open:
        unrealized_profit += trade.profit

    trade_stats = TradeStats(
        total_trades=len(all_trades),
        winning_trades=win_count,
        losing_trades=loss_count,
        winning_percentage=winning_percentage,
        average_profit=average_profit,
        unrealized_profit=unrealized_profit,
        total_profit=total_profit,
        percent_complete= progress
    )

    return all_trades, trade_stats