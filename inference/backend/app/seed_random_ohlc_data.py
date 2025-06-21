import random
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import PriceData

def generate_ohlc(symbol: str, start_time: datetime, num_rows: int):
    data = []
    current_time = start_time
    price = 100
    for _ in range(num_rows):
        open_price = price
        high_price = open_price + random.uniform(0, 5)
        low_price = open_price - random.uniform(0, 5)
        close_price = random.uniform(low_price, high_price)
        volume = random.randint(100, 1000)

        data.append(PriceData(
            symbol=symbol,
            time=current_time,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume
        ))

        current_time = current_time + timedelta(minutes=1)
        price = close_price

    return data

def seed_random_ohlc_data():
    db: Session = SessionLocal()
    try:
        symbol = "SPY"
        start_time = datetime(2025, 6, 18, 9, 30)
        rows = generate_ohlc(symbol, start_time, 300)
        db.bulk_save_objects(rows)
        db.commit()

        start_time = datetime(2025, 6, 17, 10, 30)
        rows = generate_ohlc(symbol, start_time, 300)
        db.bulk_save_objects(rows)
        db.commit()

        print("Inserted random OHLC data successfully.")
    except Exception as e:
        print(f"Error inserting random OHLC data: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_random_ohlc_data()