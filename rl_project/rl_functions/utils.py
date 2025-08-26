import random
import datetime
from trading_functions.db.session import SessionLocal
from trading_functions.db.models import PriceData
from sqlalchemy.orm import Session
import numpy as np
import pandas as pd

def get_random_weekday(year, db: Session):
    """
    Returns a random date from the given year that is not a Saturday or Sunday.
    """
    # Query all dates in PriceData for the given year
    dates = db.query(PriceData.time).filter(
        PriceData.time >= datetime.date(year, 1, 1),
        PriceData.time <= datetime.date(year, 12, 31)
    ).all()
    if not dates:
        return None
    random_date = random.choice([d[0] for d in dates])
    return random_date



def get_slope_values(values: pd.Series):
    if len(values) < 2:
        return 0
    x = np.arange(len(values))
    y = values.to_numpy()
    A = np.vstack([x, np.ones(len(x))]).T
    m, c = np.linalg.lstsq(A, y, rcond=None)[0]
    return m