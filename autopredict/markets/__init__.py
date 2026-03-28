"""Market adapters for different prediction market venues."""

from .base import MarketAdapter
from .polymarket import PolymarketAdapter

__all__ = ["MarketAdapter", "PolymarketAdapter"]
