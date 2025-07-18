from json import load
import random
from datetime import datetime
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import PriceData
import random
import os
import yaml
import pandas as pd


def add_ohlc_data_from_excel(start_date: datetime, end_date: datetime, symbol: str = "SPY"):
    db: Session = SessionLocal()
    message = "Trying to insert OHLC data from Excel..."
    try:
        existing = db.query(PriceData).filter(
            PriceData.time >= start_date,
            PriceData.time <= end_date,
            PriceData.symbol == symbol
        ).order_by(PriceData.time.asc()).all()
        if existing:
            existing_start = existing[0].time
            existing_end = existing[-1].time
            message += f" | Data already exists for {symbol} from {existing_start.strftime('%Y-%m-%d %H:%M:%S')} to {existing_end.strftime('%Y-%m-%d %H:%M:%S')}. So No new data added."
            return message
        conf_path = os.getenv("CONFIG_PATH", "not_set")
        config = yaml.safe_load(open(conf_path, 'r')) if conf_path != "not_set" else {}
        excel_path = os.getenv("EXCEL_OHLC_DATA_PATH", "not_set")
        if excel_path == "not_set":
            message += " | EXCEL_OHLC_DATA_PATH environment variable is not set."
            return message
        sheet_names = [sheet.strip() for sheet in config['training_details']['sheet_names'].split(',')]
        data = pd.concat(
            pd.read_excel(excel_path, sheet_name=sheet_names),
            ignore_index=True
        )
        data['Date'] = pd.to_datetime(data['Date'])
        filtered_data = data[(data['Date'] >= start_date) & (data['Date'] <= end_date)]

        # Convert data rows to ORM Objects
        rows = [
            PriceData(
                symbol=symbol,
                time=row['Date'],
                open=row['Open'],
                high=row['High'],
                low=row['Low'],
                close=row['Close'],
                volume=row['Volume']
            ) 
            for _, row in filtered_data.iterrows()
        ]
        db.bulk_save_objects(rows)
        db.commit()
        message += f" | {len(rows)} rows for {symbol} from {start_date.strftime('%Y-%m-%d %H:%M:%S')} to {end_date.strftime('%Y-%m-%d %H:%M:%S')}"

    except Exception as e:
        message += f" | Error inserting OHLC data: {e}"
        db.rollback()
    finally:
        db.close()
    return message
