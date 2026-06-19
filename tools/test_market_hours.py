import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.market_hours import is_us_market_open, get_us_market_status, is_us_tradable_hours
print(f"Market status: {get_us_market_status()}")
print(f"Is open: {is_us_market_open()}")
print(f"Is tradable: {is_us_tradable_hours()}")
