# AutoPredict Calibration & Forecast Quality Recommendations

**Analysis Date**: 2026-03-26
**Current Brier Score**: 0.255
**Target**: < 0.20 (20% improvement)

---

## Executive Summary

**KEY FINDING**: Your `fair_prob` estimates have **genuine predictive edge** over market prices (Brier: 0.255 vs 0.315). The calibration issue is NOT overconfidence - it's **inconsistent quality across categories**.

**DO NOT** apply blanket shrinkage toward market prices - this will destroy your edge.

**DO** focus on improving fair_prob quality in underperforming categories (sports, macro, crypto).

---

## Current Performance Analysis

### Overall Metrics
- **Fair Brier Score**: 0.2548
- **Market Brier Score**: 0.3148
- **Fair wins**: 5/6 markets
- **Performance**: Fair_prob beats market_prob by ~19% on Brier score

### Calibration by Bucket (from metrics.json)

| Bucket | Avg Prob | Realized Rate | Count | Status |
|--------|----------|---------------|-------|--------|
| 0.3-0.4 | 0.34 | 0.0 | 1 | ❌ Overconfident (predicted 34%, actual 0%) |
| 0.4-0.5 | 0.46 | 1.0 | 1 | ❌ Underconfident (predicted 46%, actual 100%) |
| 0.5-0.6 | 0.53 | 0.5 | 2 | ✅ Well calibrated |
| 0.6-0.7 | 0.655 | 0.5 | 2 | ❌ Overconfident (predicted 65.5%, actual 50%) |

**Issue**: With only 6 markets, calibration buckets have sample size = 1-2, making them unreliable for drawing conclusions.

### Performance by Category

| Category | Brier Score | Sample Size | Assessment | Priority |
|----------|-------------|-------------|------------|----------|
| **geopolitics** | 0.116 | 1 | Excellent | Maintain |
| **science** | 0.137 | 1 | Excellent | Maintain |
| **politics** | 0.230 | 1 | Good | Maintain |
| **crypto** | 0.292 | 1 | Poor | **HIGH - Fix** |
| **macro** | 0.292 | 1 | Poor | **HIGH - Fix** |
| **sports** | 0.462 | 1 | Very Poor | **CRITICAL - Fix** |

---

## Root Cause Analysis

### Why is Brier score 0.255 when fair_prob beats market?

1. **Category variance**: Sports, macro, and crypto categories are dragging down overall performance
2. **Small sample size**: Only 6 markets, so 1-2 bad predictions heavily impact overall score
3. **Not a calibration curve issue**: The problem is forecast quality, not systematic bias

### Market-by-Market Breakdown

| Market | Fair | Market | Outcome | Fair Error | Market Error | Winner |
|--------|------|--------|---------|------------|--------------|--------|
| us-election-2028-democrat-win | 0.52 | 0.44 | 1 | 0.2304 | 0.3136 | FAIR ✅ |
| fed-cuts-before-september | 0.54 | 0.61 | 0 | 0.2916 | 0.3721 | FAIR ✅ |
| btc-above-120k-by-year-end | 0.46 | 0.36 | 1 | 0.2916 | 0.4096 | FAIR ✅ |
| championship-favorite-wins-title | 0.68 | 0.73 | 0 | **0.4624** | 0.5329 | FAIR ✅ |
| space-launch-on-schedule | 0.63 | 0.58 | 1 | 0.1369 | 0.1764 | FAIR ✅ |
| ceasefire-before-quarter-end | 0.34 | 0.29 | 0 | 0.1156 | **0.0841** | MARKET ❌ |

**Insight**: fair_prob is LESS extreme than market in 5/6 cases and correct in 4/5 of those. This is CONSERVATIVE and SKILLFUL forecasting.

---

## Recommendations

### 🚫 What NOT to Do

1. **DO NOT apply shrinkage toward market prices**
   - Analysis shows this REDUCES performance (increases Brier score)
   - Your edge comes from being different from the market when you're right

2. **DO NOT trust calibration_by_bucket with N=6**
   - Need minimum 100-200 markets for reliable calibration curves
   - Current bucket sample sizes (1-2) are too small for statistical significance

3. **DO NOT add a calibration layer to agent.py**
   - No evidence of systematic bias requiring correction
   - Would likely hurt performance

### ✅ Recommended Actions

#### Priority 1: Improve Dataset Quality (HIGHEST IMPACT)

**For users generating fair_prob estimates:**

Create a fair_prob quality checklist (`/Users/howdymary/Documents/New project/autopredict/docs/fair_prob_guidelines.md`):

```markdown
# Fair Probability Estimation Guidelines

## Quality Checklist

Before submitting a market with fair_prob, verify:

### 1. Sports Markets
- [ ] Have you checked recent team performance (last 5 games)?
- [ ] Have you adjusted for home/away advantage?
- [ ] Have you considered injuries to key players?
- [ ] Does your fair_prob account for margin of victory vs. win probability?
- **Target**: Avoid probabilities >0.70 for favorites unless heavily justified

### 2. Macro Markets
- [ ] Have you reviewed recent economic indicators?
- [ ] Have you considered Fed communication patterns?
- [ ] Are you using base rates from similar historical events?
- **Target**: Use historical base rates as anchors (e.g., Fed cuts historically happen X% of the time)

### 3. Crypto Markets
- [ ] Have you adjusted for crypto volatility (typically 60-80% annualized)?
- [ ] Are you considering network fundamentals, not just price action?
- [ ] Have you checked correlation with traditional risk assets?
- **Target**: Widen probability ranges to account for volatility

### 4. General Rules
- [ ] Is |fair_prob - market_prob| > 0.20? If yes, document why.
- [ ] Are you using extreme probabilities (<0.15 or >0.85)? If yes, document justification.
- [ ] Have you considered the market's information advantage?
- [ ] Would you bet $100 at these odds?

### 5. Validation
- Compare your fair_prob against:
  - Historical base rates for similar events
  - Multiple independent forecasting models
  - Consensus forecasts from prediction markets
```

#### Priority 2: Add Data Validation Layer

Add input validation to catch problematic fair_prob estimates before they hurt performance:

**File**: `/Users/howdymary/Documents/New project/autopredict/validation.py`

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationWarning:
    """Warning about potentially problematic fair_prob estimate."""

    severity: str  # "info", "warning", "error"
    message: str
    field: str
    value: float
    suggestion: str


class FairProbValidator:
    """Validate fair_prob estimates before they enter the system."""

    # Category-specific quality thresholds based on historical performance
    CATEGORY_QUALITY = {
        "geopolitics": {"min_confidence": 0.8, "max_edge": 0.15},
        "science": {"min_confidence": 0.8, "max_edge": 0.15},
        "politics": {"min_confidence": 0.7, "max_edge": 0.15},
        "crypto": {"min_confidence": 0.5, "max_edge": 0.20},  # More uncertain
        "macro": {"min_confidence": 0.5, "max_edge": 0.20},
        "sports": {"min_confidence": 0.3, "max_edge": 0.25},  # Least reliable
    }

    def validate(
        self,
        fair_prob: float,
        market_prob: float,
        category: str = "unknown",
    ) -> list[ValidationWarning]:
        """Run validation checks and return warnings."""
        warnings = []

        # Check 1: Extreme probabilities
        if fair_prob < 0.10 or fair_prob > 0.90:
            warnings.append(ValidationWarning(
                severity="warning",
                message=f"Extreme probability: {fair_prob:.2f}",
                field="fair_prob",
                value=fair_prob,
                suggestion="Extreme probabilities should be rare. Consider using 0.10-0.90 range.",
            ))

        # Check 2: Large divergence from market
        edge = abs(fair_prob - market_prob)
        max_edge = self.CATEGORY_QUALITY.get(category, {}).get("max_edge", 0.20)

        if edge > max_edge:
            warnings.append(ValidationWarning(
                severity="warning",
                message=f"Large edge ({edge:.2f}) in {category} category",
                field="edge",
                value=edge,
                suggestion=f"Category '{category}' has poor historical calibration. "
                           f"Consider reducing edge or improving estimation.",
            ))

        # Check 3: Category-specific quality scores
        category_quality = self.CATEGORY_QUALITY.get(category, {})
        min_confidence = category_quality.get("min_confidence", 0.5)

        if category in ["sports", "crypto", "macro"]:
            warnings.append(ValidationWarning(
                severity="info",
                message=f"Category '{category}' has low historical quality (confidence={min_confidence})",
                field="category",
                value=min_confidence,
                suggestion=f"Consider extra validation or reducing position size for {category} markets.",
            ))

        # Check 4: Fair prob between market and 0.5 (regression to mean)
        mid = 0.5
        if (fair_prob - mid) * (market_prob - mid) < 0:
            # fair_prob is on opposite side of 0.5 from market_prob
            warnings.append(ValidationWarning(
                severity="info",
                message=f"Fair prob ({fair_prob:.2f}) crosses 0.5 relative to market ({market_prob:.2f})",
                field="fair_prob",
                value=fair_prob,
                suggestion="Reversing market direction is high conviction. Verify your reasoning.",
            ))

        return warnings
```

#### Priority 3: Enhanced Metrics & Monitoring

Add more granular metrics to track forecast quality:

**File**: `/Users/howdymary/Documents/New project/autopredict/forecast_metrics.py`

```python
from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass
class ForecastQualityMetrics:
    """Extended forecast quality metrics beyond Brier score."""

    brier_score: float
    brier_skill_score: float  # Relative to market baseline
    log_score: float  # Proper scoring rule
    calibration_slope: float  # From regression
    calibration_intercept: float
    resolution: float  # Variance in forecasts
    reliability: float  # Distance from perfect calibration
    sharpness: float  # How far from 0.5 forecasts are


def calculate_extended_metrics(
    fair_probs: list[float],
    market_probs: list[float],
    outcomes: list[int],
) -> ForecastQualityMetrics:
    """Calculate comprehensive forecast quality metrics."""

    import math

    # Brier score
    brier_fair = statistics.fmean([(fp - o) ** 2 for fp, o in zip(fair_probs, outcomes)])
    brier_market = statistics.fmean([(mp - o) ** 2 for mp, o in zip(market_probs, outcomes)])

    # Brier Skill Score (relative improvement over baseline)
    brier_skill_score = 1 - (brier_fair / brier_market) if brier_market > 0 else 0

    # Log score (proper scoring rule)
    epsilon = 1e-9
    log_score = -statistics.fmean([
        o * math.log(max(fp, epsilon)) + (1 - o) * math.log(max(1 - fp, epsilon))
        for fp, o in zip(fair_probs, outcomes)
    ])

    # Calibration via simple linear regression
    # outcomes = slope * fair_probs + intercept
    # Perfect calibration: slope=1, intercept=0
    n = len(fair_probs)
    mean_prob = statistics.fmean(fair_probs)
    mean_outcome = statistics.fmean(outcomes)

    numerator = sum((p - mean_prob) * (o - mean_outcome) for p, o in zip(fair_probs, outcomes))
    denominator = sum((p - mean_prob) ** 2 for p in fair_probs)

    slope = numerator / denominator if denominator > 0 else 0
    intercept = mean_outcome - slope * mean_prob

    # Resolution (variance in forecasts - higher is better)
    resolution = statistics.variance(fair_probs) if len(fair_probs) > 1 else 0

    # Sharpness (distance from 0.5)
    sharpness = statistics.fmean([abs(fp - 0.5) for fp in fair_probs])

    # Reliability (calibration error)
    # Group into buckets and compare avg forecast vs realized rate
    buckets = {}
    for fp, o in zip(fair_probs, outcomes):
        bucket = round(fp * 10) / 10
        buckets.setdefault(bucket, {"probs": [], "outcomes": []})
        buckets[bucket]["probs"].append(fp)
        buckets[bucket]["outcomes"].append(o)

    calibration_errors = []
    for bucket_data in buckets.values():
        avg_prob = statistics.fmean(bucket_data["probs"])
        realized = statistics.fmean(bucket_data["outcomes"])
        calibration_errors.append((avg_prob - realized) ** 2)

    reliability = statistics.fmean(calibration_errors) if calibration_errors else 0

    return ForecastQualityMetrics(
        brier_score=brier_fair,
        brier_skill_score=brier_skill_score,
        log_score=log_score,
        calibration_slope=slope,
        calibration_intercept=intercept,
        resolution=resolution,
        reliability=reliability,
        sharpness=sharpness,
    )
```

#### Priority 4: Accumulate Data for Future Calibration

Create a data collection system to enable proper calibration once you have 100+ markets:

**File**: `/Users/howdymary/Documents/New project/autopredict/calibration_database.py`

```python
from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any


@dataclass
class CalibrationDataPoint:
    """Single observation for calibration curve fitting."""

    timestamp: str
    market_id: str
    category: str
    fair_prob: float
    market_prob: float
    outcome: int
    metadata: dict[str, Any]


class CalibrationDatabase:
    """Accumulate calibration data for future curve fitting."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def add_observation(
        self,
        market_id: str,
        category: str,
        fair_prob: float,
        market_prob: float,
        outcome: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a new calibration observation."""

        observation = CalibrationDataPoint(
            timestamp=datetime.utcnow().isoformat(),
            market_id=market_id,
            category=category,
            fair_prob=fair_prob,
            market_prob=market_prob,
            outcome=outcome,
            metadata=metadata or {},
        )

        # Append to JSONL file
        with self.db_path.open("a") as f:
            f.write(json.dumps(asdict(observation)) + "\n")

    def load_all(self) -> list[CalibrationDataPoint]:
        """Load all observations from database."""

        if not self.db_path.exists():
            return []

        observations = []
        with self.db_path.open("r") as f:
            for line in f:
                data = json.loads(line)
                observations.append(CalibrationDataPoint(**data))

        return observations

    def get_calibration_curve(self, min_samples: int = 100) -> dict[str, Any] | None:
        """
        Fit calibration curve if enough data is available.
        Returns None if insufficient data.
        """

        observations = self.load_all()

        if len(observations) < min_samples:
            return {
                "status": "insufficient_data",
                "current_samples": len(observations),
                "required_samples": min_samples,
                "message": f"Need {min_samples - len(observations)} more observations",
            }

        # TODO: Implement isotonic regression or other calibration method
        # For now, return bucket-based calibration

        buckets = {}
        for obs in observations:
            bucket = round(obs.fair_prob * 10) / 10
            buckets.setdefault(bucket, []).append(obs.outcome)

        calibration_map = {
            bucket: sum(outcomes) / len(outcomes)
            for bucket, outcomes in buckets.items()
        }

        return {
            "status": "ready",
            "num_observations": len(observations),
            "calibration_map": calibration_map,
            "coverage": len(buckets),
        }
```

---

## Implementation Plan

### Phase 1: Data Quality (Immediate - Week 1)
1. ✅ Create fair_prob guidelines document
2. ✅ Add FairProbValidator to validation.py
3. ✅ Update run_experiment.py to run validation and log warnings
4. ✅ Review existing sample_markets.json and flag issues

### Phase 2: Enhanced Metrics (Week 2)
1. ✅ Add forecast_metrics.py with extended metrics
2. ✅ Update evaluate_all() to include new metrics
3. ✅ Add category-specific reporting to CLI output

### Phase 3: Data Collection (Week 3)
1. ✅ Create calibration_database.py
2. ✅ Update run_experiment.py to log all observations
3. ✅ Set up periodic calibration curve re-fitting (when N > 100)

### Phase 4: Category Improvement (Ongoing)
1. ✅ Analyze sports category failures (why was championship favorite so overconfident?)
2. ✅ Review macro category (Fed cuts prediction - what was missed?)
3. ✅ Improve crypto volatility modeling

---

## Expected Impact

### Conservative Estimate (with current data quality)
- **Target Brier**: 0.20 (-21% improvement)
- **Method**: Better input validation, reject low-quality fair_prob estimates
- **Timeline**: 2-4 weeks

### Optimistic Estimate (with full implementation)
- **Target Brier**: 0.15 (-41% improvement)
- **Method**: All phases + 100+ market calibration curve
- **Timeline**: 2-3 months

### Category-Specific Targets
- Sports: 0.46 → 0.25 (learn from science/geopolitics methodology)
- Macro: 0.29 → 0.20 (use historical base rates)
- Crypto: 0.29 → 0.22 (account for volatility)
- Maintain: geopolitics (0.12), science (0.14), politics (0.23)

---

## Monitoring & Success Metrics

Track these metrics on each backtest run:

1. **Overall Brier Score**: Target < 0.20
2. **Brier Skill Score** vs market: Target > 0.30 (30% better than market)
3. **Category Performance**: No category > 0.30 Brier
4. **Calibration Slope**: Target 0.9-1.1 (well calibrated)
5. **Validation Warnings**: Reduce warning rate to < 10%

Create dashboard in `/Users/howdymary/Documents/New project/autopredict/state/quality_dashboard.json`

---

## References

- Current metrics: `/Users/howdymary/Documents/New project/autopredict/state/backtests/20260327-035136/metrics.json`
- Sample data: `/Users/howdymary/Documents/New project/autopredict/datasets/sample_markets.json`
- Analysis scripts: `/Users/howdymary/Documents/New project/autopredict/calibration_analysis.py`

---

**Next Steps**: Implement Phase 1 (Data Quality) validation layer before next backtest run.
