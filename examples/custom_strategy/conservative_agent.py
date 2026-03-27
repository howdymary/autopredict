"""Conservative agent that only uses limit orders to capture spread."""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from autopredict.agent import AutoPredictAgent, AgentConfig, ExecutionStrategy


class ConservativeExecutionStrategy(ExecutionStrategy):
    """Always use limit orders, never market orders."""

    def decide_order_type(
        self,
        *,
        edge: float,
        spread_pct: float,
        liquidity_depth: float,
        time_to_expiry_hours: float,
        aggressive_edge: float,
        mid_price: float,
    ) -> str:
        """
        Conservative order type logic: ALWAYS use limit orders.

        This captures the spread instead of paying it, at the cost of lower fill rates.
        """
        # Ignore all the usual logic - we always want limit orders
        return "limit"


class ConservativeAgent(AutoPredictAgent):
    """
    Conservative trading agent that prioritizes execution quality over fill rate.

    Key differences from baseline:
    - Always uses limit orders (never market orders)
    - Higher minimum edge threshold
    - Smaller position sizes
    - Stricter liquidity requirements
    """

    def __init__(self, config: AgentConfig | None = None) -> None:
        """Initialize with conservative execution strategy."""
        # Use default config if not provided
        if config is None:
            config = AgentConfig(
                min_edge=0.08,  # Higher than baseline (0.05)
                aggressive_edge=999.0,  # Effectively never trigger market orders
                max_risk_fraction=0.015,  # Lower than baseline (0.02)
                max_position_notional=20.0,  # Lower than baseline (25.0)
                min_book_liquidity=80.0,  # Higher than baseline (60.0)
                max_spread_pct=0.03,  # Lower than baseline (0.04)
                max_depth_fraction=0.12,  # Lower than baseline (0.15)
                split_threshold_fraction=0.20,  # Lower than baseline (0.25)
                passive_requote_fraction=0.30,  # Higher than baseline (0.25)
            )

        super().__init__(config)

        # Replace execution strategy with conservative version
        self.execution = ConservativeExecutionStrategy()

    @classmethod
    def from_mapping(cls, data: dict) -> "ConservativeAgent":
        """Create conservative agent from config dict."""
        # Use standard AgentConfig parsing but return ConservativeAgent
        config = AgentConfig(
            min_edge=float(data.get("min_edge", 0.08)),
            aggressive_edge=float(data.get("aggressive_edge", 999.0)),
            max_risk_fraction=float(data.get("max_risk_fraction", 0.015)),
            max_position_notional=float(data.get("max_position_notional", 20.0)),
            min_book_liquidity=float(data.get("min_book_liquidity", 80.0)),
            max_spread_pct=float(data.get("max_spread_pct", 0.03)),
            max_depth_fraction=float(data.get("max_depth_fraction", 0.12)),
            split_threshold_fraction=float(data.get("split_threshold_fraction", 0.20)),
            passive_requote_fraction=float(data.get("passive_requote_fraction", 0.30)),
        )
        return cls(config)


if __name__ == "__main__":
    # Demonstrate conservative agent creation
    agent = ConservativeAgent()
    print("Conservative Agent Configuration:")
    print(f"  min_edge: {agent.config.min_edge}")
    print(f"  aggressive_edge: {agent.config.aggressive_edge}")
    print(f"  max_risk_fraction: {agent.config.max_risk_fraction}")
    print(f"  max_position_notional: {agent.config.max_position_notional}")
    print(f"  min_book_liquidity: {agent.config.min_book_liquidity}")
    print(f"  max_spread_pct: {agent.config.max_spread_pct}")
    print(f"\nStrategy: Limit orders only, prioritize execution quality over fill rate")
