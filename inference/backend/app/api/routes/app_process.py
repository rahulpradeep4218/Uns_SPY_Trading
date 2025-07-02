import json
from math import inf
from pdb import run
import stat
from webbrowser import get
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import alias
from sqlalchemy.orm import Session
import asyncio
from datetime import datetime

from app.api.deps import get_db
from app.db.schemas import SimulationOptions, TradeStats, TradeRecordResponse
from app.db.models import TradeSession, PriceData, TradeRecord
import yaml
from trading_functions.inference.inf_functions import (
    download_artifacts,
    get_model_from_mlflow
)
from app.methods.sim_lib import run_simulation_one_candle



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
        if all_candles_count > 0:
            progress = candle_till_now_count / all_candles_count * 100
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
        inf_config_path = '../../Config/config_dev.yaml'
        with open(inf_config_path, 'r') as file:
            inf_config = yaml.safe_load(file)
        speed = min(sim_options.speed, 10.0)  # Cap speed to a maximum of 10x
        session_record = db.query(TradeSession).filter(TradeSession.id == session_id).first()
        if not session_record:
            await websocket.close(code=1008, reason="Session not found")
            return
        high_alias = session_record.model_high_alias if session_record.model_high_alias else None
        if not high_alias:
            await websocket.close(code=1008, reason="Session high model alias not found")
            return
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
                scalers
            )

            candles_till_now = db.query(PriceData).filter(
                PriceData.symbol == session_record.symbol,
                PriceData.time <= current_candle.time,
                PriceData.time >= session_record.trade_start
            ).all()
            candle_till_now_count = len(candles_till_now)
            progress = candle_till_now_count / len(all_candles) * 100 if all_candles else 0
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
        TradeRecord.signal != 0
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