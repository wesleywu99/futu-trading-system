"""Core data classes for signals, orders, and positions."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class SignalStrength(Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


@dataclass
class Signal:
    code: str
    signal_type: SignalType
    strength: SignalStrength
    strategy_name: str
    price: float
    timestamp: datetime
    reason: str
    suggested_qty: int = 0


@dataclass
class OrderEvent:
    code: str
    side: str
    price: float
    qty: int
    order_type: str
    strategy_name: str
    timestamp: datetime
    order_id: str = ""


@dataclass
class Position:
    code: str
    qty: int
    avg_cost: float
    current_price: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    highest_price_since_buy: float = 0.0


@dataclass
class RiskApproval:
    approved: bool
    reason: str
    adjusted_qty: int = 0
