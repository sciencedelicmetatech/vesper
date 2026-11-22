from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any
from vesper.decider import Signal, Side

@dataclass
class ExecutionResult:
    order_id: str
    filled_price: Optional[float] = None
    filled_size: float = 0.0
    status: str = "PENDING"  # PENDING, FILLED, REJECTED, PARTIAL
    raw_response: Optional[Dict[str, Any]] = None

class BrokerAdapter(ABC):
    @abstractmethod
    def submit_order(self, signal: Signal, state: MarketState) -> ExecutionResult:
        """Translate a Signal into a broker order. Must be idempotent."""
        ...
    
    @abstractmethod
    def get_order_status(self, order_id: str) -> ExecutionResult:
        """Poll or retrieve the current state of an order."""
        ...
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        ...
    
    @abstractmethod
    def get_position(self, symbol: str) -> float:
        """Current position size for the symbol."""
        ...