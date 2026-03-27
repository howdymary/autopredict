"""Mutable agent template for AutoPredict experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .market_env import OrderBook

# Constants for epsilon values and calculation precision
EPSILON = 1e-9
BPS_MULTIPLIER = 10_000.0


@dataclass
class AgentConfig:
    """Baseline knobs intended to evolve over experiments.

    This dataclass holds all tunable parameters for agent decision-making.
    Each parameter controls a specific aspect of order selection, sizing, and risk management.
    All parameters are JSON-serializable floats and can be edited in strategy_configs/{name}.json.

    Attributes:
        min_edge: Minimum edge (probability units) to consider a trade. Skip if edge < this.
            Typical: 0.05 (5% edge). Higher = fewer but higher-quality trades.

        aggressive_edge: Threshold for using market orders instead of limit orders.
            If edge >= this AND edge_to_spread_ratio >= 3.0: use market order.
            Typical: 0.12 (12% edge triggers aggression).

        max_risk_fraction: Maximum loss per trade as fraction of bankroll.
            Typical: 0.02 (risk 2% per trade). Hard limit on position size.

        max_position_notional: Hard cap on position size in currency units.
            Typical: $25.0. Independent of bankroll - prevents oversizing.

        min_book_liquidity: Minimum visible depth to trade (sum of both sides).
            Typical: 60.0. Avoids thin books where execution is poor.

        max_spread_pct: Maximum spread (as % of mid price) to trade unless edge is strong.
            Typical: 0.04 (4% spread is max). Wide spreads = high slippage.

        max_depth_fraction: Maximum position as fraction of visible depth.
            Typical: 0.15 (don't take > 15% of available depth). Prevents market impact.

        split_threshold_fraction: Threshold for splitting orders.
            If size > available_depth * this: split into 3 slices. Typical: 0.25.

        passive_requote_fraction: Reserved for future passive order re-quoting logic.

        limit_price_improvement_ticks: Reserved for future limit price placement logic.

    Example:
        >>> config = AgentConfig(min_edge=0.08, aggressive_edge=0.15)
        >>> agent = AutoPredictAgent(config)
    """

    min_edge: float = 0.05
    aggressive_edge: float = 0.12
    max_risk_fraction: float = 0.02
    max_position_notional: float = 25.0
    min_book_liquidity: float = 60.0
    max_spread_pct: float = 0.04
    max_depth_fraction: float = 0.15
    split_threshold_fraction: float = 0.25
    passive_requote_fraction: float = 0.25
    limit_price_improvement_ticks: float = 1.0


@dataclass
class MarketState:
    """Normalized decision context for one market snapshot.

    This represents a single market at a point in time, with all information
    the agent needs to make a trading decision. Normalized to prevent duplicate
    logic in agent.evaluate_market().

    Attributes:
        market_id: Unique identifier for the market (e.g., "politics-2025-03").
        market_prob: Current market price (0-1, binary outcome YES/NO).
        fair_prob: Your forecast probability (0-1).
        time_to_expiry_hours: Time until market resolves (in hours).
        order_book: OrderBook object with bids, asks, liquidity.
        metadata: Additional context (category, tag, etc.) as optional dict.

    Example:
        >>> state = MarketState(
        ...     market_id="sports-2025-nfl",
        ...     market_prob=0.45,
        ...     fair_prob=0.65,
        ...     time_to_expiry_hours=24.0,
        ...     order_book=order_book,
        ...     metadata={"category": "sports"}
        ... )
        >>> agent.evaluate_market(state, bankroll=1000.0)
    """

    market_id: str
    market_prob: float
    fair_prob: float
    time_to_expiry_hours: float
    order_book: OrderBook
    metadata: dict[str, float | str] = field(default_factory=dict)


@dataclass
class ProposedOrder:
    """Normalized agent order proposal.

    Represents a single order the agent wants to execute. Contains all information
    needed by the execution engine to simulate the trade.

    Attributes:
        market_id: Which market this order is for.
        side: "buy" to go long, "sell" to go short.
        order_type: "market" (immediate execution) or "limit" (price-specific).
        size: Number of units to trade (probability-weighted dollars typically).
        limit_price: Required for limit orders; ignored for market orders.
            Set to the best bid (for buy limit) or best ask (for sell limit).
        rationale: Human-readable explanation of why agent proposed this order.
            E.g., "edge=0.15, order_type=limit due to 4% spread".
        split_sizes: If non-empty, split this order into these sized pieces.
            E.g., [10.0, 10.0, 10.0] for 3-way split of 30-unit order.

    Example:
        >>> order = ProposedOrder(
        ...     market_id="politics-2025-03",
        ...     side="buy",
        ...     order_type="limit",
        ...     size=20.0,
        ...     limit_price=0.55,
        ...     rationale="edge=0.15, deep book, use limit for passive fill",
        ...     split_sizes=[10.0, 10.0]  # Split into 2 pieces
        ... )
    """

    market_id: str
    side: str
    order_type: str
    size: float
    limit_price: float | None
    rationale: str
    split_sizes: list[float] = field(default_factory=list)


class ExecutionStrategy:
    """Mutable execution policy that agents can iteratively refine.

    This class encapsulates all decisions about order type, sizing, and order
    splitting. Designed to be overridden in subclasses or via monkey-patching
    for experimentation.

    Example:
        >>> strategy = ExecutionStrategy()
        >>> order_type = strategy.decide_order_type(
        ...     edge=0.10,
        ...     spread_pct=0.02,
        ...     liquidity_depth=100.0,
        ...     time_to_expiry_hours=24.0,
        ...     aggressive_edge=0.12,
        ...     mid_price=0.50
        ... )
        >>> # Returns "limit" (edge doesn't justify market order cost)

        >>> size = strategy.calculate_trade_size(
        ...     edge=0.10,
        ...     bankroll=1000.0,
        ...     liquidity_depth=150.0,
        ...     config=AgentConfig()
        ... )
        >>> # Returns ~20 (scaled by edge, limited by risk/depth)
    """

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
        """Spread-aware order type selection using edge-to-spread ratio logic.

        Key principle: Use market orders when edge significantly exceeds spread cost,
        otherwise use limit orders to capture the spread instead of paying it.

        Args:
            edge: Absolute edge in probability terms
            spread_pct: Current spread as percentage of mid price
            liquidity_depth: Available liquidity on the relevant side
            time_to_expiry_hours: Time until market expiry
            aggressive_edge: Threshold for considering edge "strong"
            mid_price: Current mid price for spread comparison

        Returns:
            "market" for aggressive execution, "limit" for passive execution
        """
        # Calculate spread in absolute price terms for comparison with edge
        spread_abs = spread_pct * mid_price

        # Edge-to-spread ratio: measures how much edge we have relative to spread cost
        edge_to_spread_ratio = edge / max(spread_abs, EPSILON)

        # Use market orders when edge is strong AND edge-to-spread ratio favors aggression
        # Ratio > 3.0 means edge is at least 3x the spread, making taker fees worthwhile
        if edge >= aggressive_edge and edge_to_spread_ratio >= 3.0:
            return "market"

        # Time urgency: use market orders when time is short and edge is decent
        if time_to_expiry_hours <= 12 and edge >= aggressive_edge * 0.75:
            return "market"

        # Wide spreads with poor liquidity: always use limit orders to avoid excessive slippage
        if spread_pct >= 0.05 and liquidity_depth < 100:
            return "limit"

        # Default to limit orders to capture spread rather than pay it
        return "limit"

    def calculate_trade_size(
        self,
        *,
        edge: float,
        bankroll: float,
        liquidity_depth: float,
        config: AgentConfig,
    ) -> float:
        """Calculate position size given edge, bankroll, and liquidity constraints.

        Position sizing uses three independent constraints, all of which must be satisfied:

        1. Edge scaling: Larger edges → larger positions (up to 2.5x baseline)
        2. Bankroll constraint: Never risk > max_risk_fraction of bankroll
        3. Liquidity constraint: Never take > max_depth_fraction of visible depth

        The final size is the minimum of all three constraints, which ensures conservative
        sizing when conditions are tight.

        Args:
            edge: Absolute edge in probability terms (e.g., 0.10 for 10%).
            bankroll: Current available capital.
            liquidity_depth: Total visible liquidity on the relevant side.
            config: AgentConfig with risk parameters.

        Returns:
            Position size in currency units (probability-weighted dollars typically).

        Example:
            >>> strategy.calculate_trade_size(
            ...     edge=0.10,
            ...     bankroll=1000.0,
            ...     liquidity_depth=200.0,
            ...     config=AgentConfig(
            ...         min_edge=0.05,
            ...         max_risk_fraction=0.02,
            ...         max_position_notional=25.0,
            ...         max_depth_fraction=0.15
            ...     )
            ... )
            >>> # edge_scale = 0.10 / 0.05 = 2.0 (capped at 2.5)
            >>> # bankroll_cap = 1000 * 0.02 * 2.0 = 40
            >>> # depth_cap = 200 * 0.15 = 30
            >>> # final = min(40, 30, 25) = 25.0
        """

        edge_scale = min(max(edge / max(config.min_edge, EPSILON), 1.0), 2.5)
        bankroll_cap = bankroll * config.max_risk_fraction * edge_scale
        depth_cap = liquidity_depth * config.max_depth_fraction
        return max(min(bankroll_cap, depth_cap, config.max_position_notional), 0.0)

    def should_split_order(self, desired_size: float, order_book: OrderBook, config: AgentConfig) -> bool:
        """Split outsized orders relative to visible depth.

        Args:
            desired_size: Total order size to evaluate
            order_book: Current order book state
            config: Agent configuration with split thresholds

        Returns:
            True if order should be split, False otherwise
        """

        available_depth = max(order_book.get_total_depth("buy"), order_book.get_total_depth("sell"), 1.0)
        return desired_size > available_depth * config.split_threshold_fraction

    def split_order(self, desired_size: float, slices: int = 3) -> list[float]:
        """Create a flat TWAP-like schedule.

        Args:
            desired_size: Total size to split
            slices: Number of slices to divide into

        Returns:
            List of order sizes
        """

        if desired_size <= 0 or slices <= 1:
            return [desired_size]
        chunk = desired_size / slices
        return [chunk] * (slices - 1) + [desired_size - chunk * (slices - 1)]

    def calculate_limit_price(
        self,
        *,
        side: str,
        order_book: OrderBook,
        mid_price: float,
        improvement_ticks: float,
    ) -> float:
        """
        Calculate intelligent limit order price with price improvement.

        Strategy: Place limit orders inside the spread to improve fill probability
        while still capturing spread value.

        Args:
            side: "buy" or "sell"
            order_book: Current order book state
            mid_price: Current mid price
            improvement_ticks: Number of ticks to improve beyond best bid/ask (in cents)

        Returns:
            Limit price with price improvement applied
        """
        best_bid = order_book.bids[0].price if order_book.bids else mid_price
        best_ask = order_book.asks[0].price if order_book.asks else mid_price

        # Convert ticks (cents) to price improvement
        tick_size = 0.01  # 1 cent tick size for prediction markets
        improvement = improvement_ticks * tick_size

        if side == "buy":
            # Improve bid: bid slightly higher than current best bid
            # This increases fill probability while still better than market price
            improved_price = best_bid + improvement
            # Cap at mid price to avoid crossing the spread completely
            return min(improved_price, mid_price)
        else:  # sell
            # Improve ask: ask slightly lower than current best ask
            improved_price = best_ask - improvement
            # Cap at mid price to avoid crossing the spread completely
            return max(improved_price, mid_price)


class AutoPredictAgent:
    """Minimal agent template focused on edge, liquidity, and execution quality."""

    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig()
        self.execution = ExecutionStrategy()

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "AutoPredictAgent":
        """Create agent from strategy config mapping with validation.

        Validates that all config values are within reasonable ranges and positive.
        """

        min_edge = float(data.get("min_edge", AgentConfig.min_edge))
        aggressive_edge = float(data.get("aggressive_edge", AgentConfig.aggressive_edge))
        max_risk_fraction = float(data.get("max_risk_fraction", AgentConfig.max_risk_fraction))
        max_position_notional = float(data.get("max_position_notional", AgentConfig.max_position_notional))
        min_book_liquidity = float(data.get("min_book_liquidity", AgentConfig.min_book_liquidity))
        max_spread_pct = float(data.get("max_spread_pct", AgentConfig.max_spread_pct))
        max_depth_fraction = float(data.get("max_depth_fraction", AgentConfig.max_depth_fraction))
        split_threshold_fraction = float(
            data.get("split_threshold_fraction", AgentConfig.split_threshold_fraction)
        )
        passive_requote_fraction = float(
            data.get("passive_requote_fraction", AgentConfig.passive_requote_fraction)
        )
        limit_price_improvement_ticks = float(
            data.get("limit_price_improvement_ticks", AgentConfig.limit_price_improvement_ticks)
        )

        # Validate all values are positive
        if min_edge <= 0:
            raise ValueError(f"min_edge must be positive, got {min_edge}")
        if aggressive_edge <= 0:
            raise ValueError(f"aggressive_edge must be positive, got {aggressive_edge}")
        if max_risk_fraction <= 0 or max_risk_fraction > 0.5:
            raise ValueError(f"max_risk_fraction must be in (0, 0.5], got {max_risk_fraction}")
        if max_position_notional <= 0:
            raise ValueError(f"max_position_notional must be positive, got {max_position_notional}")
        if min_book_liquidity < 0:
            raise ValueError(f"min_book_liquidity must be non-negative, got {min_book_liquidity}")
        if max_spread_pct <= 0 or max_spread_pct > 1.0:
            raise ValueError(f"max_spread_pct must be in (0, 1.0], got {max_spread_pct}")
        if max_depth_fraction <= 0 or max_depth_fraction > 1.0:
            raise ValueError(f"max_depth_fraction must be in (0, 1.0], got {max_depth_fraction}")
        if split_threshold_fraction <= 0 or split_threshold_fraction > 1.0:
            raise ValueError(f"split_threshold_fraction must be in (0, 1.0], got {split_threshold_fraction}")
        if passive_requote_fraction < 0 or passive_requote_fraction > 1.0:
            raise ValueError(f"passive_requote_fraction must be in [0, 1.0], got {passive_requote_fraction}")
        if limit_price_improvement_ticks < 0:
            raise ValueError(f"limit_price_improvement_ticks must be non-negative, got {limit_price_improvement_ticks}")

        return cls(
            AgentConfig(
                min_edge=min_edge,
                aggressive_edge=aggressive_edge,
                max_risk_fraction=max_risk_fraction,
                max_position_notional=max_position_notional,
                min_book_liquidity=min_book_liquidity,
                max_spread_pct=max_spread_pct,
                max_depth_fraction=max_depth_fraction,
                split_threshold_fraction=split_threshold_fraction,
                passive_requote_fraction=passive_requote_fraction,
                limit_price_improvement_ticks=limit_price_improvement_ticks,
            )
        )

    def evaluate_market(self, market: MarketState, bankroll: float) -> ProposedOrder | None:
        """Return an order proposal when the market clears basic gating rules."""

        edge = market.fair_prob - market.market_prob
        abs_edge = abs(edge)
        book = market.order_book
        mid = book.get_mid_price()
        spread_pct = book.get_spread() / max(mid, EPSILON)
        liquidity_depth = book.get_total_depth("buy") if edge > 0 else book.get_total_depth("sell")

        if abs_edge < self.config.min_edge:
            return None
        if liquidity_depth < self.config.min_book_liquidity:
            return None
        if spread_pct > self.config.max_spread_pct and abs_edge < self.config.aggressive_edge:
            return None

        order_type = self.execution.decide_order_type(
            edge=abs_edge,
            spread_pct=spread_pct,
            liquidity_depth=liquidity_depth,
            time_to_expiry_hours=market.time_to_expiry_hours,
            aggressive_edge=self.config.aggressive_edge,
            mid_price=mid,
        )
        size = self.execution.calculate_trade_size(
            edge=abs_edge,
            bankroll=bankroll,
            liquidity_depth=liquidity_depth,
            config=self.config,
        )
        if size <= 0:
            return None

        side = "buy" if edge > 0 else "sell"
        limit_price = None
        if order_type == "limit":
            # Validate order book before accessing it
            if book.bids or book.asks:
                limit_price = self.execution.calculate_limit_price(
                    side=side,
                    order_book=book,
                    mid_price=mid,
                    improvement_ticks=self.config.limit_price_improvement_ticks,
                )
            else:
                # Empty order book - use mid price as fallback
                limit_price = mid

        split_sizes = []
        if self.execution.should_split_order(size, book, self.config):
            split_sizes = self.execution.split_order(size)

        rationale = (
            f"edge={abs_edge:.3f}, spread_pct={spread_pct:.3f}, depth={liquidity_depth:.1f}, "
            f"expiry_h={market.time_to_expiry_hours:.1f}, order_type={order_type}"
        )
        return ProposedOrder(
            market_id=market.market_id,
            side=side,
            order_type=order_type,
            size=size,
            limit_price=limit_price,
            rationale=rationale,
            split_sizes=split_sizes,
        )

    def analyze_performance(self, metrics: dict[str, Any], guidance: str) -> dict[str, str]:
        """Identify the dominant weakness from a metrics snapshot.

        Args:
            metrics: Dictionary of execution and performance metrics
            guidance: Optional guidance text for analysis

        Returns:
            Dictionary with identified weakness and hypothesis
        """

        avg_slippage = float(metrics.get("avg_slippage_bps", 0.0) or 0.0)
        fill_rate = float(metrics.get("fill_rate", 0.0) or 0.0)
        brier = float(metrics.get("brier_score", 0.0) or 0.0)
        max_drawdown = float(metrics.get("max_drawdown", 0.0) or 0.0)

        if avg_slippage > 15.0:
            return {"weakness": "execution_quality", "hypothesis": "Use passive orders more selectively and split size."}
        if fill_rate < 0.35:
            return {"weakness": "limit_fill_quality", "hypothesis": "Passive quoting is too timid or too small."}
        if brier > 0.20:
            return {"weakness": "calibration", "hypothesis": "Forecasts are too confident relative to realized outcomes."}
        if max_drawdown > 75.0:
            return {"weakness": "risk", "hypothesis": "Sizing is too large for edge quality and liquidity."}
        return {"weakness": "selection", "hypothesis": "Tighten filters to avoid low-edge churn."}

    def propose_improvement(self, current_config: dict[str, Any], metrics: dict[str, Any], guidance: str) -> dict[str, str]:
        """Return a lightweight improvement suggestion for higher-level agents.

        Args:
            current_config: Current agent configuration
            metrics: Dictionary of execution and performance metrics
            guidance: Optional guidance text for analysis

        Returns:
            Dictionary with improvement summary and hypothesis
        """

        analysis = self.analyze_performance(metrics, guidance)
        return {
            "summary": f"Focus next iteration on {analysis['weakness']}.",
            "hypothesis": analysis["hypothesis"],
        }
