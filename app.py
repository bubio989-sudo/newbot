//@version=5
strategy("1BTCUSDT High Win Rate 1min w/ Visual Filters", 
     overlay=true,
     default_qty_type=strategy.percent_of_equity, 
     default_qty_value=1, 
     initial_capital=100, 
     currency=currency.USD,
     pyramiding=1,
     commission_type=strategy.commission.percent,
     commission_value=0.0,
     calc_on_every_tick=false)

// ================== KRAKEN ALERT SETTINGS ==================
send_order_alerts   = input.bool(true, "Send alerts to Kraken")
product_id_input    = input.string("BTC-USD", "Exchange Pair Symbol")
alert_amount        = input.float(10.0, "Order Amount (USD)", minval=1, step=1)

// Kraken-friendly message format (key:value pairs)
long_msg  = 'symbol: ' + product_id_input + '; action: buy; amount: ' + str.tostring(alert_amount)
short_msg = 'symbol: ' + product_id_input + '; action: sell; amount: ' + str.tostring(alert_amount)

// ================== INPUTS ==================
RiskPct       = input.float(1.0, "Risk % per trade", step=0.1, minval=0.1)
atrPeriod     = input.int(14, "ATR period")
atrMult       = input.float(1.0, "ATR multiplier")
minStopPips   = input.float(0.5, "Min stop")
rr            = input.float(1.2, "Take-profit (R multiple)")
useTrail      = input.bool(true, "Enable trailing")
trailATRmult  = input.float(1.0, "Trailing distance = ATR ×")
showRTrades   = input.bool(true, "Show per-trade R-multiples")
showPanel     = input.bool(true, "Show Stats Panel")

// ================== INDICATORS ==================
emaFast = ta.ema(close, 9)
emaSlow = ta.ema(close, 21)
atrValue = ta.atr(atrPeriod)
atrMin = ta.lowest(atrValue, 14)

// ================== SIGNALS ==================
candleBull = close > open
candleBear = close < open
volatilityOK = atrValue > atrMin * 1.1

longSignal  = ta.crossover(emaFast, emaSlow) and candleBull and volatilityOK
shortSignal = ta.crossunder(emaFast, emaSlow) and candleBear and volatilityOK

// ================== TRADE FUNCTION ==================
f_enterTrade(dir) =>
    float stop = na
    float tp = na
    float trail = na
    float qty = 0.0
    float riskPerUnit = na

    if dir == strategy.long
        stop := close - math.max(atrValue * atrMult, minStopPips)
        riskPerUnit := close - stop
        tp := close + rr * riskPerUnit
    else
        stop := close + math.max(atrValue * atrMult, minStopPips)
        riskPerUnit := stop - close
        tp := close - rr * riskPerUnit

    if not na(riskPerUnit) and riskPerUnit > 0
        riskValue = strategy.equity * RiskPct / 100.0
        qty := riskValue / riskPerUnit

    if useTrail
        trail := trailATRmult * atrValue

    if qty > 0
        entryName = dir==strategy.long ? "Long" : "Short"
        alertMsg  = dir==strategy.long ? long_msg : short_msg
        
        strategy.entry(entryName, dir, qty=qty, alert_message=(send_order_alerts ? alertMsg : ""))

        if not na(trail) and trail > 0
            strategy.exit(entryName + " Exit", from_entry=entryName, stop=stop, limit=tp, trail_offset=trail)
        else
            strategy.exit(entryName + " Exit", from_entry=entryName, stop=stop, limit=tp)

    [qty, stop, tp, riskPerUnit, trail]

// ================== EXECUTION ==================
if barstate.isconfirmed and longSignal
    f_enterTrade(strategy.long)
    alert(long_msg, alert.freq_once_per_bar_close)

if barstate.isconfirmed and shortSignal
    f_enterTrade(strategy.short)
    alert(short_msg, alert.freq_once_per_bar_close)

// ================== VISUAL FILTERS ==================
plotshape(volatilityOK, title="Volatility OK", style=shape.triangleup, color=color.yellow, location=location.bottom, size=size.tiny)
plotshape(candleBull and volatilityOK, title="Strong Bull Candle", style=shape.triangleup, color=color.green, location=location.belowbar, size=size.small)
plotshape(candleBear and volatilityOK, title="Strong Bear Candle", style=shape.triangledown, color=color.red, location=location.abovebar, size=size.small)

plotshape(longSignal, title="Long Entry", style=shape.labelup, location=location.belowbar, color=color.green, text="LONG")
plotshape(shortSignal, title="Short Entry", style=shape.labeldown, location=location.abovebar, color=color.red, text="SHORT")

// ================== R-MULTIPLES ==================
var float tradeRisk = na
var float lastR = na
var float sumR = 0
var int tradeCount = 0

if strategy.closedtrades > tradeCount
    tradeCount += 1
    pl = strategy.closedtrades.profit(strategy.closedtrades - 1)
    if not na(tradeRisk) and tradeRisk > 0
        lastR := pl / tradeRisk
        sumR += lastR
        if showRTrades and not na(lastR)
            label.new(bar_index, close, text="R=" + str.tostring(lastR,"#.##"), 
                      style=(lastR < 0 ? label.style_label_down : label.style_label_up), 
                      color=(lastR < 0 ? color.new(color.red,70) : color.new(color.green,70)), 
                      textcolor=color.white)

// ================== PLOTS ==================
plot(emaFast, color=color.yellow, title="EMA Fast")
plot(emaSlow, color=color.orange, title="EMA Slow")
plot(strategy.equity, "Equity Curve", color=color.green, linewidth=2)

// ================== STATS PANEL ==================
if barstate.islast and showPanel
    winRate = strategy.closedtrades>0 ? (strategy.wintrades/strategy.closedtrades)*100 : na
    pf = strategy.grossloss!=0 ? strategy.grossprofit/-strategy.grossloss : na
    dd = strategy.max_drawdown
    netProfit = strategy.netprofit
    trades = strategy.closedtrades
    avgR = tradeCount>0 ? sumR/tradeCount : na

    var table stats = table.new(position.top_right, 1, 6, border_width=1)
    table.cell(stats, 0,0,"📊 Stats", text_color=color.white, bgcolor=color.black)
    table.cell(stats, 0,1,"Win Rate: "+str.tostring(winRate,"#.##")+"%", text_color=color.lime)
    table.cell(stats, 0,2,"PF: "+str.tostring(pf,"#.##"), text_color=color.aqua)
    table.cell(stats, 0,3,"Max DD: "+str.tostring(dd,"#.##"), text_color=color.orange)
    table.cell(stats, 0,4,"Net Profit: "+str.tostring(netProfit,"#.##"), text_color=color.green)
    table.cell(stats, 0,5,"Trades: "+str.tostring(trades), text_color=color.yellow)
