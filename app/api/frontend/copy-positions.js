const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);
}

function shortAddress(value) {
  return value.length > 14 ? `${value.slice(0, 7)}…${value.slice(-5)}` : value;
}

function number(value, maximumFractionDigits = 6) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits }).format(value || 0);
}

function price(value) {
  if (!value) return "$0";
  const digits = value < 0.0001 ? 10 : value < 0.01 ? 7 : 4;
  return `$${number(value, digits)}`;
}

function dateTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("uk-UA", {
    timeZone: "Europe/Kyiv", day: "2-digit", month: "2-digit", year: "2-digit",
    hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}

function summaryCard(label, value, tone = "") {
  return `<article class="portfolio-card ${tone}"><span>${label}</span><strong>${value}</strong></article>`;
}

function render(data) {
  const pnlTone = data.total_pnl_usd >= 0 ? "positive" : "negative";
  document.querySelector("#portfolioSummary").innerHTML = [
    summaryCard("Відкрито", number(data.positions.length, 0)),
    summaryCard("Стартовий баланс", money.format(data.initial_balance_usd)),
    summaryCard("Готівка", money.format(data.cash_balance_usd)),
    summaryCard("Equity", money.format(data.total_equity_usd)),
    summaryCard("Загальний PnL", `${data.total_pnl_usd >= 0 ? "+" : ""}${money.format(data.total_pnl_usd)}`, pnlTone),
  ].join("");
  document.querySelector("#portfolioWallet").textContent = data.portfolio_wallet;
  document.querySelector("#portfolioStatus").textContent = data.enabled ? "Активний" : "Вимкнений";
  document.querySelector("#allocation").textContent = money.format(data.allocation_usd);
  document.querySelector("#positionLimit").textContent = data.max_open_positions;
  document.querySelector("#slippage").textContent = `${data.slippage_bps} bps`;
  document.querySelector("#startedAt").textContent = dateTime(data.started_at);
  document.querySelector("#updatedAt").textContent = `Оновлено ${dateTime(data.updated_at)}`;
  document.querySelector("#positionCount").textContent = `${data.positions.length} позицій`;

  const body = document.querySelector("#positionsBody");
  if (!data.positions.length) {
    body.innerHTML = '<tr><td colspan="11" class="empty">Зараз відкритих позицій немає.</td></tr>';
    return;
  }
  body.innerHTML = data.positions.map((item, index) => {
    const pnlClass = item.unrealized_pnl_usd >= 0 ? "positive" : "negative";
    const pnlSign = item.unrealized_pnl_usd >= 0 ? "+" : "";
    const symbol = escapeHtml(item.symbol || "UNKNOWN");
    return `<tr>
      <td class="rank">${String(index + 1).padStart(2, "0")}</td>
      <td class="asset-cell"><strong>${symbol}</strong><a href="https://solscan.io/token/${encodeURIComponent(item.token_address)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(item.token_address)}">${escapeHtml(shortAddress(item.token_address))}</a></td>
      <td><a class="wallet" href="https://solscan.io/account/${encodeURIComponent(item.source_wallet)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(item.source_wallet)}">${escapeHtml(shortAddress(item.source_wallet))}</a></td>
      <td class="numeric"><strong>${number(item.quantity)}</strong><small>джерело: ${number(item.source_quantity)}</small></td>
      <td class="numeric">${price(item.entry_price_usd)}</td>
      <td class="numeric">${price(item.last_price_usd)}</td>
      <td class="numeric">${money.format(item.cost_basis_usd)}</td>
      <td class="numeric"><strong>${money.format(item.estimated_exit_value_usd)}</strong><small>ринок: ${money.format(item.market_value_usd)}</small></td>
      <td class="numeric pnl ${pnlClass}"><strong>${pnlSign}${money.format(item.unrealized_pnl_usd)}</strong><small>${pnlSign}${number(item.unrealized_roi_pct, 2)}%</small></td>
      <td class="date-cell">${dateTime(item.opened_at)}</td>
      <td class="date-cell">${dateTime(item.updated_at)}</td>
    </tr>`;
  }).join("");
}

async function loadData() {
  const connection = document.querySelector("#connection");
  const error = document.querySelector("#error");
  try {
    const response = await fetch("/api/v1/copy-positions", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
    connection.textContent = "Онлайн";
    connection.classList.remove("offline");
    error.hidden = true;
  } catch (reason) {
    connection.textContent = "Немає зв'язку";
    connection.classList.add("offline");
    error.textContent = `Не вдалося завантажити позиції: ${reason.message}`;
    error.hidden = false;
  }
}

function scheduleHalfHourRefresh() {
  const now = new Date();
  const next = new Date(now);
  next.setSeconds(0, 0);
  next.setMinutes(now.getMinutes() < 30 ? 30 : 60);
  window.setTimeout(() => {
    loadData();
    scheduleHalfHourRefresh();
  }, Math.max(1000, next.getTime() - now.getTime()));
}

loadData();
scheduleHalfHourRefresh();
