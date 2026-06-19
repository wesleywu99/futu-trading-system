"""Quick KDJ check for a stock via Futu API."""

import sys
from futu import OpenQuoteContext, KLType, RET_OK, SubType

CODE = sys.argv[1] if len(sys.argv) > 1 else "US.GOOGL"

ctx = OpenQuoteContext(host="127.0.0.1", port=11111)
ctx.subscribe([CODE], [SubType.K_DAY])
ret, data = ctx.get_cur_kline(CODE, 60, ktype=KLType.K_DAY)

if ret != RET_OK:
    print(f"Error: {data}")
    ctx.close()
    sys.exit(1)

closes = data["close"].tolist()
highs = data["high"].tolist()
lows = data["low"].tolist()
dates = data["time_key"].tolist()

K_vals = [50.0]
D_vals = [50.0]

for i in range(8, len(closes)):
    low_9 = min(lows[i - 8 : i + 1])
    high_9 = max(highs[i - 8 : i + 1])
    if high_9 == low_9:
        rsv = 50
    else:
        rsv = (closes[i] - low_9) / (high_9 - low_9) * 100
    K = 2 / 3 * K_vals[-1] + 1 / 3 * rsv
    D = 2 / 3 * D_vals[-1] + 1 / 3 * K
    K_vals.append(K)
    D_vals.append(D)

J_vals = [3 * K - 2 * D for K, D in zip(K_vals, D_vals)]

header = f"{'Date':<14} {'Close':>8} {'K':>8} {'D':>8} {'J':>8}"
print(f"\n{CODE} Daily KDJ (last 20 bars):")
print(header)
print("-" * 52)

for i in range(-20, 0):
    idx = len(K_vals) + i
    if idx >= 0:
        j_val = J_vals[idx]
        marker = " <<< J<0 OVERSOLD" if j_val < 0 else ""
        print(
            f"{str(dates[idx])[:10]:<14} "
            f"{closes[idx]:>8.2f} "
            f"{K_vals[idx]:>8.2f} "
            f"{D_vals[idx]:>8.2f} "
            f"{j_val:>8.2f}"
            f"{marker}"
        )

print()
print(f"Latest: K={K_vals[-1]:.2f}  D={D_vals[-1]:.2f}  J={J_vals[-1]:.2f}")

if J_vals[-1] < 0:
    print(">>> J < 0: DEEPLY OVERSOLD - potential buying opportunity")
elif J_vals[-1] < 20:
    print(">>> J < 20: oversold zone")
elif J_vals[-1] > 100:
    print(">>> J > 100: DEEPLY OVERBOUGHT - potential selling opportunity")
elif J_vals[-1] > 80:
    print(">>> J > 80: overbought zone")
else:
    print(">>> J in neutral zone (20-80)")

ctx.close()
