# Stock Screener - User Guide for Beginners

## Important Disclaimer (Please Read First)

This application is created **ONLY for educational and learning purposes**.

It:
- Demonstrates how technical indicators like RSI, MACD, and Volume can be combined
- Helps users understand market data and screening logic
- Is meant for **study, experimentation, and technical analysis learning**

[NOT] **This app does NOT provide investment advice**  
[NOT] **This app does NOT recommend buying or selling any stock**  
[NOT] **This app is NOT a trading system**  
[NOT] **This app is NOT a financial advisory tool**

Any output shown in this app:
- Should NOT be considered as a trading signal  
- Should NOT be used directly for real-money trading  
- Should NOT be treated as a recommendation  

**Always consult a qualified financial advisor before making investment decisions.**

You are solely responsible for any financial decisions you make.

---

## What is this App?

This is a **Stock Screener** - a tool that automatically analyzes stocks and highlights them based on **technical indicators** such as:

- RSI (Relative Strength Index)
- Moving Averages (50-DMA, 200-DMA)
- MACD (Momentum)
- Volume behavior

Think of it as:
> A learning tool to understand how technical screening works  
> NOT a tool that tells you what to buy or sell

---

## Chart Viewer (Candlestick)

The app includes a **Chart Viewer** below the results table:

- Select any stock from the filtered list
- The app shows a **1-year candlestick chart** (Open, High, Low, Close) when OHLC data is available
- If OHLC data is not available, it falls back to a **line chart** using Close prices

This chart is for visual learning and pattern study only.

---

## Data Update Frequency

This app uses **pre-generated daily scan results** to ensure fast performance.

- Market scans are run **once per day**
- Results are saved to data files
- The scan date and time are shown in the app
- The app only **loads existing results**, it does not calculate them live

This design makes the app:
- Faster
- More stable
- Easier to test and demonstrate

---

## Understanding the Results Table

When you load a scan, you will see a table with these columns:

---

### **Stock**
- The name of the company (e.g., "Asian Paints Ltd.", "Reliance Industries")
- This is the stock being analyzed

---

### **Ticker**
- Exchange code used to identify the stock  
- Example: `ASIANPAINT.NS`  
- `.NS` means the stock is listed on NSE (India)

---

### **Close**
- The most recent closing price (in INR)

---

### **Rank**
- The technical rank (1 is best, higher is weaker)
- Sorts stocks by best technical alignment

---

### **1Y_Return_%**
- The percentage return over the last 1 year

---

### **RSI (Relative Strength Index)**

RSI measures how fast a stock has moved up or down recently.

**RSI Zones:**
- **RSI < 30** -> Oversold (price fell rapidly)
- **RSI 30-60** -> Neutral
- **RSI > 70** -> Overbought (price rose rapidly)

Low RSI does NOT mean the stock must go up.  
It only shows recent price behavior.

---

### **Vol_Spike (Volume Spike)**

This shows how today's volume compares to recent average volume.

Examples:
- `1.0` -> normal volume  
- `2.0` -> double the usual volume  
- `0.5` -> half the usual volume  

High volume during a price fall can indicate panic selling.

---

### **Action**

This is a **technical label**, not a recommendation.

Possible labels:

- **OVERSOLD**
- **CONTRA BUY**
- **BUY**
- **BUILD**
- **SELL**
- **EXIT**
- **SHORT**
- **HOLD**

These labels describe how indicators align, not what you should trade.

---

## OVERSOLD (Highest Priority)

A stock is marked **OVERSOLD** when:

- RSI is very low  
- Volume is unusually high  
- Price is below 50-day average  
- MACD momentum is improving  

This may indicate selling pressure is reducing.  
It does NOT guarantee a price increase.

---

## CONTRA BUY

Conditions:
- Price is below both 50-DMA and 200-DMA (Downtrend)
- RSI is low (<40)
- **MACD Histogram is improving** (Momentum is turning up)

Meaning:
- Stock is in a downtrend but selling pressure is fading
- "Catching the turn, not the knife"
- Still a **high-risk technical pattern**, but safer with momentum check

---

## BUY

Conditions:
- Price is above 200-DMA  
- RSI is low (<40)
- **MACD Histogram is improving**

Meaning:
- Stock is in a long-term uptrend
- Recently corrected, but starting to recover

---

## BUILD

Conditions:
- Price is above 50-DMA and 200-DMA  
- **MACD Histogram is improving**

Meaning:
- Stock is in a stable uptrend with rising momentum

---

## SELL

Conditions:
- Price is above 50-DMA and 200-DMA (Uptrend)
- RSI is Overbought (>60)
- **MACD Histogram is weakening** (Momentum slowing down)

Meaning:
- Stock has run up fast and is losing steam
- Potential profit booking zone

---

## EXIT

Conditions:
- Price is below 200-DMA (Downtrend)
- RSI is rising (>40)
- **MACD Histogram is weakening**

Meaning:
- Exit on bounce that is now failing
- Downtrend likely to continue

---

## SHORT

Conditions:
- Price is below 50-DMA and 200-DMA (Strong Downtrend)
- **MACD Histogram is weakening**

Meaning:
- Strong downward momentum accelerating

---

## HOLD

Meaning:
- No clear technical pattern
- Indicators do not align

---

## Understanding Moving Averages (DMA)

- **50-DMA** -> short-term trend  
- **200-DMA** -> long-term trend  

Interpretation:
- Price above 200-DMA -> long-term uptrend  
- Price below 200-DMA -> long-term downtrend  

---

## Understanding MACD

MACD shows momentum changes.

When MACD histogram rises:
- Downward momentum is slowing
- Price may consolidate or bounce

---

## How Ranking Works

Stocks are ranked from **best technical alignment** to weakest.

| Rank | Meaning |
|------|---------|
| 1 | Strongest technical alignment |
| 2 | Moderate alignment |
| 3 | Weak alignment |
| 4+ | Very weak alignment |

Lower rank number = stronger technical pattern  
Higher rank number = weaker technical pattern  

This ranking is based purely on indicator logic.

---

## Example Usage

1. Load latest scan  
2. Observe which stocks appear in top ranks  
3. Study:
   - Candlestick chart (or line chart fallback)
   - Company fundamentals
   - News
4. Learn how indicators behave

Do NOT treat the output as trade advice.

---

## What This App Does NOT Do

This app does NOT:
- Predict future prices
- Consider company financials
- Analyze news or events
- Guarantee profits
- Replace professional advice

---

## Educational Purpose Summary

This project is meant to help users learn:

- How technical indicators are calculated
- How screening logic is written in code
- How ranking systems can be built
- How market data can be visualized

It is a:
[OK] Learning tool  
[OK] Coding project  
[OK] Technical analysis demo  

It is NOT:
[NO] A trading system  
[NO] A financial advisor  
[NO] A profit machine

---

## Tech Highlights (Under the Hood)

For the tech-savvy, this app includes:
- **Fast Caching**: Optimized O(1) cache reads/writes (no re-reading large CSVs).
- **Robustness**: Auto-retries on failed downloads, stale cache expiry (5 days), and input validation.
- **Automation**: Fully automated GitHub Actions workflow scans Nifty 50 and Next 50 nightly.
- **Safe**: Prevents data corruption using immutable DataFrame copies.  

---

## Responsibility

All financial decisions carry risk.

By using this app, you agree that:
- You understand it is for educational use only
- You will not rely on it for real trading decisions
- You take full responsibility for any actions you take

---

## Need Help Learning?

You can:
- Read about RSI, MACD, Moving Averages
- Study charts on TradingView
- Learn Python-based market analysis
- Explore NSE historical data
- Read books on market psychology

---

## Final Note

This app shows **how screening works**, not **what to trade**.

Use it to:
[OK] Learn  
[OK] Experiment  
[OK] Understand markets  

Not to:
[NO] Trade blindly  
[NO] Risk real money  
[NO] Assume accuracy  

Always verify with multiple sources and professional advice.
