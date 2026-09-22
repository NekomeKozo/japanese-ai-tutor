from datetime import datetime, timezone

def utc(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Review timestamps must have a timezone')
    return value.astimezone(timezone.utc)

class Clock:
    def now(self):
        return datetime.now(timezone.utc)
