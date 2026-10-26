from polygon import RESTClient
from dotenv import load_dotenv
import os
from datetime import datetime
import random
from functools import lru_cache
from datetime import timezone

load_dotenv(override=True)

massive_api_key = os.getenv("MASSIVE_API_KEY")
massive_plan = os.getenv("MASSIVE_PLAN")

is_paid_massive = massive_plan == "paid"


def is_market_open() -> bool:
    client = RESTClient(massive_api_key)
    market_status = client.get_market_status()
    return market_status.market == "open"


def get_all_share_prices_polygon_eod() -> dict[str, float]:
    """With much thanks to student Reema R. for fixing the timezone issue with this!"""
    client = RESTClient(massive_api_key)

    probe = client.get_previous_close_agg("SPY")[0]
    last_close = datetime.fromtimestamp(probe.timestamp / 1000, tz=timezone.utc).date()

    results = client.get_grouped_daily_aggs(last_close, adjusted=True, include_otc=False)
    return {result.ticker: result.close for result in results}


@lru_cache(maxsize=2)
def get_market_for_prior_date(today):
    market_data = get_all_share_prices_polygon_eod()
    return market_data


def get_share_price_polygon_eod(symbol) -> float:
    today = datetime.now().date().strftime("%Y-%m-%d")
    market_data = get_market_for_prior_date(today)
    return market_data.get(symbol, 0.0)


def get_share_price_polygon_min(symbol) -> float:
    client = RESTClient(massive_api_key)
    result = client.get_snapshot_ticker("stocks", symbol)
    return result.min.close or result.prev_day.close


def get_share_price_polygon(symbol) -> float:
    if is_paid_massive:
        return get_share_price_polygon_min(symbol)
    else:
        return get_share_price_polygon_eod(symbol)


def get_share_price(symbol) -> float:
    if massive_api_key:
        try:
            return get_share_price_polygon(symbol)
        except Exception as e:
            print(f"Was not able to use the Massive API due to {e}; using a random number")
    return float(random.randint(1, 100))
