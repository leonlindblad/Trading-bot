"""Web dashboard — single-page trading bot monitor with basic auth."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

if TYPE_CHECKING:
    pass

security = HTTPBasic()

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trading Bot Dashboard</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f1117; color: #e1e4e8; min-height: 100vh; }
.header { background: #161b22; border-bottom: 1px solid #30363d; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
.header h1 { font-size: 18px; font-weight: 600; }
.header .status { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.header .dot { width: 8px; height: 8px; border-radius: 50%; background: #3fb950; }
.header .dot.offline { background: #f85149; }
.container { max-width: 1200px; margin: 0 auto; padding: 24px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 24px; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }
.card h3 { font-size: 12px; text-transform: uppercase; color: #8b949e; margin-bottom: 8px; letter-spacing: 0.5px; }
.card .value { font-size: 28px; font-weight: 700; }
.card .sub { font-size: 13px; color: #8b949e; margin-top: 4px; }
.positive { color: #3fb950; }
.negative { color: #f85149; }
.neutral { color: #e1e4e8; }
.section { background: #161b22; border: 1px solid #30363d; border-radius: 8px; margin-bottom: 24px; overflow: hidden; }
.section-header { padding: 16px 20px; border-bottom: 1px solid #30363d; display: flex; justify-content: space-between; align-items: center; }
.section-header h2 { font-size: 14px; font-weight: 600; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 10px 20px; color: #8b949e; font-weight: 500; border-bottom: 1px solid #30363d; font-size: 12px; text-transform: uppercase; }
td { padding: 10px 20px; border-bottom: 1px solid #21262d; }
tr:last-child td { border-bottom: none; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }
.badge-buy { background: #0d4429; color: #3fb950; }
.badge-sell { background: #490b10; color: #f85149; }
.badge-on { background: #0d4429; color: #3fb950; }
.badge-off { background: #343941; color: #8b949e; }
.logs { max-height: 300px; overflow-y: auto; padding: 12px 20px; font-family: 'SF Mono', Monaco, monospace; font-size: 12px; line-height: 1.6; background: #0d1117; }
.log-line { white-space: pre-wrap; word-break: break-all; }
.log-time { color: #3fb950; }
.log-level-info { color: #58a6ff; }
.log-level-warn { color: #d29922; }
.log-level-error { color: #f85149; }
.btn { padding: 6px 14px; border-radius: 6px; border: 1px solid #30363d; background: #21262d; color: #e1e4e8; cursor: pointer; font-size: 12px; }
.btn:hover { background: #30363d; }
.btn-danger { border-color: #f85149; color: #f85149; }
.btn-danger:hover { background: #490b10; }
.refresh-info { font-size: 11px; color: #484f58; }
.strategies-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; padding: 16px 20px; }
.strat-card { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 12px; }
.strat-card h4 { font-size: 13px; margin-bottom: 6px; display: flex; justify-content: space-between; }
.strat-card .stat { font-size: 12px; color: #8b949e; }
.tab-bar { display: flex; gap: 0; border-bottom: 1px solid #30363d; background: #161b22; }
.tab-btn { padding: 10px 20px; background: none; border: none; border-bottom: 2px solid transparent; color: #8b949e; cursor: pointer; font-size: 13px; font-weight: 500; }
.tab-btn:hover { color: #e1e4e8; }
.tab-btn.active { color: #58a6ff; border-bottom-color: #58a6ff; }
.market-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; padding: 16px 20px; }
.market-item { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 12px; display: flex; flex-direction: column; gap: 4px; }
.market-item .mi-header { display: flex; justify-content: space-between; align-items: center; }
.market-item .mi-symbol { font-weight: 700; font-size: 14px; }
.market-item .mi-name { font-size: 11px; color: #8b949e; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.market-item .mi-price { font-size: 18px; font-weight: 600; margin: 4px 0; }
.market-item .mi-change { font-size: 12px; font-weight: 600; padding: 2px 6px; border-radius: 4px; display: inline-block; }
.market-item .mi-change.up { background: #0d4429; color: #3fb950; }
.market-item .mi-change.down { background: #490b10; color: #f85149; }
.market-item .mi-details { font-size: 11px; color: #8b949e; display: flex; justify-content: space-between; margin-top: 4px; }
.market-loading { text-align: center; padding: 40px; color: #8b949e; }
.tab-content { display: none; }
.tab-content.active { display: block; }
</style>
</head>
<body>
<div class="header">
  <h1>Trading Bot</h1>
  <div class="status">
    <span class="refresh-info">Updates every 5s</span>
    <div class="dot" id="status-dot"></div>
    <span id="status-text">Connecting...</span>
    <button class="btn btn-danger" onclick="emergencyStop()">Emergency Stop</button>
  </div>
</div>
<div class="container">
  <div class="grid" id="summary-cards"></div>

  <div class="section">
    <div class="section-header">
      <h2>Live Market Feed</h2>
      <span class="refresh-info" id="market-feed-time"></span>
    </div>
    <div class="tab-bar">
      <button class="tab-btn active" onclick="switchTab('crypto')">Crypto</button>
      <button class="tab-btn" onclick="switchTab('us_stocks')">US Stocks</button>
      <button class="tab-btn" onclick="switchTab('uk_stocks')">UK Stocks</button>
    </div>
    <div class="tab-content active" id="tab-crypto">
      <div class="market-grid" id="market-crypto"><div class="market-loading">Loading crypto prices...</div></div>
    </div>
    <div class="tab-content" id="tab-us_stocks">
      <div class="market-grid" id="market-us_stocks"><div class="market-loading">Loading US stocks...</div></div>
    </div>
    <div class="tab-content" id="tab-uk_stocks">
      <div class="market-grid" id="market-uk_stocks"><div class="market-loading">Loading UK stocks...</div></div>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <h2>Strategies</h2>
    </div>
    <div class="strategies-grid" id="strategies-grid"></div>
  </div>

  <div class="section">
    <div class="section-header">
      <h2>Open Positions</h2>
      <span class="refresh-info" id="pos-count"></span>
    </div>
    <div style="overflow-x:auto;">
      <table>
        <thead><tr><th>Symbol</th><th>Market</th><th>Qty</th><th>Avg Cost</th><th>Price</th><th>P&L</th><th>Strategy</th></tr></thead>
        <tbody id="positions-body"></tbody>
      </table>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <h2>Recent Trades</h2>
      <span class="refresh-info" id="trade-count"></span>
    </div>
    <div style="overflow-x:auto;">
      <table>
        <thead><tr><th>Time</th><th>Side</th><th>Symbol</th><th>Qty</th><th>Price</th><th>Fees</th><th>Strategy</th></tr></thead>
        <tbody id="trades-body"></tbody>
      </table>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <h2>Live Logs</h2>
      <button class="btn" onclick="clearLogs()">Clear</button>
    </div>
    <div class="logs" id="logs-container"></div>
  </div>
</div>

<script>
const API = '/api';
let logLines = [];

function pnlClass(val) {
  const n = parseFloat(val);
  if (n > 0) return 'positive';
  if (n < 0) return 'negative';
  return 'neutral';
}

function fmt(val, decimals=2) {
  const n = parseFloat(val);
  if (isNaN(n)) return val;
  return n.toLocaleString('en-US', {minimumFractionDigits: decimals, maximumFractionDigits: decimals});
}

function pnlFmt(val) {
  const n = parseFloat(val);
  const sign = n >= 0 ? '+' : '';
  return sign + fmt(val);
}

async function fetchJSON(path) {
  const res = await fetch(API + path);
  return res.json();
}

async function updateSummary() {
  try {
    const data = await fetchJSON('/portfolio');
    if (data.error) return;
    document.getElementById('summary-cards').innerHTML = `
      <div class="card">
        <h3>Total Equity</h3>
        <div class="value">$${fmt(data.total_equity)}</div>
        <div class="sub">${data.open_positions} open positions</div>
      </div>
      <div class="card">
        <h3>Cash Balance</h3>
        <div class="value">$${fmt(data.cash_balance)}</div>
        <div class="sub">Positions: $${fmt(data.positions_value)}</div>
      </div>
      <div class="card">
        <h3>Daily P&L</h3>
        <div class="value ${pnlClass(data.daily_pnl)}">${pnlFmt(data.daily_pnl)}</div>
        <div class="sub">Today</div>
      </div>
      <div class="card">
        <h3>Total P&L</h3>
        <div class="value ${pnlClass(data.total_pnl)}">${pnlFmt(data.total_pnl)}</div>
        <div class="sub">Weekly: ${pnlFmt(data.weekly_pnl)}</div>
      </div>
    `;
  } catch(e) { console.error('Summary fetch failed', e); }
}

async function updatePositions() {
  try {
    const data = await fetchJSON('/positions');
    if (data.error) return;
    document.getElementById('pos-count').textContent = data.length + ' positions';
    const tbody = document.getElementById('positions-body');
    if (data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#8b949e;padding:20px;">No open positions</td></tr>';
      return;
    }
    tbody.innerHTML = data.map(p => `
      <tr>
        <td><strong>${p.symbol}</strong></td>
        <td>${p.market}</td>
        <td>${fmt(p.quantity, 6)}</td>
        <td>$${fmt(p.avg_cost)}</td>
        <td>$${fmt(p.current_price)}</td>
        <td class="${pnlClass(p.unrealised_pnl)}">${pnlFmt(p.unrealised_pnl)}</td>
        <td>${p.strategy}</td>
      </tr>
    `).join('');
  } catch(e) { console.error('Positions fetch failed', e); }
}

async function updateTrades() {
  try {
    const data = await fetchJSON('/trades?limit=50');
    if (data.error) return;
    document.getElementById('trade-count').textContent = data.length + ' trades';
    const tbody = document.getElementById('trades-body');
    if (data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#8b949e;padding:20px;">No trades yet</td></tr>';
      return;
    }
    tbody.innerHTML = data.slice().reverse().map(t => `
      <tr>
        <td>${t.timestamp || '-'}</td>
        <td><span class="badge ${t.side === 'BUY' ? 'badge-buy' : 'badge-sell'}">${t.side}</span></td>
        <td><strong>${t.symbol}</strong></td>
        <td>${fmt(t.quantity, 6)}</td>
        <td>$${fmt(t.price)}</td>
        <td>$${fmt(t.fees, 4)}</td>
        <td>${t.strategy || '-'}</td>
      </tr>
    `).join('');
  } catch(e) { console.error('Trades fetch failed', e); }
}

async function updateStrategies() {
  try {
    const data = await fetchJSON('/strategies');
    if (data.error) return;
    const grid = document.getElementById('strategies-grid');
    const strats = data.strategies || {};
    grid.innerHTML = Object.entries(strats).map(([name, info]) => `
      <div class="strat-card">
        <h4>${name} <span class="badge ${info.enabled ? 'badge-on' : 'badge-off'}">${info.enabled ? 'ON' : 'OFF'}</span></h4>
        <div class="stat">Signals: ${info.signal_count || 0}</div>
        <div class="stat">Evaluations: ${info.eval_count || 0}</div>
        <button class="btn" onclick="toggleStrategy('${name}')" style="margin-top:8px;width:100%;">
          ${info.enabled ? 'Disable' : 'Enable'}
        </button>
      </div>
    `).join('');
  } catch(e) { console.error('Strategies fetch failed', e); }
}

async function updateHealth() {
  try {
    const data = await fetchJSON('/health');
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    if (data.status === 'healthy') {
      dot.className = 'dot';
      text.textContent = 'Running';
    } else {
      dot.className = 'dot offline';
      text.textContent = 'Stopped';
    }
  } catch(e) {
    document.getElementById('status-dot').className = 'dot offline';
    document.getElementById('status-text').textContent = 'Offline';
  }
}

async function updateLogs() {
  try {
    const data = await fetchJSON('/logs?limit=100');
    if (!data.lines) return;
    logLines = data.lines;
    renderLogs();
  } catch(e) { /* logs endpoint may not exist yet */ }
}

function renderLogs() {
  const container = document.getElementById('logs-container');
  container.innerHTML = logLines.map(line => {
    let levelClass = '';
    if (line.includes('INFO')) levelClass = 'log-level-info';
    else if (line.includes('WARNING')) levelClass = 'log-level-warn';
    else if (line.includes('ERROR')) levelClass = 'log-level-error';
    const timeMatch = line.match(/^(\\d{2}:\\d{2}:\\d{2})/);
    if (timeMatch) {
      const rest = line.substring(timeMatch[0].length);
      return `<div class="log-line"><span class="log-time">${timeMatch[0]}</span><span class="${levelClass}">${escapeHtml(rest)}</span></div>`;
    }
    return `<div class="log-line ${levelClass}">${escapeHtml(line)}</div>`;
  }).join('');
  container.scrollTop = container.scrollHeight;
}

function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

function clearLogs() {
  logLines = [];
  document.getElementById('logs-container').innerHTML = '';
}

function switchTab(tabName) {
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('tab-' + tabName).classList.add('active');
}

function formatMarketCap(val) {
  if (!val) return '-';
  if (val >= 1e12) return '$' + (val / 1e12).toFixed(2) + 'T';
  if (val >= 1e9) return '$' + (val / 1e9).toFixed(2) + 'B';
  if (val >= 1e6) return '$' + (val / 1e6).toFixed(1) + 'M';
  return '$' + val.toLocaleString();
}

function formatVolume(val) {
  if (!val) return '-';
  if (val >= 1e9) return (val / 1e9).toFixed(2) + 'B';
  if (val >= 1e6) return (val / 1e6).toFixed(1) + 'M';
  if (val >= 1e3) return (val / 1e3).toFixed(1) + 'K';
  return val.toLocaleString();
}

function renderMarketItems(items, containerId, currencySymbol) {
  const container = document.getElementById(containerId);
  if (!items || items.length === 0) {
    container.innerHTML = '<div class="market-loading">No data available</div>';
    return;
  }
  container.innerHTML = items.map(item => {
    const price = item.price != null ? item.price : 0;
    const change = item.change_24h != null ? item.change_24h : 0;
    const changeClass = change >= 0 ? 'up' : 'down';
    const changeSign = change >= 0 ? '+' : '';
    const priceStr = price >= 1000 ? currencySymbol + price.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})
      : price >= 1 ? currencySymbol + price.toFixed(2)
      : currencySymbol + price.toFixed(4);
    return `
      <div class="market-item">
        <div class="mi-header">
          <span class="mi-symbol">${escapeHtml(item.symbol)}</span>
          <span class="mi-change ${changeClass}">${changeSign}${change.toFixed(2)}%</span>
        </div>
        <div class="mi-name">${escapeHtml(item.name || '')}</div>
        <div class="mi-price">${priceStr}</div>
        <div class="mi-details">
          <span>MCap: ${formatMarketCap(item.market_cap)}</span>
          <span>Vol: ${formatVolume(item.volume_24h)}</span>
        </div>
      </div>
    `;
  }).join('');
}

async function updateMarketFeed() {
  try {
    const data = await fetchJSON('/market-feed');
    if (data.crypto) renderMarketItems(data.crypto, 'market-crypto', '$');
    if (data.us_stocks) renderMarketItems(data.us_stocks, 'market-us_stocks', '$');
    if (data.uk_stocks) renderMarketItems(data.uk_stocks, 'market-uk_stocks', '');
    const timeEl = document.getElementById('market-feed-time');
    if (data.timestamp) {
      const d = new Date(data.timestamp * 1000);
      timeEl.textContent = 'Updated: ' + d.toLocaleTimeString();
    }
  } catch(e) { console.error('Market feed fetch failed', e); }
}

async function toggleStrategy(name) {
  await fetch(API + '/strategies/' + name + '/toggle', {method: 'POST'});
  updateStrategies();
}

async function emergencyStop() {
  if (confirm('HALT ALL TRADING? This will stop the bot from placing new trades.')) {
    await fetch(API + '/emergency-stop', {method: 'POST'});
    updateHealth();
  }
}

async function refresh() {
  await Promise.all([updateHealth(), updateSummary(), updatePositions(), updateTrades(), updateStrategies(), updateLogs()]);
}

refresh();
updateMarketFeed();
setInterval(refresh, 5000);
setInterval(updateMarketFeed, 30000);
</script>
</body>
</html>"""


def create_dashboard_router(dashboard_password: str) -> APIRouter:
    """Create dashboard router with optional basic auth."""
    router = APIRouter()

    def _check_auth(credentials: HTTPBasicCredentials = Depends(security)):
        if not dashboard_password:
            return  # No password set, allow access
        correct = secrets.compare_digest(credentials.password, dashboard_password)
        if not correct:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password",
                headers={"WWW-Authenticate": "Basic"},
            )

    if dashboard_password:
        @router.get("/", response_class=HTMLResponse)
        async def dashboard(credentials: HTTPBasicCredentials = Depends(_check_auth)):
            return DASHBOARD_HTML
    else:
        @router.get("/", response_class=HTMLResponse)
        async def dashboard():
            return DASHBOARD_HTML

    return router
