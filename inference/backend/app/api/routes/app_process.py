
from venv import logger
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import alias
from sqlalchemy.orm import Session
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import os

from app.api.deps import get_db
from app.db.schemas import SimulationOptions, TradeStats, TradeRecordResponse
from app.db.models import TradeSession, PriceData, TradeRecord
import yaml
from trading_functions.inference.inf_functions import (
    download_artifacts,
    get_model_from_mlflow
)
import os
from app.methods.sim_lib import run_simulation_one_candle, run_realtime_one_candle, check_trade_exit

from app.methods.schwab_methods import get_price_history, sync_realtime_price_history
import time
import logging

logger = logging.getLogger(__name__)

load_dotenv()

router = APIRouter()


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
    
    candles_query = db.query(PriceData).filter(
            PriceData.symbol == session.symbol,
            PriceData.time <= session.trade_end,
            PriceData.time >= session.trade_start
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

    response = {
        "session": jsonable_encoder(session),
        "trades": jsonable_encoder(all_trades),
        "trade_stats": trade_stats.model_dump(),
        "last_trade_signal_time": last_trade_signal_time,
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
        

        speed = min(sim_options.speed, 20.0)  # Cap speed to a maximum of 20x
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

            candles_till_now = db.query(PriceData).filter(
                PriceData.symbol == session_record.symbol,
                PriceData.time <= current_candle.time,
                PriceData.time >= session_record.trade_start
            ).all()
            trade_signals_till_now = db.query(TradeRecord).filter(
                TradeRecord.session_id == session_id,
                TradeRecord.trade_time <= current_candle.time,
                TradeRecord.trade_time >= session_record.trade_start
            ).all()
            trade_signals_till_now_count = len(trade_signals_till_now)
            progress = trade_signals_till_now_count / len(all_candles) * 100 if all_candles else 0
            candles_list = [can for can in candles_till_now]
            candle_table = jsonable_encoder(candles_list)
            await websocket.send_json({
                "type": "candle_data",
                "data": candle_table
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
        while True:
            print("Waiting for initial data from client...")
            initial_data = await websocket.receive_json()
            print("Session id : ", session_id)
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
            print("Scalers and models loaded successfully. Running sync realtime for once before entering loop")
            first_record_time = sync_realtime_price_history(
                session_record.symbol,
                inf_config['inference']['schwab']
            ) 
            sync_frequency = inf_config['inference']['schwab'].get('realtime_schwab_sync_frequency', 20)  # Default to 20 seconds

            candles_query = db.query(PriceData).filter(
                PriceData.symbol == session_record.symbol,
                PriceData.time >= first_record_time
            ).order_by(PriceData.time.desc())
            
            candles = candles_query.all()
            print(f"Total candles to process: {len(candles)}")
            last_sync_time = 0

            for current_candle in candles:
                # Simulate processing time based on speed factor
                #await asyncio.sleep(1.0 / speed)
                # Check already trade run for this candle
                
                now = time.time()
                if now - last_sync_time >= sync_frequency:
                    print(f"Syncing realtime data for session {session_id} at {current_candle.time}")
                    first_record_time = sync_realtime_price_history(
                        session_record.symbol,
                        inf_config['inference']['schwab']
                    ) 
                    open_trades = db.query(TradeRecord).filter(
                        TradeRecord.session_id == session_id,
                        TradeRecord.status == "OPEN"
                    ).all()
                    for trade in open_trades:
                        await check_trade_exit(trade, current_candle, sim_options)
                    db.commit()  # Commit the changes to the database
                    last_sync_time = time.time()
                else:
                    trade_candle = db.query(TradeRecord).filter(
                        TradeRecord.session_id == session_id,
                        TradeRecord.trade_time == current_candle.time,
                    ).first()
                    if trade_candle:
                        continue
                    result = await run_realtime_one_candle(
                        db,
                        session_record,
                        training_config,
                        current_candle,
                        sim_options,
                        model_high,
                        model_low,
                        scalers
                    )

                candle_data = db.query(PriceData).filter(
                    PriceData.symbol == session_record.symbol,
                    PriceData.time >= first_record_time,
                ).all()
                progress = 0
                candles_list = [can for can in candle_data]
                candle_table = jsonable_encoder(candles_list)
                await websocket.send_json({
                    "type": "candle_data",
                    "data": candle_table
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

    all_trade_signals = db.query(TradeRecord).filter(
        TradeRecord.session_id == session_id
    ).count()

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