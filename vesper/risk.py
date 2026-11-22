import datetime as dt
from dataclasses import dataclass, field

@dataclass
class RiskGate:
    max_daily_loss_pct: float = 0.03
    max_open_positions: int = 3
    _day_start_equity: float = 0.0
    _day: dt.date = field(default_factory=dt.date.today)
    halted: bool = False

    def roll_day(self, equity: float):
        today = dt.date.today()
        if today != self._day:
            self._day = today
            self._day_start_equity = equity
            self.halted = False

    def check(self, equity: float, open_positions: int) -> tuple[bool, str]:
        self.roll_day(equity)
        if self.halted:
            return False, "halted"
        if self._day_start_equity and equity < self._day_start_equity * (1 - self.max_daily_loss_pct):
            self.halted = True
            return False, "daily_loss_limit"
        if open_positions >= self.max_open_positions:
            return False, "max_positions"
        return True, "ok"