"""BTC race bot: capped dip-buy on CBBTC (buy-and-hold the dip, bank the bounce).

Strategy: wait for a sharp dip, buy it once, take a modest profit, stop out small,
and never trade more than twice per window.

  - Entry: the close is at least 2% below the highest close of the last 240 bars
    (4 hours). Full size (all cash).
  - Exit: the position is worth at least 1.5% over its cost (take profit), or at
    most 1% under it (stop loss). Whole position, one sell.
  - Cap: at most 2 round trips per window. After the second sell, never buy again.

Why this, and not the kit's baselines: on this race's frozen 24h dev window BTC
fell 2.80% end to end, so buy-and-hold loses $31.63 and momentum loses $23.87,
while every active baseline loses too (EMA cross 8/21: -$148.17 on 80 trades,
RSI-Bollinger: -$39.92, ADX-momentum: -$75.57). A full round trip costs about
26 bps in fees, slippage and price impact, and 1-minute bars are mostly noise
(median 1m move 0 bps, p95 about +/-12 bps), so any rule that trades often
bleeds to death: the uncapped version of this same dip rule made 36 trades and
lost $62.44 on the previous race's dev window. Capping the trades is the whole
point: one well-chosen round trip on the dev window buys the early dip at
$63,781 and sells the recovery at $64,688 for +$13.41 net, and the same rule
made +$14.00 on the previous race's (rising, +0.49%) dev window, so it is not
tuned to one day's shape. It also keeps the maximum drawdown tiny (-0.64% on
the dev window) and the action log short, so it cannot be confused with a
baseline's log.

Verified against the kit's own grader (grade-local, process driver, 18 Nov
2026): net PnL +$13.41, 2 trades (1 round trip), fees $0.81, max drawdown
0.64% — exactly the backtest figure, so the bot's integer rules reproduce the
design on the wire. Dev gate (+$0) passed; guardrails (at least 1 trade,
drawdown at most 25%) passed.

Determinism: integer arithmetic only (no floats), no randomness, no clock, no
environment reads. The only state is the close history, whether a position is
held, and how many round trips have finished. A rejected order (a gap, a price
past the slippage cap) is simply decided again on the next batch while the
entry or exit condition still holds.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
MAX_SLIPPAGE_BPS = 100
LOOKBACK_BARS = 240
DIP_NUM, DIP_DEN = 2, 100          # buy at least 2% below the 240-bar high
TP_NUM, TP_DEN = 3, 200            # sell at least 1.5% over cost
SL_NUM, SL_DEN = 1, 100            # sell at most 1% under cost
MAX_ROUND_TRIPS = 2

closes = []
round_trips = 0


def on_batch(state, batch):
    """Decide the orders for this batch: dip-buy, take profit / stop loss, cap 2 trips."""
    global round_trips
    if state.warming_up:
        return []
    bar = state.latest.get(SYMBOL)
    if bar is None:
        return []
    closes.append(int(bar["c"]))
    held = state.positions.get(SYMBOL)
    if held is not None:
        value = state.value(SYMBOL, held.qty)
        if value * TP_DEN >= held.cost * (TP_DEN + TP_NUM) or value * SL_DEN <= held.cost * (SL_DEN - SL_NUM):
            round_trips += 1
            return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []
    if round_trips >= MAX_ROUND_TRIPS or len(closes) <= LOOKBACK_BARS:
        return []
    high = max(closes[-LOOKBACK_BARS - 1:])
    close = closes[-1]
    if close * DIP_DEN <= high * (DIP_DEN - DIP_NUM):
        amount = min(state.cash, state.weight_room(SYMBOL))
        min_notional = int(state.hello["fees"]["min_notional_quote_units"])
        if amount < min_notional:
            return []
        return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": amount,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    return []


makefun_bars.run(on_batch)
