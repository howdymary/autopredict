"""Market adapters for different prediction market venues."""

from .base import MarketAdapter

__all__ = ["MarketAdapter", "PolymarketAdapter"]


def __getattr__(name: str):
    if name == "PolymarketAdapter":
        from .polymarket import PolymarketAdapter

        return PolymarketAdapter
    raise AttributeError(name)
