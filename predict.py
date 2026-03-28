#!/usr/bin/env python3
"""Scan live Polymarket markets, show real data, find edges.

What this does:
  1. Fetches active markets + real order books from Polymarket (no auth needed)
  2. Fetches events to find multi-outcome groups where prices should sum to ~1
  3. Flags markets where sibling prices are inconsistent (real structural edges)
  4. Shows you the data you need to form your own opinion on fair_prob
  5. Optionally runs the AutoPredict agent with your fair_prob override

What this does NOT do:
  - Pretend a formula can outpredict the market
  - Generate fake edge from microstructure artifacts

Usage:
    python predict.py                           # scan top markets by volume
    python predict.py --events                  # show events with sibling mispricing
    python predict.py --fair 0.60 CONDITION_ID  # run agent with your fair_prob
    python predict.py --verbose                 # show order book details
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

sys.path.insert(0, ".")

from autopredict.markets.polymarket import PolymarketAdapter, PolymarketMarket, PolymarketEvent


# ---------------------------------------------------------------------------
# Market analysis — real data, no fake edges
# ---------------------------------------------------------------------------

@dataclass
class MarketReport:
    """Everything you need to decide if a market is mispriced."""
    condition_id: str
    question: str
    market_prob: float
    best_bid: float
    best_ask: float
    spread: float
    spread_pct: float
    depth_bid: float          # total $ on bid side
    depth_ask: float          # total $ on ask side
    depth_imbalance: float    # (bid_depth - ask_depth) / total — positive = more buying support
    liquidity: float
    volume_24h: float
    hours_to_expiry: float
    category: str
    book_levels: int
    # Event-level analysis (if applicable)
    event_title: str | None = None
    sibling_prob_sum: float | None = None  # all sibling YES prices summed
    implied_overround: float | None = None # how far prob_sum is from 1.0
    arb_edge: float | None = None          # structural edge from overround


def analyze_market(
    market: PolymarketMarket,
    event_title: str | None = None,
    sibling_probs: list[float] | None = None,
) -> MarketReport:
    """Analyze a market using only real, observable data."""
    bids = market.order_book_bids
    asks = market.order_book_asks

    depth_bid = sum(s for _, s in bids) if bids else 0.0
    depth_ask = sum(s for _, s in asks) if asks else 0.0
    total_depth = depth_bid + depth_ask
    depth_imbalance = (depth_bid - depth_ask) / total_depth if total_depth > 0 else 0.0

    spread_pct = market.spread / market.market_prob if market.market_prob > 0.01 else 0.0

    # Parse expiry
    try:
        expiry = datetime.fromisoformat(market.end_date.replace("Z", "+00:00"))
        hours_to_expiry = max((expiry - datetime.now(timezone.utc)).total_seconds() / 3600, 0)
    except (ValueError, AttributeError):
        hours_to_expiry = -1.0

    # Event-level: check if sibling prices reveal structural mispricing
    sibling_prob_sum = None
    implied_overround = None
    arb_edge = None
    if sibling_probs is not None and len(sibling_probs) >= 2:
        sibling_prob_sum = sum(sibling_probs)
        implied_overround = sibling_prob_sum - 1.0
        # If prices sum to > 1.0, there's overround (bookmaker vig)
        # The edge per market is roughly overround / N (distributed evenly)
        # Negative overround (< 1.0) means free money on a portfolio of all YES tokens
        if abs(implied_overround) > 0.01:
            arb_edge = -implied_overround  # negative overround = positive edge for YES buyers

    return MarketReport(
        condition_id=market.condition_id,
        question=market.question,
        market_prob=market.market_prob,
        best_bid=market.best_bid,
        best_ask=market.best_ask,
        spread=market.spread,
        spread_pct=spread_pct,
        depth_bid=depth_bid,
        depth_ask=depth_ask,
        depth_imbalance=depth_imbalance,
        liquidity=market.liquidity,
        volume_24h=market.volume_24h,
        hours_to_expiry=hours_to_expiry,
        category=market.category,
        book_levels=len(bids) + len(asks),
        event_title=event_title,
        sibling_prob_sum=sibling_prob_sum,
        implied_overround=implied_overround,
        arb_edge=arb_edge,
    )


# ---------------------------------------------------------------------------
# Agent integration
# ---------------------------------------------------------------------------

def run_agent(
    market: PolymarketMarket,
    fair_prob: float,
    bankroll: float = 1000.0,
) -> dict | None:
    """Run the AutoPredict agent on a real market with an explicit fair_prob."""
    from autopredict.agent import AutoPredictAgent, AgentConfig, MarketState
    from autopredict.market_env import BookLevel, OrderBook

    bids = [BookLevel(price=p, size=s) for p, s in market.order_book_bids]
    asks = [BookLevel(price=p, size=s) for p, s in market.order_book_asks]
    book = OrderBook(market_id=market.condition_id, bids=bids, asks=asks)

    try:
        expiry = datetime.fromisoformat(market.end_date.replace("Z", "+00:00"))
        hours = max((expiry - datetime.now(timezone.utc)).total_seconds() / 3600, 0)
    except (ValueError, AttributeError):
        hours = 24.0

    state = MarketState(
        market_id=market.condition_id,
        market_prob=market.market_prob,
        fair_prob=fair_prob,
        time_to_expiry_hours=hours,
        order_book=book,
        metadata={"category": market.category, "question": market.question},
    )

    agent = AutoPredictAgent(AgentConfig())
    proposal = agent.evaluate_market(state, bankroll)

    if proposal is None:
        return None

    return {
        "side": proposal.side,
        "order_type": proposal.order_type,
        "size": round(proposal.size, 2),
        "limit_price": round(proposal.limit_price, 4) if proposal.limit_price else None,
        "rationale": proposal.rationale,
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_scan(adapter: PolymarketAdapter, args: argparse.Namespace) -> None:
    """Scan markets, show real data."""
    print("Fetching markets...", file=sys.stderr)
    markets = adapter.get_active_markets(
        limit=100,
        min_liquidity=args.min_liquidity,
        category=args.category,
    )
    print(f"Got {len(markets)} markets, fetching order books...", file=sys.stderr)

    reports: list[tuple[MarketReport, PolymarketMarket]] = []
    for i, mkt in enumerate(markets):
        mkt = _enrich_with_clob_book(adapter, mkt)
        report = analyze_market(mkt)
        reports.append((report, mkt))
        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(markets)}]", file=sys.stderr)

    # Sort by 24h volume (most active first)
    reports.sort(key=lambda x: x[0].volume_24h, reverse=True)
    reports = reports[:args.top]

    if args.json:
        _print_json(reports, args)
        return

    print()
    print(f"{'Question':<50} {'Price':>6} {'Bid':>6} {'Ask':>6} {'Sprd%':>6} "
          f"{'BidDepth':>9} {'AskDepth':>9} {'Imbal':>6} {'Vol24h':>10} {'Expiry':>8}")
    print("-" * 130)

    for report, mkt in reports:
        q = report.question[:49]
        expiry_str = f"{report.hours_to_expiry:.0f}h" if report.hours_to_expiry >= 0 else "?"
        print(
            f"{q:<50} {report.market_prob:>5.1%} {report.best_bid:>5.3f} "
            f"{report.best_ask:>5.3f} {report.spread_pct:>5.1%} "
            f"${report.depth_bid:>8,.0f} ${report.depth_ask:>8,.0f} "
            f"{report.depth_imbalance:>+5.0%} ${report.volume_24h:>9,.0f} {expiry_str:>8}"
        )

        if args.verbose:
            print(f"    id: {report.condition_id}")
            print(f"    book: {report.book_levels} levels, "
                  f"liq=${report.liquidity:,.0f}, cat={report.category}")

    print()
    print("All data live from Polymarket Gamma API + CLOB order books.")
    print("Use --fair <prob> <condition_id> to test your own prediction.")


def cmd_events(adapter: PolymarketAdapter, args: argparse.Namespace) -> None:
    """Show events where sibling market prices don't sum to 1 (structural edges)."""
    print("Fetching events...", file=sys.stderr)
    events = adapter.get_events(limit=50, active=True)
    print(f"Got {len(events)} events", file=sys.stderr)

    # Only show events with 2+ markets (multi-outcome)
    multi_events: list[tuple[PolymarketEvent, float]] = []
    for event in events:
        if len(event.markets) < 2:
            continue
        prob_sum = sum(m.market_prob for m in event.markets)
        overround = prob_sum - 1.0
        multi_events.append((event, overround))

    # Sort by how close prob_sum is to 1.0 — these are most likely
    # mutually exclusive events where normalization makes sense.
    # Events with prob_sum >> 1 (like "which countries qualify") are
    # likely non-exclusive (multiple can be YES).
    multi_events.sort(key=lambda x: abs(x[1]))
    multi_events = multi_events[:args.top]

    if not multi_events:
        print("No multi-outcome events found.")
        return

    print()
    for event, overround in multi_events:
        prob_sum = overround + 1.0
        n = len(event.markets)
        # Heuristic: if prob_sum is close to 1.0, likely mutually exclusive
        # If prob_sum >> 1, likely non-exclusive (e.g., "which countries qualify")
        if prob_sum > 1.5:
            exclusivity = "NON-EXCLUSIVE (multiple YES possible, normalization not meaningful)"
        elif prob_sum < 0.5:
            exclusivity = "STALE/DEAD (markets may be expired)"
        else:
            exclusivity = "LIKELY EXCLUSIVE" + (
                f" — overround {overround:+.1%}" if overround > 0.02
                else f" — underround {overround:+.1%}" if overround < -0.02
                else " — well-priced"
            )
        print(f"Event: {event.title}")
        print(f"  {n} markets, prob_sum={prob_sum:.3f} — {exclusivity}")
        print()

        for mkt in sorted(event.markets, key=lambda m: m.market_prob, reverse=True):
            implied_fair = mkt.market_prob / prob_sum if prob_sum > 0 else mkt.market_prob
            adj = implied_fair - mkt.market_prob
            print(f"    {mkt.market_prob:>5.1%}  (fair≈{implied_fair:>5.1%}, adj={adj:>+.1%})  {mkt.question[:60]}")

        print()

    print("'fair' = market price normalized so all siblings sum to 1.0")
    print("Negative overround means buying all YES tokens costs < $1 → structural arb.")
    print("Positive overround is normal (bookmaker vig), but extreme values may be stale.")


def cmd_fair(adapter: PolymarketAdapter, args: argparse.Namespace) -> None:
    """Run the agent on a specific market with your fair_prob."""
    if not args.condition_id:
        print("Usage: predict.py --fair <probability> <condition_id>", file=sys.stderr)
        return

    print(f"Fetching market {args.condition_id}...", file=sys.stderr)
    mkt = adapter.get_market(args.condition_id)
    if mkt is None:
        print(f"Market not found: {args.condition_id}", file=sys.stderr)
        return

    mkt = _enrich_with_clob_book(adapter, mkt)
    report = analyze_market(mkt)

    print()
    print(f"Question: {mkt.question}")
    print(f"Market price:    {report.market_prob:.1%}")
    print(f"Your fair_prob:  {args.fair_prob:.1%}")
    print(f"Edge:            {args.fair_prob - report.market_prob:+.1%}")
    print(f"Best bid/ask:    {report.best_bid:.3f} / {report.best_ask:.3f} (spread {report.spread_pct:.1%})")
    print(f"Book depth:      ${report.depth_bid:,.0f} bid / ${report.depth_ask:,.0f} ask (imbalance {report.depth_imbalance:+.0%})")
    print(f"24h volume:      ${report.volume_24h:,.0f}")
    print(f"Liquidity:       ${report.liquidity:,.0f}")
    print(f"Expiry:          {report.hours_to_expiry:.0f}h")
    print()

    trade = run_agent(mkt, args.fair_prob)
    if trade:
        print(f"Agent says: {trade['side'].upper()} {trade['order_type']}, "
              f"size=${trade['size']:.2f}", end="")
        if trade['limit_price']:
            print(f", limit={trade['limit_price']:.4f}", end="")
        print()
        print(f"Rationale: {trade['rationale']}")
    else:
        print("Agent says: SKIP (doesn't pass filters at current config)")
        print("  This could mean: edge too small, spread too wide, or book too thin.")
        print("  Try adjusting strategy_configs/baseline.json if you're confident in your fair_prob.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enrich_with_clob_book(
    adapter: PolymarketAdapter, market: PolymarketMarket
) -> PolymarketMarket:
    """Replace Gamma placeholder book with real CLOB order book."""
    if not market.token_id_yes:
        return market
    try:
        book = adapter.get_order_book(market.token_id_yes)
        return PolymarketMarket(
            condition_id=market.condition_id,
            question=market.question,
            token_id_yes=market.token_id_yes,
            token_id_no=market.token_id_no,
            market_prob=market.market_prob,
            volume_24h=market.volume_24h,
            liquidity=market.liquidity,
            end_date=market.end_date,
            active=market.active,
            closed=market.closed,
            category=market.category,
            best_bid=book["bids"][0][0] if book["bids"] else market.best_bid,
            best_ask=book["asks"][0][0] if book["asks"] else market.best_ask,
            spread=(book["asks"][0][0] - book["bids"][0][0])
                if book["bids"] and book["asks"]
                else market.spread,
            order_book_bids=book["bids"],
            order_book_asks=book["asks"],
            metadata=market.metadata,
        )
    except (ConnectionError, KeyError, IndexError, Exception):
        return market


def _print_json(reports: list[tuple[MarketReport, PolymarketMarket]], args) -> None:
    output = []
    for report, mkt in reports:
        output.append({
            "condition_id": report.condition_id,
            "question": report.question,
            "market_prob": round(report.market_prob, 4),
            "best_bid": round(report.best_bid, 4),
            "best_ask": round(report.best_ask, 4),
            "spread_pct": round(report.spread_pct, 4),
            "depth_bid": round(report.depth_bid, 0),
            "depth_ask": round(report.depth_ask, 0),
            "depth_imbalance": round(report.depth_imbalance, 3),
            "volume_24h": round(report.volume_24h, 0),
            "liquidity": round(report.liquidity, 0),
            "hours_to_expiry": round(report.hours_to_expiry, 1),
            "category": report.category,
            "book_levels": report.book_levels,
        })
    print(json.dumps(output, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan Polymarket for real data and structural edges"
    )
    parser.add_argument("--category", type=str, default=None, help="Filter by category")
    parser.add_argument("--min-liquidity", type=float, default=1000.0, help="Min liquidity ($)")
    parser.add_argument("--top", type=int, default=15, help="Show top N results")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show extra details")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--events", action="store_true",
                        help="Show multi-outcome events with overround analysis")
    parser.add_argument("--fair", type=float, default=None, dest="fair_prob",
                        help="Your fair probability estimate (0-1)")
    parser.add_argument("condition_id", nargs="?", default=None,
                        help="Condition ID for --fair mode")

    args = parser.parse_args()

    adapter = PolymarketAdapter()

    if args.fair_prob is not None:
        cmd_fair(adapter, args)
    elif args.events:
        cmd_events(adapter, args)
    else:
        cmd_scan(adapter, args)


if __name__ == "__main__":
    main()
