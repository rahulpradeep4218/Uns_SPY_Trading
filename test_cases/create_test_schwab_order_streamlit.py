from trading_functions.db.models import SchwabOrders, RealtimeData, PriceData
from trading_functions.db.session import SessionLocal
from sqlalchemy.orm import Session
from datetime import datetime
from zoneinfo import ZoneInfo

db: Session = SessionLocal()

#data to add
new_order_id = "1003894752012"
option_symbol = "SPY   250817C00650000"
take_profit = 645.0
current_price = 643.0
stop_loss = 640.0
quantity = 1

existing_order = db.query(SchwabOrders).filter(SchwabOrders.open_order_id == new_order_id).first()
if existing_order:
    db.delete(existing_order)
    db.commit()


new_order_db = SchwabOrders(
            open_order_id=new_order_id,
            symbol=option_symbol,
            open_time=datetime.now(ZoneInfo("America/New_York")),
            open_status="FILLED",
            quantity=quantity,
            take_profit=take_profit,
            stop_loss=stop_loss,
            entry_price=current_price,
            profit=0.0
        )
db.add(new_order_db)
db.commit()
db.refresh(new_order_db)

db.close()