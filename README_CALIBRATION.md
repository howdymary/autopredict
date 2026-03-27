# AutoPredict Calibration Improvement Guide

**Last Updated**: 2026-03-26
**Current Brier Score**: 0.255
**Target Brier Score**: < 0.20

---

## Quick Start

### For Users (Creating fair_prob Estimates)

1. **Read the guidelines**: [`docs/fair_prob_guidelines.md`](docs/fair_prob_guidelines.md)
2. **Follow category-specific checklists** for your market type
3. **Run validation** before submitting new markets:

```python
from validation import FairProbValidator

validator = FairProbValidator()
warnings = validator.validate(
    fair_prob=0.65,
    market_prob=0.58,
    category="sports"
)

for warning in warnings:
    print(f"{warning.severity}: {warning.message}")
```

### For Developers (Integrating Validation)

1. **Review the analysis**: [`CALIBRATION_SUMMARY.md`](CALIBRATION_SUMMARY.md)
2. **See example implementation**: [`run_experiment_with_validation.py`](run_experiment_with_validation.py)
3. **Test validation**: `python3 test_validation.py`

---

## Key Findings

### ✅ Good News

Your `fair_prob` estimates **beat market prices** by 19%:
- Fair Brier Score: 0.255
- Market Brier Score: 0.315
- **Fair wins 5/6 markets** ✅

**This means you have genuine edge.** Don't throw it away with over-calibration.

### ❌ The Problem

**Inconsistent quality across categories**:

| Category | Brier Score | Quality | Action Needed |
|----------|-------------|---------|---------------|
| geopolitics | 0.116 | ⭐⭐⭐⭐⭐ Excellent | Maintain |
| science | 0.137 | ⭐⭐⭐⭐⭐ Excellent | Maintain |
| politics | 0.230 | ⭐⭐⭐ Good | Maintain |
| crypto | 0.292 | ⭐ Poor | **Improve** |
| macro | 0.292 | ⭐ Poor | **Improve** |
| sports | 0.462 | ❌ Very Poor | **Critical** |

**Root cause**: Sports, macro, and crypto fair_prob estimates need better methodology.

---

## Solution Overview

### ❌ What NOT to Do

1. **DO NOT shrink toward market prices**
   - Testing showed this WORSENS Brier score
   - Your edge comes from disagreeing with the market when you're right

2. **DO NOT add blanket calibration layer**
   - No systematic bias detected in aggregate
   - Would destroy genuine predictive power

3. **DO NOT trust calibration_by_bucket yet**
   - Only 6 markets = unreliable (need 100+ for calibration curves)

### ✅ What TO Do

**Priority 1: Improve Weak Categories**

Focus on sports, macro, and crypto:
- **Sports**: Avoid over-estimating favorites (>0.70 probability)
- **Macro**: Use historical base rates, not just recent news
- **Crypto**: Account for 60-80% volatility, use wider probability ranges

See [`docs/fair_prob_guidelines.md`](docs/fair_prob_guidelines.md) for detailed checklists.

**Priority 2: Add Input Validation**

Use `validation.py` to catch problematic estimates:

```python
from validation import FairProbValidator

validator = FairProbValidator()
should_reject, warnings = validator.validate_and_log(
    fair_prob=0.75,
    market_prob=0.45,
    market_id="my-market",
    category="sports"
)

if should_reject:
    print("Market rejected due to validation errors")
```

**Priority 3: Collect Data for Future Calibration**

Once you have 100+ markets, fit a proper calibration curve. Until then:
- Log all (fair_prob, outcome) observations
- Monitor calibration by category
- Re-evaluate calibration approach when N > 100

---

## Files Overview

### Analysis & Documentation

- **`CALIBRATION_SUMMARY.md`** - Executive summary of findings (START HERE)
- **`CALIBRATION_RECOMMENDATIONS.md`** - Detailed technical analysis and roadmap
- **`docs/fair_prob_guidelines.md`** - User-facing guidelines for creating fair_prob

### Implementation

- **`validation.py`** - FairProbValidator class for input validation
- **`run_experiment_with_validation.py`** - Example integration with validation
- **`test_validation.py`** - Test validation on sample markets

### Analysis Tools

- **`calibration_analysis.py`** - Shrinkage testing, category analysis
- **`detailed_calibration_report.py`** - Market-by-market breakdown
- **`calibration_recommendations.json`** - Machine-readable recommendations

---

## Testing Validation

Run validation on existing sample markets:

```bash
cd "/Users/howdymary/Documents/New project/autopredict"
python3 test_validation.py
```

**Expected output**:
- 4/6 markets trigger warnings (66.7%)
- All warnings are INFO level (no errors)
- Categories flagged: sports, macro, crypto, politics
- No markets would be rejected (all warnings are informational)

---

## Integration Example

### Before (Original `run_experiment.py`)

```python
# No validation
fair_prob = float(record["fair_prob"])
forecasts.append(ForecastRecord(market_id, fair_prob, outcome))
```

### After (With Validation)

```python
from validation import FairProbValidator

validator = FairProbValidator()

# Validate before using
should_reject, warnings = validator.validate_and_log(
    fair_prob=fair_prob,
    market_prob=market_prob,
    market_id=market_id,
    category=category,
)

if should_reject:
    print(f"Skipping {market_id} due to validation errors")
    continue

# Proceed with validated fair_prob
forecasts.append(ForecastRecord(market_id, fair_prob, outcome))
```

See [`run_experiment_with_validation.py`](run_experiment_with_validation.py) for complete example.

---

## Expected Impact

### Conservative (2-4 weeks)
- **Brier**: 0.255 → 0.20 (-21%)
- **Method**: Input validation, reject low-quality estimates
- **Effort**: Low (just add validation)

### Optimistic (2-3 months)
- **Brier**: 0.255 → 0.15 (-41%)
- **Method**: Category improvements + calibration curve (N>100)
- **Effort**: Medium (improve estimation methodology)

### Category Targets

| Category | Current | Target | Method |
|----------|---------|--------|--------|
| sports | 0.462 | 0.25 | Learn from science/geopolitics methodology |
| macro | 0.292 | 0.20 | Use historical base rates |
| crypto | 0.292 | 0.22 | Account for volatility |
| others | 0.12-0.23 | Maintain | Continue current approach |

---

## Monitoring Progress

Track these metrics on each backtest:

1. **Overall Brier Score** - Target: < 0.20
2. **Brier by Category** - No category > 0.30
3. **Validation Warning Rate** - Target: < 10%
4. **Fair vs Market Win Rate** - Maintain > 70%

---

## Common Questions

### Q: Should I shrink fair_prob toward market_prob?

**A: NO.** Analysis shows this REDUCES performance. Your edge comes from being different from the market when you're right.

### Q: My calibration_by_bucket shows poor calibration. Should I fix it?

**A: Not yet.** With only 6 markets, bucket sample sizes (N=1-2) are too small for reliable conclusions. Collect 100+ markets first.

### Q: Should I avoid sports/macro/crypto markets?

**A: No, but be extra careful.** Use the guidelines in `docs/fair_prob_guidelines.md` and consider reducing position size for these categories.

### Q: How do I improve my fair_prob estimates?

**A: Follow these principles:**
1. Start with historical base rates
2. Make small adjustments based on new information
3. Use market price as sanity check
4. Avoid extreme probabilities (<0.15 or >0.85)
5. Document reasoning for large edges

See [`docs/fair_prob_guidelines.md`](docs/fair_prob_guidelines.md) for detailed guidance.

---

## Next Steps

### Immediate
1. ✅ Read `CALIBRATION_SUMMARY.md` to understand findings
2. ✅ Review `docs/fair_prob_guidelines.md` for your category
3. ✅ Run `python3 test_validation.py` to see validation in action

### Short-term (This Week)
1. Integrate `validation.py` into your workflow
2. Review existing markets and flag issues
3. Apply guidelines to new fair_prob estimates

### Medium-term (2-4 Weeks)
1. Collect 20-30 more market observations
2. Analyze sports/macro/crypto failures
3. Develop improved estimation methodology

### Long-term (2-3 Months)
1. Accumulate 100+ observations
2. Implement isotonic regression calibration
3. Re-fit calibration curve periodically

---

## Support & Contribution

### Questions?
- Fair prob estimation: See `docs/fair_prob_guidelines.md`
- Validation warnings: See `validation.py` docstrings
- Technical details: See `CALIBRATION_RECOMMENDATIONS.md`

### Contributing?
- Add new validation rules to `validation.py`
- Improve category-specific guidelines in `docs/fair_prob_guidelines.md`
- Share successful estimation methodologies

---

## References

- Current backtest: `/Users/howdymary/Documents/New project/autopredict/state/backtests/20260327-035136/metrics.json`
- Sample data: `/Users/howdymary/Documents/New project/autopredict/datasets/sample_markets.json`
- Baseline config: `/Users/howdymary/Documents/New project/autopredict/strategy_configs/baseline.json`

---

**Bottom Line**: You have genuine edge over the market. Focus on improving weak categories (sports, macro, crypto) through better methodology, not calibration adjustments that would destroy your predictive power.
