"""Position tracker: syncs positions from Futu API and computes P&L."""

import logging

from futu import RET_OK
from src.core.events import Position

logger = logging.getLogger(__name__)


class PositionTracker:
    def __init__(self, store):
        self.store = store
        self.positions = {}  # code -> Position

    def update_from_api(self, trade_ctx, trd_env):
        """Sync positions from the Futu trade API."""
        try:
            ret, data = trade_ctx.position_list_query(trd_env=trd_env)
            if ret != RET_OK or data is None or data.empty:
                return

            current_codes = set()
            for _, row in data.iterrows():
                code = row["code"]
                qty = int(row["qty"])
                current_codes.add(code)

                if qty <= 0:
                    self.positions.pop(code, None)
                    continue

                current_price = self.store.get_latest_price(code)
                avg_cost = float(row["cost_price"])
                market_value = current_price * qty
                pnl = market_value - avg_cost * qty
                pnl_pct = (current_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0

                pos = self.positions.get(code)
                # Initialize highest to max of cost and current price,
                # so trailing stop has a correct baseline
                if pos:
                    highest = pos.highest_price_since_buy
                else:
                    highest = max(avg_cost, current_price)
                highest = max(highest, current_price)

                self.positions[code] = Position(
                    code=code,
                    qty=qty,
                    avg_cost=avg_cost,
                    current_price=current_price,
                    market_value=market_value,
                    unrealized_pnl=pnl,
                    unrealized_pnl_pct=pnl_pct,
                    highest_price_since_buy=highest,
                )
        except Exception as e:
            logger.error(f"Failed to update positions: {e}")

    def get_position(self, code):
        return self.positions.get(code)

    def get_all_positions(self):
        return dict(self.positions)

    def num_positions(self):
        return len(self.positions)
