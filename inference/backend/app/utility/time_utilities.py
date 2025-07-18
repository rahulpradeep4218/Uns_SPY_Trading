from dateutil import parser, tz
from datetime import datetime, timezone



def to_epoch_ms_est(dt_str: str) -> int:
    """
    Parse dt_str with dateutil, assume America/New_York timezone if none is given,
    then convert to UTC and return milliseconds since the UNIX epoch.
    """
    # 1. Define the Eastern Time zone (handles EST/EDT automatically)
    eastern = tz.gettz("America/New_York")

    # 2. Parse the string (this may attach a tz if the string has one)
    dt = parser.parse(dt_str)

    # 3. If no timezone was present in the string, localize to Eastern
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=eastern)
    else:
        # if the string had a different tz, convert it to Eastern
        dt = dt.astimezone(eastern)

    # 4. Convert to UTC for a correct epoch reference
    dt_utc = dt.astimezone(tz.UTC)

    # 5. Return milliseconds since epoch
    return int(dt_utc.timestamp() * 1000)


def epoch_ms_to_est(epoch_ms: int) -> str:
    """
    Convert milliseconds since the UNIX epoch to a string in EST/EDT.
    """
    # 1. Convert milliseconds to seconds
    dt_utc = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)

    # 2. Convert to Eastern Time
    eastern = tz.gettz("America/New_York")
    dt_est = dt_utc.astimezone(eastern)

    # 3. Return formatted string
    return dt_est.strftime("%Y-%m-%d %H:%M:%S %Z")


