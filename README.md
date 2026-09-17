# 美股回调指数 — Auto

手机优先的 GitHub Pages 实验性风险仪表盘。指数尚未通过预测能力验证，不应单独用于交易决策。

## 自动更新

`.github/workflows/update-data.yml` 每小时运行一次：

1. 抓取股票 / ETF 行情
2. 抓取 FRED 宏观数据
3. 计算各信号 0–10 分
4. 写入 `data/latest.json`
5. 追加 `data/history.json`
6. 自动 commit 回仓库

网页每 5 分钟重新读取 `latest.json`。

## 历史回测

`.github/workflows/update-backtest.yml` 每天重算 `data/backtest.json`。脚本从 Nasdaq 获取 SPY、QQQ、HOOD、ARKK、SMH、XBI、IWM、RSP 的历史日收盘价，从 FRED 获取全部宏观因子的历史观测值，沿用 `scripts/update_data.py` 的 11 因子评分规则逐日重建指数（不使用当前手动覆盖）。网页将指数与首日归一化为 100 的 SPY 并列显示。

为避免明显的未来数据泄漏，日度 FRED 因子假设滞后 1 天、油价滞后 3 天、核心 CPI 滞后 45 天后才可使用。真实历史发布时间并未逐项重建，FRED 历史值也可能已经修订，所以这仍是回溯近似，不是严格的 point-in-time 回测。

预测检验分别查看指数与未来 5、10、20 个交易日收益率及最大收盘跌幅的相关性，以及识别未来 ≥5% 跌幅的 AUC、≥7 分后的事件比例。未来窗口重叠，样本并非独立；模型权重和阈值是在样本期后制定，也不能把回测当作样本外验证。详情和每日因子分数见 `data/backtest.json`。

## 数据源

### 股票 / ETF
优先使用 Alpaca Market Data。

在 GitHub 仓库中添加两个 Actions secrets：

- `ALPACA_API_KEY`
- `ALPACA_API_SECRET`

如果没有配置，会尝试 Yahoo chart 后备源。这个后备源不保证稳定，建议正式使用时配置 Alpaca。

自动监控：
- SPY
- QQQ
- HOOD
- ARKK
- SMH
- XBI
- IWM
- RSP

### 宏观
使用 FRED 公共 CSV：
- DGS10 — US 10Y
- DGS2 — US 2Y
- VIXCLS — VIX close
- DCOILBRENTEU — Brent spot
- DCOILWTICO — WTI spot
- DFEDTARU — Fed target upper bound
- CPILFESL — Core CPI

注意：GitHub Action 是每小时重算，但 FRED 中的收益率、油价、VIX、CPI 本身可能是日频/月频，并不代表每小时都会改变。

## 模型

当前权重：
- HOOD reversal 14%
- HOOD/QQQ divergence 14%
- ARKK / high-beta 10%
- breadth proxy 10%
- VIX complacency 8%
- Oil 9%
- US 10Y 11%
- US 2Y 6%
- Fed path pressure 8%
- Inflation pressure 5%
- Broad risk-off 5%

`Breadth` 自动版使用：
- RSP vs SPY
- IWM vs QQQ

`Fed` 自动版使用 US 2Y yield - Fed target upper bound；`CPI` 自动版使用 Core CPI YoY。它们属于代理指标，不假装成实时 FedWatch 或 CPI surprise。

## 手动覆盖

编辑 `data/manual_overrides.json`：

```json
{
  "signals": {
    "fed": 9.5,
    "cpi": 8.8
  }
}
```

## GitHub Pages

Settings → Pages → Source 选择 **GitHub Actions**，然后 `deploy-pages.yml` 会部署站点。

## 红色预警

指数 `>= 9.3` 时页面自动显示 **极高风险 · 红色预警**。

这不是“必跌”判断。历史样本中红色阈值尚未触发，不能据此声称它能预测回调。
