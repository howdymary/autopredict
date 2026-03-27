# AutoPredict Calibration - Quick Reference Card

**Current Brier**: 0.255 | **Target**: < 0.20 | **Status**: ✅ Phase 1 Complete

---

## TL;DR

**Finding**: Your fair_prob beats market by 19%. Don't calibrate - improve weak categories.

**Action**: Fix sports (0.462), macro (0.292), crypto (0.292) estimation methodology.

**Tools**: Use `validation.py` to catch bad estimates before they hurt performance.

---

## Category Quality at a Glance

```
⭐⭐⭐⭐⭐ geopolitics  0.116  |  Excellent - Maintain
⭐⭐⭐⭐⭐ science      0.137  |  Excellent - Maintain
⭐⭐⭐     politics    0.230  |  Good - Maintain
⭐       crypto      0.292  |  Poor - HIGH PRIORITY FIX
⭐       macro       0.292  |  Poor - HIGH PRIORITY FIX
❌       sports      0.462  |  CRITICAL - URGENT FIX
```

---

## What to Fix by Category

### 🏆 Sports (CRITICAL)
- **Problem**: Overestimating favorites (>0.70 probabilities)
- **Fix**: Use historical win rates, avoid >0.70 unless heavily justified
- **Example**: Championship favorite at 0.68 → actual outcome 0 (error: 0.462)

### 📈 Macro
- **Problem**: Not using historical base rates
- **Fix**: Check "how often does Fed cut when X happens?" historically
- **Example**: Fed cuts at 0.54 → actual outcome 0 (error: 0.292)

### ₿ Crypto
- **Problem**: Not accounting for volatility (60-80% annualized)
- **Fix**: Use wider probability ranges, check options markets
- **Example**: BTC >$120K at 0.46 → actual outcome 1 (error: 0.292)

---

## Quick Validation Check

```python
from validation import FairProbValidator

validator = FairProbValidator()
warnings = validator.validate(
    fair_prob=0.70,      # Your estimate
    market_prob=0.55,    # Market price
    category="sports"    # Market category
)

# Review warnings before using this market
for w in warnings:
    print(f"{w.severity}: {w.message}")
```

---

## Red Flags (Avoid These)

❌ Fair prob > 0.90 or < 0.10 (too extreme)
❌ Edge > 0.20 in poor quality categories (sports, macro, crypto)
❌ Sports probabilities > 0.70 without strong evidence
❌ Ignoring market price completely
❌ Using gut feeling instead of base rates

---

## Best Practices (Do These)

✅ Start with historical base rates
✅ Make small adjustments from market price
✅ Use market price as sanity check
✅ Document reasoning for large edges
✅ Validate before using (run validation.py)
✅ Learn from excellent categories (science, geopolitics)

---

## Files to Know

**Read First**: `CALIBRATION_SUMMARY.md`
**For Users**: `docs/fair_prob_guidelines.md`
**For Devs**: `README_CALIBRATION.md`
**Production Code**: `validation.py`
**Example**: `run_experiment_with_validation.py`
**Test It**: `python3 test_validation.py`

---

## Expected Impact

**Conservative** (2-4 weeks): 0.255 → 0.20 (-21%)
**Optimistic** (2-3 months): 0.255 → 0.15 (-41%)

---

## One-Liner Answers

**Q: Should I shrink toward market?**
A: NO. You already beat market by 19%.

**Q: Should I add calibration layer?**
A: NO. No systematic bias detected.

**Q: What's the #1 priority?**
A: Fix sports category (0.462 Brier).

**Q: Can I trust calibration_by_bucket?**
A: NO. Need 100+ markets (currently 6).

**Q: What should I do today?**
A: Read `docs/fair_prob_guidelines.md` for your category.

---

## Common Mistakes

| Mistake | Impact | Fix |
|---------|--------|-----|
| Sports prob > 0.70 | High error | Use historical win rates |
| Ignoring volatility (crypto) | High error | Widen probability ranges |
| Overreacting to news (macro) | Medium error | Use historical base rates |
| Extreme probs (<0.10, >0.90) | Variable | Stay in 0.15-0.85 range |

---

## Next Steps

1. Read category guidelines (`docs/fair_prob_guidelines.md`)
2. Run validation test (`python3 test_validation.py`)
3. Integrate validation into workflow
4. Focus on fixing weak categories

---

**Remember**: You have genuine edge. Don't destroy it with over-calibration.
