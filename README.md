# 美股回调指数 — Auto

手机优先的 GitHub Pages 仪表盘，用于监控“未来数周 5–10% 美股回调风险是否上升”。

## 自动更新

`.github/workflows/update-data.yml` 每小时运行一次：

1. 抓取股票 / ETF 行情
2. 抓取 FRED 宏观数据
3. 计算各信号 0–10 分
4. 写入 `data/latest.json`
5. 追加 `data/history.json`
6. 自动 commit 回仓库

网页每 5 分钟重新读取 `latest.json`。

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

这不是“必跌”判断，而是表示多个独立风险信号已经高度对齐。
