# Fair Probability Estimation Guidelines

**Purpose**: Ensure high-quality `fair_prob` estimates to improve AutoPredict's Brier score and trading performance.

**Target**: Brier score < 0.20 (current: 0.255)

---

## Quality Checklist

Before submitting a market with `fair_prob`, verify the following:

### General Rules (All Categories)

- [ ] **Compare to market price**: Is `|fair_prob - market_prob|` < 0.20?
  - If NO: Document your reasoning and evidence
  - Large edges should be rare and well-justified

- [ ] **Avoid extreme probabilities**: Is `fair_prob` in range [0.15, 0.85]?
  - If NO: You need very strong evidence for <0.15 or >0.85
  - Extreme probabilities are often overconfident

- [ ] **Use base rates**: Have you anchored to historical frequency of similar events?
  - Example: "Fed cuts rates in election year" → check last 50 years of data
  - Don't rely purely on recent news or gut feeling

- [ ] **Consider market's information advantage**: Markets aggregate many informed opinions
  - If you disagree strongly with market, ask: "What do I know that the market doesn't?"
  - If you can't articulate this, consider reducing your edge

- [ ] **Personal betting test**: Would you bet $100 of your own money at these odds?
  - If NO: Your fair_prob might not reflect your true belief

---

## Category-Specific Guidelines

### 🏆 Sports (Historical Brier: 0.462 - CRITICAL IMPROVEMENT NEEDED)

**Problem**: Sports markets have the worst calibration in AutoPredict. Favorites are often overestimated.

**Checklist**:
- [ ] Have you checked team performance over last 5-10 games (not just 1-2)?
- [ ] Have you adjusted for home/away advantage (typically 3-5% edge)?
- [ ] Have you checked for injuries to key players?
- [ ] Are you confusing "margin of victory" with "win probability"?
  - Example: A 10-point favorite might only win 65-70% of the time, not 80%+
- [ ] Have you checked historical win rate for similar favorites?

**Target Range**: Avoid probabilities >0.70 for favorites unless heavily documented.

**Red Flags**:
- fair_prob > 0.70 for any team
- Edge > 0.15 without clear injury/suspension news
- Relying on "momentum" or recent winning streak

**Good Practices**:
- Use Elo ratings or similar objective systems
- Check consensus from multiple sportsbooks
- Look at historical performance in similar matchups

---

### 📈 Macro (Historical Brier: 0.292 - HIGH PRIORITY)

**Problem**: Macro events are hard to predict. Markets often price in too much or too little risk.

**Checklist**:
- [ ] Have you reviewed recent economic indicators (CPI, employment, GDP)?
- [ ] Have you considered central bank communication patterns?
- [ ] Are you using base rates from historical similar situations?
  - Example: "How often does Fed cut rates when unemployment is at X%?"
- [ ] Have you checked consensus forecasts from professional economists?
- [ ] Are you accounting for policy lag (6-12 months for macro effects)?

**Target Range**: Stay within 0.10 of market price unless you have institutional-grade research.

**Red Flags**:
- Predicting dramatic shifts (>0.20 edge) based on single data point
- Ignoring Fed's own guidance and projections
- Overreacting to short-term volatility

**Good Practices**:
- Use historical frequency: "Fed cuts within 6 months when yield curve inverts" → check historical data
- Average multiple forecasting models
- Weight recent data more heavily but don't ignore history

---

### ₿ Crypto (Historical Brier: 0.292 - HIGH PRIORITY)

**Problem**: Crypto is extremely volatile (60-80% annualized). Point predictions often fail.

**Checklist**:
- [ ] Have you adjusted for crypto's high volatility?
- [ ] Are you using price targets (bad) or probability ranges (good)?
- [ ] Have you checked on-chain metrics (network activity, holder behavior)?
- [ ] Are you considering correlation with traditional risk assets (stocks, commodities)?
- [ ] Have you accounted for potential black swans (exchange hacks, regulation)?

**Target Range**: Use WIDE probability ranges. For "BTC > $120K", consider 0.30-0.60, not extremes.

**Red Flags**:
- fair_prob < 0.20 or > 0.80 for price predictions
- Ignoring implied volatility from options markets
- Treating crypto like traditional assets

**Good Practices**:
- Use options markets to calibrate probabilities
- Widen your ranges: if you think 50%, maybe use 45-55% range
- Check multiple timeframes (1-day, 1-week, 1-month volatility)

---

### 🗳️ Politics (Historical Brier: 0.230 - GOOD)

**Checklist**:
- [ ] Have you checked high-quality poll aggregators (FiveThirtyEight, RealClearPolitics)?
- [ ] Are you accounting for polling error (typically 3-5 points)?
- [ ] Have you considered structural factors (incumbency, economy, approval ratings)?
- [ ] Are you overweighting recent news vs. fundamentals?

**Target Range**: Generally stay within 0.15 of market, which aggregates many polls and models.

**Good Practices**:
- Use poll aggregators, not individual polls
- Check prediction markets on multiple platforms
- Account for electoral college vs. popular vote (in US elections)

---

### 🔬 Science (Historical Brier: 0.137 - EXCELLENT - USE AS TEMPLATE)

**Checklist**:
- [ ] Have you checked the organization's historical on-time launch rate?
- [ ] Are you considering technical readiness (pre-launch tests, reviews)?
- [ ] Have you factored in weather/external conditions?
- [ ] Are you using base rates from similar past events?

**Target Range**: This category performs well. Continue current methodology.

**Good Practices** (Learn from this category):
- Heavy reliance on historical base rates
- Objective data (launch history, test results)
- Less speculation, more data-driven

---

### 🌍 Geopolitics (Historical Brier: 0.116 - EXCELLENT - USE AS TEMPLATE)

**Checklist**:
- [ ] Have you checked historical frequency of similar diplomatic outcomes?
- [ ] Are you considering multiple scenarios and their probabilities?
- [ ] Have you reviewed expert analysis from international relations researchers?
- [ ] Are you avoiding recency bias (overweighting latest news)?

**Target Range**: This category performs excellently. Continue current methodology.

**Good Practices** (Learn from this category):
- Systematic use of base rates
- Conservative estimates (less extreme probabilities)
- Consideration of multiple pathways to outcomes

---

## Validation Rules

AutoPredict will flag the following automatically:

1. **Edge too large for category**:
   - Sports: edge > 0.25 → Warning
   - Macro: edge > 0.20 → Warning
   - Crypto: edge > 0.20 → Warning
   - Politics: edge > 0.15 → Warning
   - Science: edge > 0.15 → Warning
   - Geopolitics: edge > 0.15 → Warning

2. **Extreme probabilities**: fair_prob < 0.10 or > 0.90 → Warning

3. **Direction reversal**: fair_prob and market_prob on opposite sides of 0.5 → Info

4. **Low-quality category**: Sports, Macro, Crypto will generate info warnings

---

## Common Pitfalls

### ❌ DON'T:
1. Use fair_prob = 0.9 just because you "feel confident"
2. Extrapolate from 1-2 recent data points
3. Ignore the wisdom of crowds (market price)
4. Confuse "should happen" with "will happen"
5. Let emotions or biases influence probabilities
6. Use round numbers (0.5, 0.7, 0.8) without calculation

### ✅ DO:
1. Start with base rates from historical data
2. Make small adjustments based on new information
3. Use market price as a sanity check
4. Document your reasoning for large edges
5. Test your calibration on out-of-sample data
6. Use precise probabilities based on actual analysis

---

## Calibration Self-Check

After making 10+ predictions, review your calibration:

1. Group your predictions by probability bucket (0-10%, 10-20%, etc.)
2. Calculate realized frequency in each bucket
3. Check if realized ≈ predicted

**Example**:
- You predicted 5 events at ~70% probability
- Only 2 occurred (40% realized rate)
- **Diagnosis**: You're overconfident at 70% → adjust future estimates down

---

## Resources

- **Historical base rates**: Use databases like Wikipedia, sports-reference.com, economic data from FRED
- **Market consensus**: Check multiple prediction markets (PredictIt, Polymarket, Metaculus)
- **Expert forecasts**: Superforecasters, domain experts, institutional research
- **Calibration tools**: Track your predictions and outcomes to improve over time

---

## Questions?

If unsure about a fair_prob estimate, ask:

1. "What's the historical base rate for events like this?"
2. "Why do I disagree with the market, and what's my evidence?"
3. "If I had to bet $100, what odds would I actually accept?"
4. "Am I being overconfident because of recent news or emotional investment?"

**When in doubt, shrink toward the market price or toward 0.5 (maximum uncertainty).**

---

**Last Updated**: 2026-03-26
**Next Review**: After 100 total markets (currently at 6)
