# 📊 Stock Screener – User Guide for Beginners

## ⚠️ Important Disclaimer (Please Read First)

This application is created **ONLY for educational and learning purposes**.

It:
- Demonstrates how technical indicators like RSI, MACD, and Volume can be combined
- Helps users understand market data and screening logic
- Is meant for **study, experimentation, and technical analysis learning**

🚫 **This app does NOT provide investment advice**  
🚫 **This app does NOT recommend buying or selling any stock**  
🚫 **This app is NOT a trading system**  
🚫 **This app is NOT a financial advisory tool**

Any output shown in this app:
- Should NOT be considered as a trading signal  
- Should NOT be used directly for real-money trading  
- Should NOT be treated as a recommendation  

**Always consult a qualified financial advisor before making investment decisions.**

You are solely responsible for any financial decisions you make.

---

## What is this App?

This is a **Stock Screener** — a tool that automatically analyzes stocks and highlights them based on **technical indicators** such as:

- RSI (Relative Strength Index)
- Moving Averages (50-DMA, 200-DMA)
- MACD (Momentum)
- Volume behavior

Think of it as:
> A learning tool to understand how technical screening works  
> NOT a tool that tells you what to buy or sell

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

### **RSI (Relative Strength Index)**

RSI measures how fast a stock has moved up or down recently.

**RSI Zones:**
- **RSI < 30** → Oversold (price fell rapidly)
- **RSI 30–60** → Neutral
- **RSI > 70** → Overbought (price rose rapidly)

Low RSI does NOT mean the stock must go up.  
It only shows recent price behavior.

---

### **Vol_Spike (Volume Spike)**

This shows how today’s volume compares to recent average volume.

Examples:
- `1.0` → normal volume  
- `2.0` → double the usual volume  
- `0.5` → half the usual volume  

High volume during a price fall can indicate panic selling.

---

### **Action**

This is a **technical label**, not a recommendation.

Possible labels:

- **OVERSOLD**  
- **CONTRA BUY**  
- **BUY**  
- **BUILD**  
- **WAIT**

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
- Price is below both 50-DMA and 200-DMA  
- RSI is low  

Meaning:
- Stock is in a downtrend
- Momentum is weak
- Could bounce temporarily

This is a **high-risk technical pattern**.

---

## BUY

Conditions:
- Price is above 200-DMA  
- RSI is low  

Meaning:
- Stock is in a long-term uptrend
- Recently corrected

---

## BUILD

Conditions:
- Price is above 50-DMA and 200-DMA  

Meaning:
- Stock is in a stable uptrend

---

## WAIT

Meaning:
- No clear technical pattern
- Indicators do not align

---

## Understanding Moving Averages (DMA)

- **50-DMA** → short-term trend  
- **200-DMA** → long-term trend  

Interpretation:
- Price above 200-DMA → long-term uptrend  
- Price below 200-DMA → long-term downtrend  

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
   - Price chart
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
✔ Learning tool  
✔ Coding project  
✔ Technical analysis demo  

It is NOT:
❌ A trading system  
❌ A financial advisor  
❌ A profit machine  

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
✔ Learn  
✔ Experiment  
✔ Understand markets  

Not to:
❌ Trade blindly  
❌ Risk real money  
❌ Assume accuracy  

Always verify with multiple sources and professional advice.
