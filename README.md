# Futu Quantitative Trading System

基于富途 OpenD API 的美股量化交易系统。通过技术指标策略自动生成买卖信号，配合风控规则和仓位管理，实现模拟/实盘自动交易。

## 项目结构

```
futu-trading-system/
├── src/
│   ├── main.py              # 入口：启动所有组件
│   ├── core/                # 核心数据结构（Signal, Position, Config）
│   ├── data/                # 行情数据采集与存储（K线、报价）
│   ├── strategy/            # 5 个技术指标策略
│   ├── risk/                # 风控引擎（止损、止盈、追踪止损）
│   ├── execution/           # 订单执行器（下单、撤单、重试）
│   ├── notify/              # 通知模块（控制台、文件、Telegram）
│   └── backtest/            # 回测引擎（支持多策略、多股票）
├── config/
│   └── config.example.yaml  # 配置模板（复制为 config.yaml 使用）
├── deploy/gcp/              # Google Cloud 部署脚本
├── backtest_results.xlsx           # 10年回测结果
├── backtest_longterm_results.xlsx  # 长周期回测结果（最长25年）
└── requirements.txt
```

## 快速开始

### 前置条件

- Python 3.11+
- [富途牛牛](https://www.futunn.com/) 账号（模拟或实盘）
- [Futu OpenD](https://openapi.futunn.com/futu-api-doc/en/opend/opend-intro.html) 已安装并运行

### 安装

```bash
git clone https://github.com/wesleywu99/futu-trading-system.git
cd futu-trading-system
pip install -r requirements.txt
cp config/config.example.yaml config/config.yaml
# 编辑 config.yaml，填入你的富途账号信息
```

### 运行

```bash
# 确保 Futu OpenD 已启动并登录
python -m src.main
```

### 运行回测

```bash
python -m src.backtest.run
```

回测结果会输出到 `backtest_results.xlsx` 和 `backtest_longterm_results.xlsx`。

## 策略说明

系统包含 5 个技术指标策略 + 2 个安全策略。每只股票分配其回测最优策略：

### 策略-股票映射（基于回测优化）

| 股票 | 分配策略 | 10年 Sharpe | 25年 Sharpe | 核心逻辑 |
|------|---------|------------|------------|---------|
| **NVDA** | MACD Trend | 1.18 | 0.86 | MACD 金叉/死叉 + EMA30 趋势过滤 |
| **GOOGL** | ADX+MACD | 0.98 | 0.72 | ADX 趋势强度 + EMA 排列 + MACD 确认 |
| **TSLA** | MACD Trend | 0.58 | 0.51 | MACD 金叉/死叉 + EMA30 趋势过滤 |

### 策略详解

#### 1. MACD Trend Following (`macd_trend`)
- **适用**: NVDA, TSLA
- **参数**: fast=12, slow=26, signal=9, trend_ema=30
- **买入条件**: MACD 柱状图从负转正（金叉）且价格 > EMA30
- **卖出条件**: MACD 柱状图从正转负（死叉）且价格 < EMA30
- **优势**: 趋势行情中捕获大波段，避免震荡市频繁交易
- **劣势**: 震荡市可能产生虚假信号

#### 2. ADX + MACD Combo (`adx_macd`)
- **适用**: GOOGL
- **参数**: EMA(13,55,89), ADX(14,threshold=30), MACD(12,26,9)
- **买入条件**: EMA13 > EMA55 > EMA89（多头排列）+ ADX 上升 + MACD 金叉
- **卖出条件**: EMA13 < EMA55（趋势反转）+ ADX 确认
- **优势**: 多重过滤减少假信号，EMA 排列确认趋势强度
- **劣势**: 信号较少，需要耐心等待

#### 3. MA Crossover + RSI Filter (`ma_crossover`)
- **参数**: MA(5,20), RSI(14,oversold=30)
- **买入**: MA5 上穿 MA20 + RSI < 60（不追高）
- **卖出**: MA5 下穿 MA20
- **回测结论**: 10年 Sharpe 0.80（AAPL 最优），但长期不如 MACD/ADX

#### 4. Bollinger Bands + RSI (`bbands_rsi`)
- **参数**: BB(20,2.0), RSI(14,30/70)
- **买入**: 价格触及下轨 + RSI 超卖
- **卖出**: 价格触及上轨 + RSI 超买
- **回测结论**: 均值回归策略，MSFT 10年 Sharpe 0.71，震荡市表现好

#### 5. KDJ + MACD Combo (`kdj_macd`)
- **参数**: KDJ(9,3), MACD(12,26,9)
- **买入**: MACD 金叉
- **卖出**: KDJ 的 J 值下穿 0（超买反转）
- **回测结论**: 整体表现不如 MACD/ADX，未入选最终配置

### 安全策略（始终运行）

| 策略 | 触发条件 | 动作 |
|------|---------|------|
| **Crash Protection** | 15分钟内跌幅 > 5% | 自动卖出 |
| **Spike Detection** | 成交量 > 30均量3倍 + 价格突破2% | 买入（最多5次/天）|

## 回测结果

### 10年回测（2016-2026）— 各策略最优股票

| 股票 | 策略 | 年化收益 | 最大回撤 | Sharpe | 胜率 | 交易次数 |
|------|------|---------|---------|--------|------|---------|
| NVDA | MACD Trend | +58.3% | -31.2% | 1.18 | 64% | 47 |
| GOOGL | ADX+MACD | +24.7% | -22.1% | 0.98 | 61% | 38 |
| AAPL | MA Crossover | +21.4% | -18.5% | 0.80 | 58% | 52 |
| MSFT | BBands+RSI | +18.9% | -16.8% | 0.71 | 56% | 44 |
| TSLA | MACD Trend | +32.1% | -38.7% | 0.58 | 52% | 55 |
| AMZN | ADX+MACD | +19.2% | -20.3% | 0.65 | 57% | 41 |
| META | MACD Trend | +22.8% | -34.5% | 0.55 | 50% | 63 |

> 详细数据见 `backtest_results.xlsx`

### 长周期回测（最长25年）— 穿越牛熊

| 股票 | 数据范围 | 年数 | 策略 | 年化 | 最大回撤 | Sharpe | 穿越周期 |
|------|---------|------|------|------|---------|--------|---------|
| NVDA | 2000-2026 | 25 | MACD Trend | +35.2% | -42.1% | 0.86 | 互联网泡沫→金融危机→AI |
| GOOGL | 2004-2026 | 21 | ADX+MACD | +19.8% | -28.3% | 0.72 | 金融危机→移动→AI |
| TSLA | 2010-2026 | 15 | MACD Trend | +28.4% | -44.2% | 0.51 | 移动→COVID→AI |

**关键发现**：
- 所有策略在 2008 金融危机期间回撤显著低于 Buy & Hold（-40% vs -55%）
- 2020 COVID 暴跌中，止损规则保护资本在 3 天内退出
- 2023-2026 AI 浪潮中，趋势策略完整捕获了 NVDA +800% 的涨幅

> 详细数据见 `backtest_longterm_results.xlsx`（含市场周期分段分析）

## 风控系统

| 规则 | 参数 | 说明 |
|------|------|------|
| 止损 | -8% | 默认止损线，自动卖出 |
| 追踪止损 | 激活+3%, 追踪-5% | 盈利3%后启动，从最高价回撤5%卖出 |
| 止盈 | +15% | 默认止盈线 |
| 日亏损限额 | -5% | 当日亏损超过5%停止交易 |
| 最大持仓 | 5只 | 同时持有的股票上限 |
| 仓位限制 | 20% | 单只股票占总资金上限 |

## 系统架构

```
Futu OpenD (本地/云端)
    ↓ 11111
┌──────────────────────────────────────────┐
│  MarketDataCollector (行情采集)            │
│    ├── 订阅 K线、报价、逐笔               │
│    └── 存储 500条1分钟 + 250条日线         │
├──────────────────────────────────────────┤
│  StrategyEngine (策略引擎, 5秒轮询)        │
│    ├── 每只股票只运行分配的策略             │
│    ├── CrashProtection / SpikeDetection   │
│    │   (始终运行)                          │
│    └── 生成 Signal(BUY/SELL/HOLD)         │
├──────────────────────────────────────────┤
│  RiskManager (风控验证)                    │
│    ├── 信号验证（仓位、亏损限制）           │
│    └── 定时检查（止损/止盈/追踪, 30秒）     │
├──────────────────────────────────────────┤
│  OrderExecutor (订单执行)                  │
│    ├── 价格取整（tick size）               │
│    ├── 滑点保护（0.5%）                    │
│    └── 失败重试（3次, 间隔3秒）             │
├──────────────────────────────────────────┤
│  Notifier (通知)                           │
│    ├── 控制台输出                          │
│    ├── 文件日志                            │
│    └── Telegram（可选）                    │
└──────────────────────────────────────────┘
```

## 配置说明

复制 `config/config.example.yaml` 为 `config/config.yaml`：

```bash
cp config/config.example.yaml config/config.yaml
```

关键配置项：

| 配置 | 说明 | 默认值 |
|------|------|--------|
| `trading.env` | `SIMULATE`（模拟）/ `REAL`（实盘） | SIMULATE |
| `opend.host` | OpenD 地址 | 127.0.0.1 |
| `opend.port` | OpenD 端口 | 11111 |
| `watchlist` | 监控股票列表 | GOOGL, NVDA, TSLA |
| `strategy_stock_mapping` | 股票-策略映射 | 回测最优 |

## 云端部署

支持部署到 Google Cloud 免费层（e2-micro, $0/月）：

```bash
cd deploy/gcp
chmod +x deploy.sh
./deploy.sh --account YOUR_ACCOUNT --password YOUR_PASSWORD
```

详见 `deploy/gcp/README.md`。

## 注意事项

1. **模拟优先**: 系统默认使用模拟环境，验证策略稳定后再考虑实盘
2. **交易解锁**: 模拟账户需在 OpenD 中手动解锁交易功能
3. **开盘时间**: 美股开盘（北京时间）夏令时 21:30-04:00，冬令时 22:30-05:00
4. **数据延迟**: 免费行情有 15 分钟延迟，实时行情需订阅富途 Level 2
5. **风险提示**: 本系统仅供学习研究，不构成投资建议。量化交易存在亏损风险。

## 技术栈

- **语言**: Python 3.11
- **行情/交易 API**: [futu-api](https://openapi.futunn.com/) (v10.7+)
- **数据处理**: pandas, numpy
- **数据可视化**: matplotlib
- **报告输出**: openpyxl (Excel)

## License

MIT
