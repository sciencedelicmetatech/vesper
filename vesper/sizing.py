from dataclasses import dataclass

@dataclass
class Sizer:
    risk_per_trade: float = 0.01     # 1% of equity per trade
    max_position_pct: float = 0.10   # 10% of equity max per position
    stop_distance_pct: float = 0.02  # 2% stop → used to convert risk to size

    def size(self, equity: float, price: float) -> float:
        if price <= 0 or equity <= 0:
            return 0.0
        risk_dollars = equity * self.risk_per_trade
        size_by_risk = risk_dollars / (price * self.stop_distance_pct)
        size_by_cap = (equity * self.max_position_pct) / price
        return round(min(size_by_risk, size_by_cap), 6)