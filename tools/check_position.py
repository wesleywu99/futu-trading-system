"""Check current positions and orders via Futu API."""

from futu import OpenSecTradeContext, TrdEnv, TrdMarket, RET_OK

trd_ctx = OpenSecTradeContext(filter_trdmarket=TrdMarket.US, host='127.0.0.1', port=11111)

# Check positions
print("=" * 60)
print("  CURRENT POSITIONS (SIMULATE)")
print("=" * 60)
ret, data = trd_ctx.position_list_query(trd_env=TrdEnv.SIMULATE)
if ret == RET_OK:
    if len(data) == 0:
        print("  >>> No positions found.")
    else:
        for _, row in data.iterrows():
            print(f"  {row['code']} | qty={row['qty']} | can_sell={row.get('can_sell_qty', '?')} | "
                  f"cost={row.get('cost_price', '?')}")
else:
    print(f"  Error: {data}")

# Check today's orders
print("\n" + "=" * 60)
print("  TODAY'S ORDERS (SIMULATE)")
print("=" * 60)
ret, data = trd_ctx.order_list_query(trd_env=TrdEnv.SIMULATE)
if ret == RET_OK:
    if len(data) == 0:
        print("  No orders found.")
    else:
        for _, row in data.iterrows():
            print(f"  ID={row['order_id']} | {row['code']} | {row['trd_side']} | "
                  f"qty={row['qty']} | price={row['price']} | status={row['order_status']} | "
                  f"dealt={row.get('dealt_qty', '?')}")
else:
    print(f"  Error: {data}")

# Check order history
print("\n" + "=" * 60)
print("  HISTORY ORDERS (SIMULATE)")
print("=" * 60)
ret, data = trd_ctx.history_order_list_query(trd_env=TrdEnv.SIMULATE)
if ret == RET_OK:
    if len(data) == 0:
        print("  No history orders found.")
    else:
        for _, row in data.iterrows():
            print(f"  ID={row['order_id']} | {row['code']} | {row['trd_side']} | "
                  f"qty={row['qty']} | price={row['price']} | status={row.get('order_status', '?')}")
            print(f"    dealt_qty={row.get('dealt_qty', '?')} | "
                  f"create_time={row.get('create_time', '?')} | "
                  f"updated_time={row.get('updated_time', '?')}")
else:
    print(f"  Error: {data}")

# Check account info
print("\n" + "=" * 60)
print("  ACCOUNT INFO (SIMULATE)")
print("=" * 60)
ret, data = trd_ctx.accinfo_query(trd_env=TrdEnv.SIMULATE)
if ret == RET_OK:
    for _, row in data.iterrows():
        print(f"  Cash: {row.get('cash', '?')}")
        print(f"  Total Assets: {row.get('total_assets', '?')}")
        print(f"  Market Value: {row.get('market_val', '?')}")
else:
    print(f"  Error: {data}")

trd_ctx.close()
