#!/usr/bin/env python3
"""
获取持仓与资金

功能：查询账户的资金状况和持仓列表
用法：python get_portfolio.py --market HK --trd-env SIMULATE

接口限制：
- 同一账户 ID 每 30 秒最多请求 10 次（仅刷新缓存时受限）

参数说明：
- currency: 仅期货账户、综合证券账户适用，其它账户类型忽略此参数；返回的资金字段会以此币种换算
- refresh_cache: True 立即请求服务器（受限频限制），False 使用 OpenD 缓存

返回字段说明：
- power（购买力）: 按 50% 融资初始保证金率计算的近似值，建议用 get_max_trd_qtys 获取精确值
- total_assets: 总资产净值 = 证券资产净值 + 基金资产净值 + 债券资产净值
- market_val: 仅证券账户适用
- avl_withdrawal_cash: 仅证券账户适用
- currency: 仅综合证券账户、期货账户适用
- pl_ratio（持仓盈亏比）: 百分比字段，20 实际对应 20%，期货不适用
"""
import argparse
import json
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    create_trade_context,
    parse_trd_env,
    parse_market,
    get_default_acc_id,
    get_default_trd_env,
    get_default_market,
    check_ret,
    safe_close,
    is_empty,
    safe_get,
    safe_float,
    format_enum,
)


def get_portfolio(acc_id=None, market=None, trd_env=None, currency=None, output_json=False):
    acc_id = acc_id or get_default_acc_id()
    trd_env = parse_trd_env(trd_env) if trd_env else get_default_trd_env()

    ctx = None
    try:
        ctx = create_trade_context(market)
        # 查询资金
        query_kwargs = dict(trd_env=trd_env, acc_id=acc_id)
        if currency:
            query_kwargs["currency"] = currency
        ret, acc_data = ctx.accinfo_query(**query_kwargs)
        check_ret(ret, acc_data, ctx, "查询账户资金")

        funds = {}
        if not is_empty(acc_data):
            row = acc_data.iloc[0] if hasattr(acc_data, "iloc") else acc_data
            funds = {
                "currency": safe_get(row, "currency", default="N/A"),
                "total_assets": safe_float(safe_get(row, "total_assets", default=0)),
                "cash": safe_float(safe_get(row, "cash", default=0)),
                "market_val": safe_float(safe_get(row, "market_val", default=0)),
                "frozen_cash": safe_float(safe_get(row, "frozen_cash", default=0)),
                "avl_withdrawal_cash": safe_float(safe_get(row, "avl_withdrawal_cash", default=0)),
                "power": safe_float(safe_get(row, "power", "buying_power", default=0)),
            }

        # 查询持仓
        ret, pos_data = ctx.position_list_query(trd_env=trd_env, acc_id=acc_id)
        check_ret(ret, pos_data, ctx, "查询持仓")

        positions = []
        if not is_empty(pos_data):
            for i in range(len(pos_data)):
                row = pos_data.iloc[i] if hasattr(pos_data, "iloc") else pos_data[i]
                positions.append({
                    "code": safe_get(row, "code", default=""),
                    "name": safe_get(row, "stock_name", default=""),
                    "qty": safe_float(safe_get(row, "qty", default=0)),
                    "can_sell_qty": safe_float(safe_get(row, "can_sell_qty", default=0)),
                    "cost_price": safe_float(safe_get(row, "cost_price", default=0)),
                    "market_val": safe_float(safe_get(row, "market_val", default=0)),
                    "pl_ratio": safe_float(safe_get(row, "pl_ratio", default=0)),
                    "pl_val": safe_float(safe_get(row, "pl_val", default=0)),
                })

        if output_json:
            print(json.dumps({"funds": funds, "positions": positions}, ensure_ascii=False))
        else:
            print("=" * 70)
            ccy_label = f"  货币: {funds.get('currency', 'N/A')}" if funds else ""
            print(f"账户概览 (环境: {format_enum(trd_env)}){ccy_label}")
            print("=" * 70)
            if funds:
                print(f"\n  总资产: {funds['total_assets']:.2f}  现金: {funds['cash']:.2f}  购买力: {funds['power']:.2f}")
                print(f"  持仓市值: {funds['market_val']:.2f}  冻结: {funds['frozen_cash']:.2f}")
            print(f"\n  {'持仓列表':=^66}")
            if positions:
                print(f"  {'代码':<12} {'名称':<10} {'数量':>8} {'成本':>10} {'市值':>12} {'盈亏%':>8}")
                print("  " + "-" * 66)
                for p in positions:
                    print(f"  {p['code']:<12} {p['name']:<10} {p['qty']:>8.0f} {p['cost_price']:>10.2f} {p['market_val']:>12.2f} {p['pl_ratio']:>8.2f}%")
            else:
                print("  暂无持仓")
            print("=" * 70)

    except Exception as e:
        if output_json:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        else:
            print(f"错误: {e}")
        sys.exit(1)
    finally:
        safe_close(ctx)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="获取持仓与资金")
    parser.add_argument("--acc-id", type=int, default=None, help="账户 ID")
    parser.add_argument("--market", choices=["US", "HK", "HKCC", "CN"], default=None, help="交易市场")
    parser.add_argument("--trd-env", choices=["REAL", "SIMULATE"], default=None, help="交易环境")
    parser.add_argument("--currency", choices=["HKD", "USD", "CNH", "JPY", "AUD", "CAD", "MYR", "SGD"], default=None,
                        help="货币类型（默认由服务端决定）")
    parser.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = parser.parse_args()
    get_portfolio(acc_id=args.acc_id, market=args.market, trd_env=args.trd_env,
                  currency=args.currency, output_json=args.output_json)
