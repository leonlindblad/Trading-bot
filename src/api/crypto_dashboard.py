"""Crypto-only web dashboard — dedicated single-page monitor for the crypto bot."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

CRYPTO_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Crypto Trading Bot</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0e17; color: #e1e4e8; min-height: 100vh; }

.header { background: linear-gradient(135deg, #0d1321 0%, #1a1e2e 100%); border-bottom: 1px solid #f7931a33; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
.header h1 { font-size: 20px; font-weight: 700; background: linear-gradient(90deg, #f7931a, #ffab40); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.header .mode-badge { padding: 4px 12px; border-radius: 12px; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
.header .mode-paper { background: #1a3a1a; color: #3fb950; border: 1px solid #3fb95055; }
.header .mode-live { background: #3a1a1a; color: #f85149; border: 1px solid #f8514955; }
.header .status { display: flex; align-items: center; gap: 10px; font-size: 14px; }
.header .dot { width: 8px; height: 8px; border-radius: 50%; background: #3fb950; animation: pulse 2s ease-in-out infinite; }
.header .dot.offline { background: #f85149; animation: none; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

.container { max-width: 1400px; margin: 0 auto; padding: 20px; }

/* Summary cards */
.summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 20px; }
.card { background: #111827; border: 1px solid #1e293b; border-radius: 10px; padding: 18px; transition: border-color 0.2s; }
.card:hover { border-color: #f7931a55; }
.card h3 { font-size: 11px; text-transform: uppercase; color: #64748b; margin-bottom: 6px; letter-spacing: 0.8px; }
.card .value { font-size: 26px; font-weight: 700; font-variant-numeric: tabular-nums; }
.card .sub { font-size: 12px; color: #64748b; margin-top: 4px; }
.positive { color: #3fb950; }
.negative { color: #f85149; }
.neutral { color: #e1e4e8; }

/* Coin ticker strip */
.ticker-strip { display: flex; gap: 12px; overflow-x: auto; padding: 0 0 14px 0; margin-bottom: 20px; scrollbar-width: thin; scrollbar-color: #1e293b transparent; }
.ticker-strip::-webkit-scrollbar { height: 4px; }
.ticker-strip::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 2px; }
.coin-card { flex: 0 0 170px; background: #111827; border: 1px solid #1e293b; border-radius: 10px; padding: 14px; cursor: default; transition: border-color 0.2s; }
.coin-card:hover { border-color: #f7931a55; }
.coin-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.coin-symbol { font-weight: 700; font-size: 14px; }
.coin-change { font-size: 11px; font-weight: 700; padding: 2px 6px; border-radius: 4px; }
.coin-change.up { background: #0d4429; color: #3fb950; }
.coin-change.down { background: #490b10; color: #f85149; }
.coin-name { font-size: 10px; color: #64748b; margin-bottom: 4px; }
.coin-price { font-size: 18px; font-weight: 600; font-variant-numeric: tabular-nums; }
.coin-meta { font-size: 10px; color: #475569; margin-top: 6px; display: flex; justify-content: space-between; }

/* Sections */
.section { background: #111827; border: 1px solid #1e293b; border-radius: 10px; margin-bottom: 20px; overflow: hidden; }
.section-header { padding: 14px 18px; border-bottom: 1px solid #1e293b; display: flex; justify-content: space-between; align-items: center; }
.section-header h2 { font-size: 14px; font-weight: 600; }

/* Strategies row */
.strat-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; padding: 14px 18px; }
.strat-card { background: #0a0e17; border: 1px solid #1e293b; border-radius: 8px; padding: 14px; }
.strat-card h4 { font-size: 13px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
.strat-card .stat { font-size: 12px; color: #64748b; margin-bottom: 2px; }

/* Tables */
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 10px 18px; color: #64748b; font-weight: 500; border-bottom: 1px solid #1e293b; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
td { padding: 10px 18px; border-bottom: 1px solid #0f172a; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #0f172a; }

/* Badges */
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }
.badge-buy { background: #0d4429; color: #3fb950; }
.badge-sell { background: #490b10; color: #f85149; }
.badge-on { background: #0d4429; color: #3fb950; }
.badge-off { background: #1e293b; color: #64748b; }

/* Buttons */
.btn { padding: 6px 14px; border-radius: 6px; border: 1px solid #1e293b; background: #1e293b; color: #e1e4e8; cursor: pointer; font-size: 12px; transition: background 0.15s; }
.btn:hover { background: #334155; }
.btn-danger { border-color: #f85149; color: #f85149; background: transparent; }
.btn-danger:hover { background: #490b10; }
.btn-sm { padding: 4px 10px; font-size: 11px; }

/* Logs */
.logs { max-height: 280px; overflow-y: auto; padding: 12px 18px; font-family: 'SF Mono', 'Fira Code', Monaco, monospace; font-size: 12px; line-height: 1.7; background: #0a0e17; }
.log-line { white-space: pre-wrap; word-break: break-all; }
.log-time { color: #f7931a; }
.log-level-info { color: #58a6ff; }
.log-level-warn { color: #d29922; }
.log-level-error { color: #f85149; }

.refresh-info { font-size: 11px; color: #334155; }

/* Two-column layout for positions + trades */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
@media (max-width: 900px) { .two-col { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="header">
  <div style="display:flex;align-items:center;gap:12px;">
    <h1>Crypto Bot</h1>
    <span class="mode-badge mode-paper" id="mode-badge">PAPER</span>
  </div>
  <div class="status">
    <span class="refresh-info">Auto-refresh 5s</span>
    <div class="dot" id="status-dot"></div>
    <span id="status-text">Connecting...</span>
    <button class="btn btn-danger" onclick="emergencyStop()">Emergency Stop</button>
  </div>
</div>

<div class="container">
  <!-- Summary cards -->
  <div class="summary" id="summary-cards"></div>

  <!-- Live coin ticker -->
  <div class="ticker-strip" id="coin-ticker">
    <div style="color:#64748b;padding:20px;">Loading crypto prices...</div>
  </div>

  <!-- Strategies -->
  <div class="section">
    <div class="section-header">
      <h2>Strategies</h2>
    </div>
    <div class="strat-row" id="strategies-grid"></div>
  </div>

  <!-- Positions + Trades side by side -->
  <div class="two-col">
    <div class="section">
      <div class="section-header">
        <h2>Open Positions</h2>
        <span class="refresh-info" id="pos-count"></span>
      </div>
      <div style="overflow-x:auto;">
        <table>
          <thead><tr><th>Pair</th><th>Qty</th><th>Avg Cost</th><th>Price</th><th>P&L</th><th>Strategy</th></tr></thead>
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
          <thead><tr><th>Time</th><th>Side</th><th>Pair</th><th>Qty</th><th>Price</th><th>Fees</th></tr></thead>
          <tbody id="trades-body"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Logs -->
  <div class="section">
    <div class="section-header">
      <h2>Live Logs</h2>
      <button class="btn btn-sm" onclick="clearLogs()">Clear</button>
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

function pctFmt(val) {
  const n = parseFloat(val);
  const sign = n >= 0 ? '+' : '';
  return sign + n.toFixed(2) + '%';
}

function formatMarketCap(val) {
  if (!val) return '-';
  if (val >= 1e12) return '$' + (val / 1e12).toFixed(2) + 'T';
  if (val >= 1e9) return '$' + (val / 1e9).toFixed(1) + 'B';
  if (val >= 1e6) return '$' + (val / 1e6).toFixed(0) + 'M';
  return '$' + val.toLocaleString();
}

function formatVolume(val) {
  if (!val) return '-';
  if (val >= 1e9) return '$' + (val / 1e9).toFixed(1) + 'B';
  if (val >= 1e6) return '$' + (val / 1e6).toFixed(0) + 'M';
  return '$' + val.toLocaleString();
}

function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

async function fetchJSON(path) {
  const res = await fetch(API + path);
  return res.json();
}

async function updateSummary() {
  try {
    const data = await fetchJSON('/portfolio');
    if (data.error) return;
    const pnlPct = ((parseFloat(data.total_pnl) / 10000) * 100).toFixed(2);
    document.getElementById('summary-cards').innerHTML = `
      <div class="card">
        <h3>Portfolio Value</h3>
        <div class="value">$${fmt(data.total_equity)}</div>
        <div class="sub">${data.open_positions} open positions</div>
      </div>
      <div class="card">
        <h3>Available Cash</h3>
        <div class="value">$${fmt(data.cash_balance)}</div>
        <div class="sub">In positions: $${fmt(data.positions_value)}</div>
      </div>
      <div class="card">
        <h3>Daily P&L</h3>
        <div class="value ${pnlClass(data.daily_pnl)}">${pnlFmt(data.daily_pnl)}</div>
        <div class="sub">Today</div>
      </div>
      <div class="card">
        <h3>Total P&L</h3>
        <div class="value ${pnlClass(data.total_pnl)}">${pnlFmt(data.total_pnl)}</div>
        <div class="sub ${pnlClass(data.total_pnl)}">${pnlPct}% all time</div>
      </div>
      <div class="card">
        <h3>Weekly P&L</h3>
        <div class="value ${pnlClass(data.weekly_pnl)}">${pnlFmt(data.weekly_pnl)}</div>
        <div class="sub">This week</div>
      </div>
    `;
  } catch(e) { console.error('Summary fetch failed', e); }
}

async function updateCoinTicker() {
  try {
    const data = await fetchJSON('/market-feed');
    const coins = data.crypto || [];
    if (coins.length === 0) return;
    const strip = document.getElementById('coin-ticker');
    strip.innerHTML = coins.map(c => {
      const change = c.change_24h || 0;
      const changeClass = change >= 0 ? 'up' : 'down';
      const changeSign = change >= 0 ? '+' : '';
      const price = c.price || 0;
      const priceStr = price >= 1000 ? '$' + price.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})
        : price >= 1 ? '$' + price.toFixed(2)
        : '$' + price.toFixed(4);
      return `
        <div class="coin-card">
          <div class="coin-header">
            <span class="coin-symbol">${escapeHtml(c.symbol)}</span>
            <span class="coin-change ${changeClass}">${changeSign}${change.toFixed(2)}%</span>
          </div>
          <div class="coin-name">${escapeHtml(c.name || '')}</div>
          <div class="coin-price">${priceStr}</div>
          <div class="coin-meta">
            <span>MCap ${formatMarketCap(c.market_cap)}</span>
            <span>Vol ${formatVolume(c.volume_24h)}</span>
          </div>
        </div>
      `;
    }).join('');
  } catch(e) { console.error('Coin ticker failed', e); }
}

async function updatePositions() {
  try {
    const data = await fetchJSON('/positions');
    if (data.error) return;
    document.getElementById('pos-count').textContent = data.length + ' positions';
    const tbody = document.getElementById('positions-body');
    if (data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#64748b;padding:20px;">No open positions</td></tr>';
      return;
    }
    tbody.innerHTML = data.map(p => `
      <tr>
        <td><strong>${escapeHtml(p.symbol)}</strong></td>
        <td>${fmt(p.quantity, 6)}</td>
        <td>$${fmt(p.avg_cost)}</td>
        <td>$${fmt(p.current_price)}</td>
        <td class="${pnlClass(p.unrealised_pnl)}">${pnlFmt(p.unrealised_pnl)}</td>
        <td>${escapeHtml(p.strategy)}</td>
      </tr>
    `).join('');
  } catch(e) { console.error('Positions fetch failed', e); }
}

async function updateTrades() {
  try {
    const data = await fetchJSON('/trades?limit=30');
    if (data.error) return;
    document.getElementById('trade-count').textContent = data.length + ' trades';
    const tbody = document.getElementById('trades-body');
    if (data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#64748b;padding:20px;">No trades yet</td></tr>';
      return;
    }
    tbody.innerHTML = data.slice().reverse().map(t => `
      <tr>
        <td>${t.timestamp ? t.timestamp.split('T')[1]?.substring(0,8) || t.timestamp : '-'}</td>
        <td><span class="badge ${t.side === 'BUY' ? 'badge-buy' : 'badge-sell'}">${t.side}</span></td>
        <td><strong>${escapeHtml(t.symbol)}</strong></td>
        <td>${fmt(t.quantity, 6)}</td>
        <td>$${fmt(t.price)}</td>
        <td>$${fmt(t.fees, 4)}</td>
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
        <h4>${escapeHtml(name)} <span class="badge ${info.enabled ? 'badge-on' : 'badge-off'}">${info.enabled ? 'ON' : 'OFF'}</span></h4>
        <div class="stat">Signals: ${info.signal_count || 0}</div>
        <div class="stat">Evals: ${info.eval_count || 0}</div>
        <button class="btn btn-sm" onclick="toggleStrategy('${name}')" style="margin-top:8px;width:100%;">
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
    const data = await fetchJSON('/logs?limit=80');
    if (!data.lines) return;
    logLines = data.lines;
    renderLogs();
  } catch(e) {}
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

function clearLogs() {
  logLines = [];
  document.getElementById('logs-container').innerHTML = '';
}

async function toggleStrategy(name) {
  await fetch(API + '/strategies/' + name + '/toggle', {method: 'POST'});
  updateStrategies();
}

async function emergencyStop() {
  if (confirm('HALT ALL CRYPTO TRADING? This will stop the bot from placing new trades.')) {
    await fetch(API + '/emergency-stop', {method: 'POST'});
    updateHealth();
  }
}

async function refresh() {
  await Promise.all([updateHealth(), updateSummary(), updatePositions(), updateTrades(), updateStrategies(), updateLogs()]);
}

refresh();
updateCoinTicker();
setInterval(refresh, 5000);
setInterval(updateCoinTicker, 30000);
</script>
</body>
</html>"""


def create_crypto_dashboard_router(dashboard_password: str) -> APIRouter:
    """Create crypto dashboard router with optional basic auth."""
    router = APIRouter()

    def _check_auth(credentials: HTTPBasicCredentials = Depends(security)):
        if not dashboard_password:
            return
        correct = secrets.compare_digest(credentials.password, dashboard_password)
        if not correct:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password",
                headers={"WWW-Authenticate": "Basic"},
            )

    if dashboard_password:
        @router.get("/", response_class=HTMLResponse)
        async def crypto_dashboard(credentials: HTTPBasicCredentials = Depends(_check_auth)):
            return CRYPTO_DASHBOARD_HTML
    else:
        @router.get("/", response_class=HTMLResponse)
        async def crypto_dashboard():
            return CRYPTO_DASHBOARD_HTML

    return router
