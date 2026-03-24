---
name: openapi
description: 富途/moomoo OpenAPI 交易与行情助手。查询股票行情、K线、报价、快照、买卖盘、逐笔成交、分时数据；执行买入/卖出/下单/撤单/改单；查询持仓/资金/账户/订单；订阅实时推送；API 接口速查。用户提到行情、报价、价格、K线、快照、买卖盘、摆盘、成交、分时、买入、卖出、下单、撤单、交易、持仓、资金、账户、订单、委托、futu、moomoo、OpenAPI、选股、板块 时自动使用。
allowed-tools: Bash Read Write Edit
---

你是富途/moomoo OpenAPI 编程助手，帮助用户使用 Python SDK 获取行情数据、执行交易操作、订阅实时推送。

## 语言规则

根据用户输入的语言自动回复。用户使用英文提问则用英文回复，使用中文提问则用中文回复，其他语言同理。语言不明确时默认使用中文。技术术语（如代码、API 名称、参数名）保持原文不翻译。

⚠️ **安全警告**：交易涉及真实资金。默认使用 **模拟环境**（`TrdEnv.SIMULATE`），除非用户明确要求使用正式环境。

## 前提条件

1. **OpenD** 必须运行在 `127.0.0.1:11111`（可通过环境变量配置）
2. **futu-api** Python SDK（脚本首次运行时自动安装）

## 启动 OpenD

当用户说"启动 OpenD"、"打开 OpenD"、"运行 OpenD"时，**先检测本地是否已安装 OpenD**，再决定下一步操作。

### 检测是否已安装

**Windows**：
```powershell
Get-ChildItem -Path "C:\Users\$env:USERNAME\Desktop","C:\Program Files","C:\Program Files (x86)","D:\" -Recurse -Filter "*OpenD-GUI*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
```

**MacOS**：
```bash
ls /Applications/*OpenD-GUI*.app 2>/dev/null || mdfind "kMDItemFSName == '*OpenD-GUI*'" 2>/dev/null | head -1
```

### 判断逻辑

- **已安装（找到可执行文件）**：直接启动，不需要运行安装流程
  - Windows：`Start-Process "找到的exe路径"`
  - MacOS：`open "/Applications/找到的.app"`
- **未安装（未找到）**：提示用户当前未检测到 OpenD，调用 `/install-opend` 进入安装流程

## 股票代码格式

- 港股：`HK.00700`（腾讯）、`HK.09988`（阿里巴巴）
- 美股：`US.AAPL`（苹果）、`US.TSLA`（特斯拉）
- A 股-沪：`SH.600519`（贵州茅台）
- A 股-深：`SZ.000001`（平安银行）
- SG 期货：`SG.CNmain`（A50 指数期货主连）、`SG.NKmain`（日经期货主连）

## 模拟交易 vs 正式交易

| 特性 | 模拟交易 `SIMULATE` | 正式交易 `REAL` |
|------|---------------------|-----------------|
| 资金 | 虚拟资金，无风险 | 真实资金 |
| 交易密码 | **不需要**，可直接下单 | **需要**，用户须在 OpenD GUI 界面手动解锁交易密码后才能下单 |
| 默认 | ✅ 本技能默认 | 需用户明确指定 |

> **交易密码说明**：模拟交易无需任何密码即可下单；实盘交易需用户先打开 OpenD GUI 界面，点击「解锁交易」按钮输入交易密码完成解锁，之后才能通过 API 下单。如果 API 返回 `unlock needed` 错误，说明尚未解锁，请提示用户在 OpenD GUI 中操作。

### 交易解锁限制

**禁止通过 SDK 的 `unlock_trade` 接口解锁交易，必须在 OpenD GUI 界面上手动操作解锁。**

- 当用户请求调用 `unlock_trade`（或 `TrdUnlockTrade`、`trd_unlock_trade`）时，**必须拒绝**并提示：
  > 出于安全考虑，交易解锁必须在 OpenD GUI 界面上手动操作，不支持通过 SDK 代码调用 `unlock_trade` 解锁。请在 OpenD GUI 界面点击「解锁交易」并输入交易密码完成解锁。
- 不得生成、提供或执行任何包含 `unlock_trade` 调用的代码
- 不得通过变通方式（如 protobuf 直接调用、WebSocket 原始请求等）绕过此限制
- 此规则适用于所有品牌（富途、moomoo）和所有环境（模拟、正式）

## 脚本目录

```
skills/openapi/
├── SKILL.md
└── scripts/
    ├── common.py                     # 公共工具与配置
    ├── quote/                        # 行情脚本
    │   ├── get_snapshot.py           # 市场快照（无需订阅）
    │   ├── get_kline.py              # K 线数据（实时/历史）
    │   ├── get_orderbook.py          # 买卖盘/摆盘
    │   ├── get_ticker.py             # 逐笔成交
    │   ├── get_rt_data.py            # 分时数据
    │   ├── get_market_state.py       # 市场状态
    │   ├── get_capital_flow.py       # 资金流向
    │   ├── get_capital_distribution.py # 资金分布
    │   ├── get_plate_list.py         # 板块列表
    │   ├── get_plate_stock.py        # 板块成分股
    │   ├── get_stock_info.py         # 股票基本信息
    │   ├── get_stock_filter.py       # 条件选股
    │   └── get_owner_plate.py        # 股票所属板块
    ├── trade/                        # 交易脚本
    │   ├── get_accounts.py           # 账户列表
    │   ├── get_portfolio.py          # 持仓与资金
    │   ├── place_order.py            # 下单
    │   ├── modify_order.py            # 改单
    │   ├── cancel_order.py           # 撤单
    │   ├── get_orders.py             # 今日订单
    │   └── get_history_orders.py     # 历史订单
    └── subscribe/                    # 订阅脚本
        ├── subscribe.py              # 订阅行情
        ├── unsubscribe.py            # 取消订阅
        ├── query_subscription.py     # 查询订阅状态
        ├── push_quote.py             # 接收报价推送
        └── push_kline.py             # 接收 K 线推送
```

### 脚本路径查找规则

运行脚本前，**必须先确认脚本文件是否存在**。如果默认路径 `skills/openapi/scripts/` 下找不到脚本，则自动到 skill 的 base directory 下查找。

**执行流程**：

1. 先检查 `skills/openapi/scripts/{category}/{script}.py` 是否存在
2. 如果不存在，改用 `{SKILL_BASE_DIR}/scripts/{category}/{script}.py`（其中 `{SKILL_BASE_DIR}` 为 skill 加载时系统提示的 "Base directory for this skill" 路径）

**示例**：假设要运行 `get_accounts.py`，skill base directory 为 `/home/user/.claude/skills/openapi`：

```bash
# 先检查默认路径
ls skills/openapi/scripts/trade/get_accounts.py 2>/dev/null

# 如果不存在，则使用 skill base directory
ls /home/user/.claude/skills/openapi/scripts/trade/get_accounts.py 2>/dev/null
```

找到脚本后，用该路径执行 `python {找到的路径} [参数...]`。后续命令示例均使用默认路径 `skills/openapi/scripts/`，实际执行时按此规则查找。

---

## 行情命令

### 获取市场快照
当用户问 "报价"、"价格"、"行情" 时：
```bash
python skills/openapi/scripts/quote/get_snapshot.py US.AAPL HK.00700 [--json]
```

### 获取 K 线
当用户问 "K线"、"蜡烛图"、"历史走势" 时：
```bash
# 实时 K 线（最近 N 根）
python skills/openapi/scripts/quote/get_kline.py HK.00700 --ktype 1d --num 10

# 历史 K 线（日期范围）
python skills/openapi/scripts/quote/get_kline.py HK.00700 --ktype 1d --start 2025-01-01 --end 2025-12-31
```
- `--ktype`: 1m, 3m, 5m, 15m, 30m, 60m, 1d, 1w, 1M, 1Q, 1Y
- `--rehab`: none(不复权), forward(前复权, 默认), backward(后复权)
- `--num`: 实时 K 线数量（默认 10）
- `--json`: JSON 格式输出

### 获取买卖盘
当用户问 "买卖盘"、"摆盘"、"depth" 时：
```bash
python skills/openapi/scripts/quote/get_orderbook.py HK.00700 --num 10 [--json]
```

### 获取逐笔成交
当用户问 "逐笔"、"成交明细"、"ticker" 时：
```bash
python skills/openapi/scripts/quote/get_ticker.py HK.00700 --num 20 [--json]
```

### 获取分时数据
当用户问 "分时"、"intraday" 时：
```bash
python skills/openapi/scripts/quote/get_rt_data.py HK.00700 [--json]
```

### 获取市场状态
当用户问 "市场状态"、"开盘了吗" 时：
```bash
python skills/openapi/scripts/quote/get_market_state.py HK.00700 US.AAPL [--json]
```

### 获取资金流向
当用户问 "资金流向"、"资金流入流出" 时：
```bash
python skills/openapi/scripts/quote/get_capital_flow.py HK.00700 [--json]
```

### 获取资金分布
当用户问 "资金分布"、"大单小单"、"主力资金" 时：
```bash
python skills/openapi/scripts/quote/get_capital_distribution.py HK.00700 [--json]
```

### 获取板块列表
当用户问 "板块列表"、"概念板块"、"行业板块" 时：
```bash
python skills/openapi/scripts/quote/get_plate_list.py --market HK --type CONCEPT [--keyword 科技] [--limit 50] [--json]
```
- `--market`: HK, US, SH, SZ
- `--type`: ALL, INDUSTRY, REGION, CONCEPT
- `--keyword`/`-k`: 关键词过滤

### 获取板块成分股 / 指数成分股
当用户问 "板块股票"、"成分股"、"恒指成分股"、"指数成分股" 时：
```bash
python skills/openapi/scripts/quote/get_plate_stock.py hsi [--limit 30] [--json]
python skills/openapi/scripts/quote/get_plate_stock.py HK.BK1910 [--json]
python skills/openapi/scripts/quote/get_plate_stock.py --list-aliases  # 列出所有别名
```
- 支持查询板块成分股和**指数成分股**（如恒生指数、恒生科技指数等）
- 内置别名：`hsi`(恒指), `hstech`(恒生科技), `hk_ai`(AI), `hk_chip`(芯片), `hk_ev`(新能源车), `us_ai`(美股AI), `us_chip`(半导体), `us_chinese`(中概股) 等

#### 板块查询工作流
1. 首次查询运行 `--list-aliases` 获取别名列表并缓存
2. 匹配用户请求与缓存别名
3. 匹配不到时用 `get_plate_list.py --keyword` 搜索
4. 用搜索到的板块代码调用 `get_plate_stock.py`

### 获取股票信息
当用户问 "股票信息"、"基本信息" 时：
```bash
python skills/openapi/scripts/quote/get_stock_info.py US.AAPL,HK.00700 [--json]
```
- 底层使用 `get_market_snapshot`，返回包含实时行情的快照数据（含价格、市值、市盈率等）
- 每次最多 400 个标的

### 条件选股
当用户问 "选股"、"筛选"、"stock filter" 时：
```bash
python skills/openapi/scripts/quote/get_stock_filter.py --market HK [条件] [--sort 字段] [--limit 20] [--json]
```
条件参数：
- 价格：`--min-price`, `--max-price`
- 市值（亿）：`--min-market-cap`, `--max-market-cap`
- PE：`--min-pe`, `--max-pe`
- PB：`--min-pb`, `--max-pb`
- 涨跌幅(%)：`--min-change-rate`, `--max-change-rate`
- 成交量：`--min-volume`
- 换手率(%)：`--min-turnover-rate`, `--max-turnover-rate`
- 排序：`--sort` (market_val/price/volume/turnover/turnover_rate/change_rate/pe/pb)
- `--asc`: 升序

示例：
```bash
# 港股市值前20
python skills/openapi/scripts/quote/get_stock_filter.py --market HK --sort market_val --limit 20
# PE 在 10-30 之间
python skills/openapi/scripts/quote/get_stock_filter.py --market US --min-pe 10 --max-pe 30
# 涨幅前10
python skills/openapi/scripts/quote/get_stock_filter.py --market HK --sort change_rate --limit 10
```

### 获取股票所属板块
当用户问 "所属板块"、"属于哪些板块" 时：
```bash
python skills/openapi/scripts/quote/get_owner_plate.py HK.00700 US.AAPL [--json]
```

---

## 交易命令

### 获取账户列表
当用户问 "我的账户"、"账户列表" 时：
```bash
python skills/openapi/scripts/trade/get_accounts.py [--json]
```
脚本会自动遍历所有 `SecurityFirm` 枚举值（FUTUSECURITIES、FUTUINC、FUTUSG、FUTUAU、FUTUCA、FUTUJP、FUTUMY 等），按 `acc_id` 去重合并，确保不同券商下的实盘账户都能被获取到。

JSON 输出包含 `trdmarket_auth` 字段，表示该账户拥有交易权限的市场列表（如 `["HK", "US", "HKCC"]`）；`acc_role` 字段表示账户角色（如 `MASTER` 为主账户）。下单时应选择 `trdmarket_auth` 包含目标市场且 `acc_role` 不是 `MASTER` 的账户。

### 获取持仓与资金
当用户问 "持仓"、"资金"、"我的股票" 时：
```bash
python skills/openapi/scripts/trade/get_portfolio.py [--market HK] [--trd-env SIMULATE] [--acc-id 12345] [--json]
```
- `--market`: US, HK, HKCC, CN, SG
- `--trd-env`: REAL, SIMULATE（默认 SIMULATE）

### 下单
当用户问 "买入"、"卖出"、"下单" 时：
```bash
python skills/openapi/scripts/trade/place_order.py --code US.AAPL --side BUY --quantity 10 --price 150.0 [--order-type NORMAL] [--market US] [--trd-env SIMULATE] [--json]
```
- `--code`: 股票代码（必填）
- `--side`: BUY/SELL（必填）
- `--quantity`: 数量（必填）
- `--price`: 价格（限价单必填，市价单不需要）
- `--order-type`: NORMAL(限价单) / MARKET(市价单)
- **下单前务必与用户确认代码、方向、数量、价格**

#### 模拟交易下单流程

模拟交易（`--trd-env SIMULATE`，默认）直接执行下单命令即可：
```bash
python skills/openapi/scripts/trade/place_order.py --code {code} --side {side} --quantity {qty} --price {price} --market {market} --trd-env SIMULATE
```

#### 实盘下单流程

当用户要求实盘（`--trd-env REAL`）下单时，**必须执行以下流程**：

1. **查询账户列表并选择有权限的账户**：
   先运行 `get_accounts.py --json` 获取所有账户，根据股票代码确定目标交易市场（如 HK.00700 → HK），筛选出 `trd_env` 为 `REAL` 且 `trdmarket_auth` 包含该市场 **且 `acc_role` 不是 `MASTER`** 的账户。主账户（MASTER）不允许下单，必须排除。
   - 如果只有 1 个符合条件的账户，直接使用
   - 如果有多个符合条件的账户，用 AskUserQuestion 让用户选择：
     ```
     问题: "请选择交易账户："
       header: "账户选择"
       选项:（列出所有符合条件的账户）
         - "账户 {acc_id} ({card_num})" : 角色: {acc_role}, 交易市场权限: {trdmarket_auth}
     ```
   - 如果没有符合条件的账户，提示用户当前无支持该市场的实盘账户（注意：MASTER 角色的账户不能用于下单）

2. **用 AskUserQuestion 进行二次确认**，明确展示订单详情：
   ```
   问题: "确认实盘下单？这将使用真实资金。"
     header: "实盘确认"
     选项:
       - "确认下单" : 账户: {acc_id}, 代码: {code}, 方向: {BUY/SELL}, 数量: {qty}, 价格: {price}
       - "取消" : 不执行下单
   ```
   用户选择"确认下单"后才能继续，选择"取消"则终止。

3. **执行下单命令**，带上 `--acc-id`：
   ```bash
   python skills/openapi/scripts/trade/place_order.py --code {code} --side {side} --quantity {qty} --price {price} --market {market} --trd-env REAL --acc-id {acc_id}
   ```

   > **注意**：如果 API 返回 `unlock needed` 或类似解锁错误，提示用户需先在 **OpenD GUI 界面手动解锁交易密码**（菜单或界面中的"解锁交易"按钮），解锁后重新执行下单。

### 改单
当用户问 "改单"、"修改订单"、"修改价格"、"修改数量" 时：
```bash
python skills/openapi/scripts/trade/modify_order.py --order-id 12345678 --price 410 --quantity 200 [--market HK] [--trd-env SIMULATE] [--acc-id 12345] [--json]
```
- `--order-id`: 订单 ID（必填）
- `--price`: 修改后的价格（可选）
- `--quantity`: 修改后的总数量，非增量（可选）
- 至少提供 `--price` 或 `--quantity` 之一
- A 股通市场不支持改单
- 用户未给出订单 ID 时，先用 `get_orders.py` 查询

### 撤单
当用户问 "撤单"、"取消订单" 时：
```bash
python skills/openapi/scripts/trade/cancel_order.py --order-id 12345678 [--acc-id 12345] [--market HK] [--trd-env SIMULATE] [--json]
```
- 用户未给出订单 ID 时，先用 `get_orders.py` 查询

### 查询今日订单
当用户问 "订单"、"我的委托" 时：
```bash
python skills/openapi/scripts/trade/get_orders.py [--market HK] [--trd-env SIMULATE] [--acc-id 12345] [--json]
```

### 查询历史订单
当用户问 "历史订单"、"过去的委托" 时：
```bash
python skills/openapi/scripts/trade/get_history_orders.py [--acc-id 12345] [--market HK] [--trd-env SIMULATE] [--start 2026-01-01] [--end 2026-03-01] [--code US.AAPL] [--status FILLED_ALL CANCELLED_ALL] [--limit 200] [--json]
```

---

## 期货交易命令

期货交易必须使用 **`OpenFutureTradeContext`**（而非证券交易的 `OpenSecTradeContext`），现有交易脚本（`place_order.py` 等）使用的是 `OpenSecTradeContext`，**不适用于期货**。期货交易需直接生成 Python 代码执行。

### 期货 vs 证券的关键区别

| 特性 | 证券交易 | 期货交易 |
|------|---------|---------|
| 上下文 | `OpenSecTradeContext` | `OpenFutureTradeContext` |
| 现有脚本 | `place_order.py` 等可用 | 不可用，需生成代码 |
| 模拟账户 | 按市场统一分配 | 按市场独立分配（如 `FUTURES_SIMULATE_SG`） |
| 合约代码 | 股票代码（如 `HK.00700`） | 期货主连代码（如 `SG.CNmain`），下单后自动映射到实际月份合约 |
| 数量单位 | 股 | 张（手） |

### SG 期货合约代码

常见 SG 期货主力合约（使用 `主连` 代码下单，系统自动映射到当月合约）：

| 代码 | 名称 | 每手 |
|------|------|------|
| `SG.CNmain` | A50 指数期货主连 | 1 |
| `SG.NKmain` | 日经期货主连 | 500 |
| `SG.FEFmain` | 铁矿期货主连 | 100 |
| `SG.SGPmain` | MSCI 新指期货主连 | 100 |
| `SG.TWNmain` | FTSE 台指期货主连 | 40 |

查询所有 SG 期货合约：
```python
from futu import *
quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
ret, data = quote_ctx.get_stock_basicinfo(Market.SG, SecurityType.FUTURE)
# 筛选主力合约
main_contracts = data[data['main_contract'] == True]
print(main_contracts[['code', 'name', 'lot_size']].to_string())
quote_ctx.close()
```

### 查询期货账户

期货账户通过 `OpenFutureTradeContext` 查询，与证券账户分开管理：

```python
from futu import *
trd_ctx = OpenFutureTradeContext(host='127.0.0.1', port=11111)
ret, data = trd_ctx.get_acc_list()
print(data.to_string())
trd_ctx.close()
```

期货模拟账户按市场独立分配，关注 `trdmarket_auth` 字段：
- `FUTURES_SIMULATE_SG`：SG 期货模拟
- `FUTURES_SIMULATE_HK`：HK 期货模拟
- `FUTURES_SIMULATE_US`：US 期货模拟
- `FUTURES_SIMULATE_JP`：JP 期货模拟
- `FUTURES`：实盘期货

### 期货模拟交易下单流程

模拟交易（`TrdEnv.SIMULATE`）流程如下：

1. 用 `OpenFutureTradeContext` 查询账户，找到 `trdmarket_auth` 包含对应模拟市场的账户（如 `FUTURES_SIMULATE_SG`）
2. 获取合约行情确认价格
3. 用 AskUserQuestion 确认下单参数（合约、方向、数量、价格）
4. 执行下单

```python
from futu import *

trd_ctx = OpenFutureTradeContext(host='127.0.0.1', port=11111)

ret, data = trd_ctx.place_order(
    price=14782.0,         # 限价
    qty=1,                 # 数量（张）
    code='SG.CNmain',      # 主连代码，自动映射到实际合约
    trd_side=TrdSide.BUY,
    order_type=OrderType.NORMAL,
    trd_env=TrdEnv.SIMULATE,
    acc_id=9492210         # 模拟账户 ID
)

if ret == RET_OK:
    print('下单成功:', data)
else:
    print('下单失败:', data)

trd_ctx.close()
```

### 期货实盘下单流程

当用户要求实盘（`TrdEnv.REAL`）下单期货时，**必须执行以下流程**：

1. **查询期货账户并选择有权限的账户**：
   用 `OpenFutureTradeContext` 的 `get_acc_list()` 获取所有期货账户，筛选出 `trd_env` 为 `REAL` 且 `trdmarket_auth` 包含 `FUTURES` 且 `acc_role` 不是 `MASTER` 的账户。
   - 如果只有 1 个符合条件的账户，直接使用
   - 如果有多个符合条件的账户，用 AskUserQuestion 让用户选择
   - 如果没有符合条件的账户，提示用户当前无实盘期货账户

2. **用 AskUserQuestion 进行二次确认**，明确展示订单详情：
   ```
   问题: "确认实盘下单期货？这将使用真实资金。"
     header: "实盘确认"
     选项:
       - "确认下单" : 账户: {acc_id}, 合约: {code}, 方向: {BUY/SELL}, 数量: {qty}张, 价格: {price}
       - "取消" : 不执行下单
   ```

3. **执行下单代码**：

   > **注意**：如果 API 返回 `unlock needed` 或类似解锁错误，提示用户需先在 **OpenD GUI 界面手动解锁交易密码**，解锁后重新执行下单。

```python
from futu import *

trd_ctx = OpenFutureTradeContext(host='127.0.0.1', port=11111)

# 实盘下单
ret, data = trd_ctx.place_order(
    price=14785.0,
    qty=1,
    code='SG.CNmain',
    trd_side=TrdSide.BUY,
    order_type=OrderType.NORMAL,
    trd_env=TrdEnv.REAL,
    acc_id=281756475296104250  # 实盘期货账户 ID
)

if ret == RET_OK:
    print('实盘下单成功:', data)
else:
    print('下单失败:', data)

trd_ctx.close()
```

### 期货持仓与资金查询

```python
from futu import *

trd_ctx = OpenFutureTradeContext(host='127.0.0.1', port=11111)

# 查询持仓
ret, data = trd_ctx.position_list_query(trd_env=TrdEnv.SIMULATE, acc_id=9492210)
if ret == RET_OK:
    print(data)

# 查询账户资金
ret, data = trd_ctx.accinfo_query(trd_env=TrdEnv.SIMULATE, acc_id=9492210)
if ret == RET_OK:
    print(data)

trd_ctx.close()
```

### 期货订单查询与撤单

```python
from futu import *

trd_ctx = OpenFutureTradeContext(host='127.0.0.1', port=11111)

# 查询今日订单
ret, data = trd_ctx.order_list_query(trd_env=TrdEnv.SIMULATE, acc_id=9492210)
if ret == RET_OK:
    print(data)

# 撤单
ret, data = trd_ctx.modify_order(
    modify_order_op=ModifyOrderOp.CANCEL,
    order_id='7679570',
    qty=0, price=0,
    trd_env=TrdEnv.SIMULATE,
    acc_id=9492210
)

trd_ctx.close()
```

### 期货合约信息查询

```python
from futu import *
quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
ret, data = quote_ctx.get_future_info(['SG.CNmain', 'SG.NKmain'])
if ret == RET_OK:
    print(data)  # 包含合约乘数、最小变动价位、交易时间等
quote_ctx.close()
```

---

## 订阅管理命令

### 订阅行情
当用户需要订阅实时数据时：
```bash
python skills/openapi/scripts/subscribe/subscribe.py HK.00700 --types QUOTE ORDER_BOOK [--json]
```
- `--types`: 订阅类型列表（必填）
- `--no-first-push`: 不立即推送缓存数据
- `--push`: 开启推送回调
- `--extended-time`: 美股盘前盘后数据

**可用订阅类型**：QUOTE, ORDER_BOOK, TICKER, RT_DATA, BROKER, K_1M, K_5M, K_15M, K_30M, K_60M, K_DAY, K_WEEK, K_MON

### 取消订阅
```bash
# 取消指定订阅
python skills/openapi/scripts/subscribe/unsubscribe.py HK.00700 --types QUOTE ORDER_BOOK [--json]

# 取消所有订阅
python skills/openapi/scripts/subscribe/unsubscribe.py --all [--json]
```
- **注意**：订阅后至少 1 分钟才能取消

### 查询订阅状态
当用户问 "已订阅什么"、"订阅状态" 时：
```bash
python skills/openapi/scripts/subscribe/query_subscription.py [--current] [--json]
```
- `--current`: 只查询当前连接（默认查询所有连接）

---

## 推送接收命令

### 接收报价推送
当用户需要实时报价推送时：
```bash
python skills/openapi/scripts/subscribe/push_quote.py HK.00700 US.AAPL --duration 60 [--json]
```
- `--duration`: 持续接收时间（秒，默认 60）
- 按 Ctrl+C 可提前停止

### 接收 K 线推送
当用户需要实时 K 线推送时：
```bash
python skills/openapi/scripts/subscribe/push_kline.py HK.00700 --ktype K_1M --duration 300 [--json]
```
- `--ktype`: K_1M, K_5M, K_15M, K_30M, K_60M, K_DAY, K_WEEK, K_MON（默认: K_1M）
- `--duration`: 持续接收时间（秒，默认 300）

---

## 通用选项

所有脚本支持 `--json` 参数输出 JSON 格式，便于程序解析。

大多数交易脚本支持：
- `--market`: US, HK, HKCC, CN, SG
- `--trd-env`: REAL, SIMULATE（默认: SIMULATE）
- `--acc-id`: 账户 ID（可选）

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `FUTU_OPEND_HOST` | OpenD 主机 | 127.0.0.1 |
| `FUTU_OPEND_PORT` | OpenD 端口 | 11111 |
| `FUTU_TRD_ENV` | 交易环境 | SIMULATE |
| `FUTU_DEFAULT_MARKET` | 默认市场 | US |
| ~~`FUTU_TRADE_PWD`~~ | ~~交易密码~~ | 已移除，需在 OpenD GUI 手动解锁 |
| `FUTU_ACC_ID` | 默认账户 ID | （首个账户） |
| `FUTU_BRAND` | 客户端品牌（`futu` 或 `moomoo`），用于行情权限提示链接自适应 | （未设置时同时显示两个链接） |

## API 速查（完整函数签名）

### 行情 API（OpenQuoteContext）

#### 订阅管理（4 个）

```
subscribe(code_list, subtype_list, is_first_push=True, subscribe_push=True, is_detailed_orderbook=False, extended_time=False, session=Session.NONE)  -- 订阅(消耗订阅额度, 每只股票每个类型占1个额度; 调用前应先用 query_subscription 检查额度)
unsubscribe(code_list, subtype_list, unsubscribe_all=False)  -- 反订阅(订阅后至少1分钟才能反订阅)
unsubscribe_all()  -- 反订阅所有
query_subscription(is_all_conn=True)  -- 查询订阅状态(调用subscribe前应先检查)
```

#### 实时数据 - 需要先订阅（6 个）

```
get_stock_quote(code_list)  -- 获取实时报价
get_cur_kline(code, num, ktype=KLType.K_DAY, autype=AuType.QFQ)  -- 获取实时 K 线
get_rt_data(code)  -- 获取实时分时
get_rt_ticker(code, num=500)  -- 获取实时逐笔
get_order_book(code, num=10)  -- 获取实时摆盘
get_broker_queue(code)  -- 获取实时经纪队列(仅港股)
```

#### 快照与历史（4 个）

```
get_market_snapshot(code_list)  -- 获取快照(无需订阅, 每次最多400个)
request_history_kline(code, start=None, end=None, ktype=KLType.K_DAY, autype=AuType.QFQ, fields=[KL_FIELD.ALL], max_count=1000, page_req_key=None, extended_time=False, session=Session.NONE)  -- 获取历史K线(消耗历史K线额度, 调用前应先用 get_history_kl_quota 检查剩余额度; 单次max_count最大1000, 超过需用page_req_key翻页)
get_rehab(code)  -- 获取复权因子
get_history_kl_quota(get_detail=False)  -- 查询历史K线额度(调用request_history_kline前应先检查)
```

#### 基础信息（5 个）

```
get_stock_basicinfo(market, stock_type=SecurityType.STOCK, code_list=None)  -- 获取股票静态信息
get_global_state()  -- 获取各市场状态（返回 dict，key 包括 market_hk/market_us/market_sh/market_sz/market_hkfuture/market_usfuture/server_ver/qot_logined/trd_logined 等）
request_trading_days(market=None, start=None, end=None, code=None)  -- 获取交易日历
get_market_state(code_list)  -- 获取市场状态
get_stock_filter(market, filter_list, plate_code=None, begin=0, num=200)  -- 条件选股
```

#### 板块（3 个）

```
get_plate_list(market, plate_class)  -- 获取板块列表
get_plate_stock(plate_code, sort_field=SortField.CODE, ascend=True)  -- 获取板块内股票
get_owner_plate(code_list)  -- 获取股票所属板块
```

#### 衍生品（5 个）

```
get_option_chain(code, index_option_type=IndexOptionType.NORMAL, start=None, end=None, option_type=OptionType.ALL, option_cond_type=OptionCondType.ALL, data_filter=None)  -- 获取期权链
get_option_expiration_date(code, index_option_type=IndexOptionType.NORMAL)  -- 获取期权到期日
get_referencestock_list(code, reference_type)  -- 获取关联股票(正股/窝轮/牛熊/期权)
get_future_info(code_list)  -- 获取期货合约信息
get_warrant(stock_owner='', req=None)  -- 获取窝轮/牛熊证
```

#### 资金（2 个）

```
get_capital_flow(stock_code, period_type=PeriodType.INTRADAY, start=None, end=None)  -- 获取资金流向
get_capital_distribution(stock_code)  -- 获取资金分布
```

#### 自选股（3 个）

```
get_user_security_group(group_type=UserSecurityGroupType.ALL)  -- 获取自选股分组
get_user_security(group_name)  -- 获取自选股列表
modify_user_security(group_name, op, code_list)  -- 修改自选股
```

#### 到价提醒（2 个）

```
get_price_reminder(code=None, market=None)  -- 获取到价提醒
set_price_reminder(code, op, key=None, reminder_type=None, reminder_freq=None, value=None, note=None)  -- 设置到价提醒
```

#### IPO（1 个）

```
get_ipo_list(market)  -- 获取IPO列表
```

**行情 API 小计：35 个**

---

### 交易 API（OpenSecTradeContext / OpenFutureTradeContext）

#### 账户（3 个）

```
get_acc_list()  -- 获取交易业务账户列表
unlock_trade(password=None, password_md5=None, is_unlock=True)  -- 解锁/锁定交易（⚠️ 本技能不通过 API 解锁，需用户在 OpenD GUI 手动解锁）
accinfo_query(trd_env=TrdEnv.REAL, acc_id=0, acc_index=0, refresh_cache=False, currency=Currency.HKD, asset_category=AssetCategory.NONE)  -- 查询账户资金
```

#### 下单改单（3 个）

```
place_order(price, qty, code, trd_side, order_type=OrderType.NORMAL, adjust_limit=0, trd_env=TrdEnv.REAL, acc_id=0, acc_index=0, remark=None, time_in_force=TimeInForce.DAY, fill_outside_rth=False, aux_price=None, trail_type=None, trail_value=None, trail_spread=None, session=Session.NONE)  -- 下单(限频: 15次/30秒)
modify_order(modify_order_op, order_id, qty, price, adjust_limit=0, trd_env=TrdEnv.REAL, acc_id=0, acc_index=0, aux_price=None, trail_type=None, trail_value=None, trail_spread=None)  -- 改单/撤单(限频: 20次/30秒)
cancel_all_order(trd_env=TrdEnv.REAL, acc_id=0, acc_index=0, trdmarket=TrdMarket.NONE)  -- 撤销所有订单
```

#### 订单查询（3 个）

```
order_list_query(order_id="", order_market=TrdMarket.NONE, status_filter_list=[], code='', start='', end='', trd_env=TrdEnv.REAL, acc_id=0, acc_index=0, refresh_cache=False)  -- 查询今日订单
history_order_list_query(status_filter_list=[], code='', order_market=TrdMarket.NONE, start='', end='', trd_env=TrdEnv.REAL, acc_id=0, acc_index=0)  -- 查询历史订单
order_fee_query(order_id_list=[], acc_id=0, acc_index=0, trd_env=TrdEnv.REAL)  -- 查询订单费用
```

#### 成交查询（2 个）

```
deal_list_query(code="", deal_market=TrdMarket.NONE, trd_env=TrdEnv.REAL, acc_id=0, acc_index=0, refresh_cache=False)  -- 查询今日成交
history_deal_list_query(code='', deal_market=TrdMarket.NONE, start='', end='', trd_env=TrdEnv.REAL, acc_id=0, acc_index=0)  -- 查询历史成交
```

#### 持仓与资金（4 个）

```
position_list_query(code='', position_market=TrdMarket.NONE, pl_ratio_min=None, pl_ratio_max=None, trd_env=TrdEnv.REAL, acc_id=0, acc_index=0, refresh_cache=False)  -- 查询持仓
acctradinginfo_query(order_type, code, price, order_id=None, adjust_limit=0, trd_env=TrdEnv.REAL, acc_id=0, acc_index=0)  -- 查询最大可买/卖数量
get_acc_cash_flow(clearing_date='', trd_env=TrdEnv.REAL, acc_id=0, acc_index=0, cashflow_direction=CashFlowDirection.NONE)  -- 查询账户现金流水
get_margin_ratio(code_list)  -- 查询融资融券比率
```

**交易 API 小计：15 个**

---

### 推送 Handler（9 个）

#### 行情推送（7 个）

```
StockQuoteHandlerBase   -- 报价推送回调
OrderBookHandlerBase    -- 摆盘推送回调
CurKlineHandlerBase     -- K线推送回调
TickerHandlerBase       -- 逐笔推送回调
RTDataHandlerBase       -- 分时推送回调
BrokerHandlerBase       -- 经纪队列推送回调
PriceReminderHandlerBase -- 到价提醒推送回调
```

#### 交易推送（2 个）

```
TradeOrderHandlerBase   -- 订单状态推送回调
TradeDealHandlerBase    -- 成交推送回调
```

注意：交易推送不需要单独订阅，设置 Handler 后自动接收。

---

### 基础接口

```
OpenQuoteContext(host='127.0.0.1', port=11111)  -- 创建行情连接
OpenSecTradeContext(filter_trdmarket=TrdMarket.HK, host='127.0.0.1', port=11111, security_firm=SecurityFirm.FUTUSECURITIES)  -- 创建证券交易连接
OpenFutureTradeContext(host='127.0.0.1', port=11111, security_firm=SecurityFirm.FUTUSECURITIES)  -- 创建期货交易连接
ctx.close()  -- 关闭连接
ctx.set_handler(handler)  -- 注册推送回调
SysNotifyHandlerBase  -- 系统通知回调
```

**全部 API 总计：行情 35 + 交易 15 + 推送 Handler 9 + 基础 6 = 65 个接口**

## SubType 订阅类型完整列表

| SubType | 说明 | 对应推送 Handler |
|---------|------|-----------------|
| `QUOTE` | 报价 | `StockQuoteHandlerBase` |
| `ORDER_BOOK` | 摆盘 | `OrderBookHandlerBase` |
| `TICKER` | 逐笔 | `TickerHandlerBase` |
| `K_1M` ~ `K_MON` | K 线 | `CurKlineHandlerBase` |
| `RT_DATA` | 分时 | `RTDataHandlerBase` |
| `BROKER` | 经纪队列（仅港股） | `BrokerHandlerBase` |

## 交易推送 Handler 类

| Handler 基类 | 说明 |
|-------------|------|
| `TradeOrderHandlerBase` | 订单状态推送 |
| `TradeDealHandlerBase` | 成交推送 |

注意：交易推送不需要单独订阅，设置 Handler 后自动接收。

## 关键枚举值

- **TrdSide**: `BUY` | `SELL`
- **OrderType**: `NORMAL`(限价) | `MARKET`(市价)
- **TrdEnv**: `REAL` | `SIMULATE`
- **ModifyOrderOp**: `NORMAL`(改单) | `CANCEL`(撤单)
- **TrdMarket**: `HK` | `US` | `CN` | `HKCC` | `SG`

## 接口限制（调用前必须考虑）

调用接口时必须考虑以下限制，避免因额度不足或频率超限导致请求失败。

### 频率限制

限频规则：30 秒内最多 n 次，第 1 次和第 n+1 次的间隔需大于 30 秒。

| 接口 | 限频 |
|------|------|
| `place_order` | 15 次/30 秒 |
| `modify_order` | 20 次/30 秒 |
| `order_list_query` | 10 次/30 秒 |

**批量操作注意**：当需要循环调用受限频接口时（如批量下单、批量查询历史K线），必须在循环中加入适当的 `time.sleep()` 间隔，避免触发限频。

### 订阅额度限制

- 每只股票订阅一个类型占 1 个订阅额度，取消订阅释放额度
- 同一只股票的不同 SubType 分别计数
- 订阅后至少 1 分钟才能反订阅
- 反订阅后需所有连接都反订阅同一标的，额度才会释放
- 不足 1 分钟关闭连接不会释放订阅额度，需等待 1 分钟后自动反订阅
- 通过 `query_subscription.py` 查询已使用的额度
- 香港市场需要 LV1 及以上权限才能订阅
- 美股盘前盘后需设置 `--extended-time`

### 历史 K 线额度限制

- 最近 30 天内，每请求 1 只股票的历史 K 线占 1 个额度
- 30 天内重复请求同一只股票不会重复累计
- 同一股票不同周期的 K 线只占 1 个额度
- **调用 `request_history_kline` 前**，应先通过 `get_history_kl_quota(get_detail=True)` 检查剩余额度是否充足
- **批量获取多只股票 K 线时**，先检查额度，确认剩余额度 >= 需要请求的股票数量后再执行

### 额度等级

订阅额度和历史 K 线额度根据用户资产和交易活跃度分级：

| 用户类型 | 订阅额度 | 历史 K 线额度 |
|---------|---------|-------------|
| 开户用户 | 100 | 100 |
| 总资产达 1 万 HKD | 300 | 300 |
| 总资产达 50 万 HKD / 月交易笔数 > 200 / 月交易额 > 200 万 HKD（任一） | 1000 | 1000 |
| 总资产达 500 万 HKD / 月交易笔数 > 2000 / 月交易额 > 2000 万 HKD（任一） | 2000 | 2000 |

### 其他限制

| 接口 | 限制 |
|------|------|
| `get_market_snapshot` | 每次最多 400 个标的 |
| `get_order_book` | num 最大为 10 |
| `get_rt_ticker` | num 最大 1000 |
| `get_cur_kline` | num 最大 1000 |
| `request_history_kline` | 单次 max_count 最大 1000，超过需用 page_req_key 翻页 |
| `get_stock_filter` | 单次最多 200 个结果 |

## 自定义 Handler 模板

对于脚本未覆盖的推送类型（如摆盘、逐笔、交易推送），可生成临时代码：

```python
import time
from futu import *

class MyHandler(OrderBookHandlerBase):  # 替换为需要的 Handler 基类
    def on_recv_rsp(self, rsp_pb):
        ret_code, data = super().on_recv_rsp(rsp_pb)
        if ret_code != RET_OK:
            print("error:", data)
            return RET_ERROR, data
        print("收到推送:")
        print(data)
        return RET_OK, data

quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
quote_ctx.set_handler(MyHandler())
ret, data = quote_ctx.subscribe(['HK.00700'], [SubType.ORDER_BOOK], subscribe_push=True)
if ret == RET_OK:
    print('订阅成功，等待推送...')
time.sleep(60)
quote_ctx.close()
```

## 已知问题

### pandas 与 numpy 版本不兼容

**现象**：运行代码时报错 `ValueError: numpy.dtype size changed`。

**解决**：`pip install --upgrade pandas`

## 错误处理

| 错误 | 解决 |
|------|------|
| 连接失败 | 启动 OpenD |
| 订单不存在 | 用 get_orders.py 检查 |
| 未找到账户 | 用 get_accounts.py 检查 |
| 解锁交易失败 / `unlock needed` | 需在 OpenD GUI 界面手动解锁交易密码 |
| 行情权限不足（如订阅失败、BMP 权限不支持等） | 提示用户开通行情权限，根据用户使用的客户端提供对应链接：牛牛用户 → https://openapi.futunn.com/futu-api-doc/intro/authority.html ；moomoo 用户 → https://openapi.moomoo.com/moomoo-api-doc/en/intro/authority.html |
| 期货购买力不足 | 提示用户入金或平仓部分合约释放保证金 |
| 期货用 OpenSecTradeContext 下单失败 | 期货必须使用 `OpenFutureTradeContext`，不能用证券交易上下文 |
| 实盘下单 `Nonexisting acc_id` | `get_accounts.py --json` 输出的 acc_id 可能因 `safe_int` 中 `int(float())` 导致大整数精度丢失（已修复）。如仍遇到，用 `filter_trdmarket=TrdMarket.NONE` 创建上下文并直接打印 DataFrame 核对真实 acc_id |
| 实盘下单 `没有解锁交易` / `unlock needed` | 实盘交易需用户先在 **OpenD GUI** 界面点击「解锁交易」输入交易密码，API 无法代替此操作。解锁后重新执行下单即可 |
| 账户购买力不足 | 账户可用资金不足以完成下单。用 `get_portfolio.py` 查看资金详情，可减少数量、卖出持仓释放资金、或入金后重试 |
| 模拟账户资金不足 | 模拟账户资金不足时有两种方式恢复：1）卖出当前持仓股票释放资金；2）在手机 App 中重置模拟账户（路径：牛牛用户 → 我的 → 模拟交易 → 我的头像 → 我的道具 → 复活卡，参考 https://openapi.futunn.com/futu-api-doc/qa/trade.html#1690 ；moomoo 用户 → Me → Paper Trading → Avatar → My Items → Revival Card，参考 https://openapi.moomoo.com/moomoo-api-doc/qa/trade.html#1690 ）。注意：重置后账户资金恢复初始值，但历史订单记录会被清空 |

## 响应规则

1. **默认使用模拟环境** `SIMULATE`，除非用户明确要求正式交易
2. **优先使用脚本**：对于上述列出的功能，直接运行对应的 Python 脚本
3. **脚本无法覆盖的需求**：生成临时 .py 文件执行，执行后删除
4. 使用正确的股票代码格式
5. 涉及下单时，提醒用户确认价格、数量和方向
6. 当用户说"正式"、"实盘"、"真实"时使用 `--trd-env REAL`
7. **实盘下单必须二次确认**：严格按照"实盘下单流程"执行，先 AskUserQuestion 确认订单详情，再执行下单。如果 API 返回解锁错误，提示用户在 OpenD GUI 界面手动解锁交易密码。**例外**：当用户要求运行其自己编写的策略脚本时，无需每次下单前二次确认，因为策略脚本的下单逻辑由用户自行控制
8. 所有脚本支持 `--json` 参数便于解析
9. 对于不清楚的接口，先在本技能的 API 速查中查找
10. **期货交易必须使用 `OpenFutureTradeContext`**：现有交易脚本使用 `OpenSecTradeContext`，不适用于期货。期货下单、查询持仓、撤单等操作需直接生成 Python 代码执行，参照"期货交易命令"章节
11. **回测使用纯后台模式**：当用户要求回测或运行回测脚本时，不使用任何 GUI 组件，使用纯后台回测模式，图表保存为文件而非弹窗显示
12. **调用接口前检查限制**：
    - 调用 `request_history_kline` 前，先用 `get_history_kl_quota()` 检查历史K线剩余额度
    - 调用 `subscribe` 前，先用 `query_subscription()` 检查订阅额度使用情况
    - 批量操作时（循环下单、批量获取K线等），加入 `time.sleep()` 避免触发限频
    - 批量获取快照时，每次不超过 400 个标的，超过需分批
    - 历史K线单次最多 1000 条，超过需用 `page_req_key` 翻页

用户需求：$ARGUMENTS
