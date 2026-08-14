const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const positionState = {
  data: null,
  openSort: { key: null, direction: null },
  closedSort: { key: null, direction: null },
  traderSort: { key: null, direction: null },
};

function sortedOpenPositions(items) {
  const { key, direction } = positionState.openSort;
  if (!key || !direction) return [...items];
  return [...items].sort((left, right) => {
    const difference = Number(left[key] || 0) - Number(right[key] || 0);
    if (difference) return direction === "desc" ? -difference : difference;
    return new Date(right.opened_at) - new Date(left.opened_at);
  });
}

function updateOpenSortIndicators() {
  document.querySelectorAll("[data-open-sort]").forEach((button) => {
    const active = button.dataset.openSort === positionState.openSort.key;
    const direction = active ? positionState.openSort.direction : null;
    button.querySelector(".sort-indicator").textContent = direction === "desc" ? " ↓" : direction === "asc" ? " ↑" : " ↕";
    button.setAttribute("aria-sort", direction === "desc" ? "descending" : direction === "asc" ? "ascending" : "none");
  });
}

function sortedClosedPositions(items) {
  const { key, direction } = positionState.closedSort;
  if (!key || !direction) return [...items];
  return [...items].sort((left, right) => {
    const difference = Number(left[key] || 0) - Number(right[key] || 0);
    if (difference) return direction === "desc" ? -difference : difference;
    return new Date(right.closed_at) - new Date(left.closed_at);
  });
}

function updateClosedSortIndicators() {
  document.querySelectorAll("[data-closed-sort]").forEach((button) => {
    const active = button.dataset.closedSort === positionState.closedSort.key;
    const direction = active ? positionState.closedSort.direction : null;
    button.querySelector(".sort-indicator").textContent = direction === "desc" ? " ↓" : direction === "asc" ? " ↑" : " ↕";
    button.setAttribute("aria-sort", direction === "desc" ? "descending" : direction === "asc" ? "ascending" : "none");
  });
}

function sortedTraderStats(items) {
  const { key, direction } = positionState.traderSort;
  if (!key || !direction) return [...items];
  return [...items].sort((left, right) => {
    const difference = Number(left[key] || 0) - Number(right[key] || 0);
    if (difference) return direction === "desc" ? -difference : difference;
    return String(left.source_wallet).localeCompare(String(right.source_wallet));
  });
}

function updateTraderSortIndicators() {
  document.querySelectorAll("[data-trader-sort]").forEach((button) => {
    const active = button.dataset.traderSort === positionState.traderSort.key;
    const direction = active ? positionState.traderSort.direction : null;
    button.querySelector(".sort-indicator").textContent = direction === "desc" ? " ↓" : direction === "asc" ? " ↑" : " ↕";
    button.setAttribute("aria-sort", direction === "desc" ? "descending" : direction === "asc" ? "ascending" : "none");
  });
}

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
  positionState.data = data;
  const pnlTone = data.total_pnl_usd >= 0 ? "positive" : "negative";
  const realizedTone = data.realized_pnl_usd >= 0 ? "positive" : "negative";
  const openTone = data.open_pnl_usd >= 0 ? "positive" : "negative";
  document.querySelector("#portfolioSummary").innerHTML = [
    summaryCard("Відкрито", number(data.positions.length, 0)),
    summaryCard("Стартовий баланс", money.format(data.initial_balance_usd)),
    summaryCard("Готівка", money.format(data.cash_balance_usd)),
    summaryCard("Equity", money.format(data.total_equity_usd)),
    summaryCard("Реалізований PnL", `${data.realized_pnl_usd >= 0 ? "+" : ""}${money.format(data.realized_pnl_usd)}`, realizedTone),
    summaryCard("PnL відкритих", `${data.open_pnl_usd >= 0 ? "+" : ""}${money.format(data.open_pnl_usd)}`, openTone),
    summaryCard("Загальний PnL", `${data.total_pnl_usd >= 0 ? "+" : ""}${money.format(data.total_pnl_usd)}`, pnlTone),
  ].join("");
  document.querySelector("#portfolioWallet").textContent = data.portfolio_wallet;
  document.querySelector("#portfolioStatus").textContent = data.enabled ? "Активний" : "Вимкнений";
  document.querySelector("#allocation").textContent = money.format(data.allocation_usd);
  document.querySelector("#positionLimit").textContent = data.max_open_positions;
  document.querySelector("#slippage").textContent = `${data.slippage_bps} bps`;
  document.querySelector("#startedAt").textContent = dateTime(data.started_at);
  document.querySelector("#updatedAt").textContent = `Оновлено ${dateTime(data.updated_at)}`;
  document.querySelector("#positionCount").textContent = data.positions.length;
  document.querySelector("#closedPositionCount").textContent = data.closed_positions.length;

  const traderStats = data.trader_stats || [];
  const currentAaCount = traderStats.filter((item) => item.current_aa).length;
  const historicalCount = traderStats.length - currentAaCount;
  document.querySelector("#traderStatsTabCount").textContent = currentAaCount;
  const traderStatsBody = document.querySelector("#traderStatsBody");
  if (!traderStats.length) {
    traderStatsBody.innerHTML = '<tr><td colspan="10" class="empty">Трейдерів A/A ще немає.</td></tr>';
  } else {
    traderStatsBody.innerHTML = sortedTraderStats(traderStats).map((item, index) => {
      const realizedClass = item.realized_pnl_usd >= 0 ? "positive" : "negative";
      const openClass = item.open_pnl_usd >= 0 ? "positive" : "negative";
      const totalClass = item.total_pnl_usd >= 0 ? "positive" : "negative";
      const signedMoney = (value) => `${value >= 0 ? "+" : ""}${money.format(value)}`;
      return `<tr>
        <td class="rank">${String(index + 1).padStart(2, "0")}</td>
        <td><a class="wallet" href="https://solscan.io/account/${encodeURIComponent(item.source_wallet)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(item.source_wallet)}">${escapeHtml(shortAddress(item.source_wallet))}</a></td>
        <td><span class="trader-status ${item.current_aa ? "active" : "historical"}">${item.current_aa ? "A/A зараз" : "Архівний"}</span></td>
        <td class="numeric"><strong>${number(item.closed_trades, 0)}</strong><small>прибуткових: ${number(item.profitable_closed_trades, 0)}</small></td>
        <td class="numeric">${number(item.open_positions, 0)}</td>
        <td class="numeric">${number(item.closed_win_rate_pct, 1)}%</td>
        <td class="numeric pnl ${realizedClass}">${signedMoney(item.realized_pnl_usd)}</td>
        <td class="numeric pnl ${openClass}">${signedMoney(item.open_pnl_usd)}</td>
        <td class="numeric pnl ${totalClass}"><strong>${signedMoney(item.total_pnl_usd)}</strong></td>
        <td class="numeric pnl ${totalClass}"><strong>${item.total_roi_pct >= 0 ? "+" : ""}${number(item.total_roi_pct, 2)}%</strong></td>
      </tr>`;
    }).join("");
  }
  document.querySelector("#traderStatsTab").title = historicalCount
    ? `${currentAaCount} поточних A/A та ${historicalCount} архівних трейдерів з угодами`
    : `${currentAaCount} поточних трейдерів A/A`;

  const body = document.querySelector("#positionsBody");
  if (!data.positions.length) {
    body.innerHTML = '<tr><td colspan="11" class="empty">Зараз відкритих позицій немає.</td></tr>';
  } else {
    body.innerHTML = sortedOpenPositions(data.positions).map((item, index) => {
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

  const closedBody = document.querySelector("#closedPositionsBody");
  if (!data.closed_positions.length) {
    closedBody.innerHTML = '<tr><td colspan="11" class="empty">Закритих позицій ще немає.</td></tr>';
    return;
  }
  closedBody.innerHTML = sortedClosedPositions(data.closed_positions).map((item, index) => {
    const pnlClass = item.realized_pnl_usd >= 0 ? "positive" : "negative";
    const pnlSign = item.realized_pnl_usd >= 0 ? "+" : "";
    const symbol = escapeHtml(item.symbol || "UNKNOWN");
    return `<tr>
      <td class="rank">${String(index + 1).padStart(2, "0")}</td>
      <td class="asset-cell"><strong>${symbol}</strong><a href="https://solscan.io/token/${encodeURIComponent(item.token_address)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(item.token_address)}">${escapeHtml(shortAddress(item.token_address))}</a></td>
      <td><a class="wallet" href="https://solscan.io/account/${encodeURIComponent(item.source_wallet)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(item.source_wallet)}">${escapeHtml(shortAddress(item.source_wallet))}</a></td>
      <td class="numeric"><strong>${number(item.quantity)}</strong><small>джерело: ${number(item.source_amount)}</small></td>
      <td class="numeric">${price(item.entry_price_usd)}</td>
      <td class="numeric">${price(item.exit_price_usd)}</td>
      <td class="numeric">${money.format(item.cost_basis_usd)}</td>
      <td class="numeric">${money.format(item.exit_value_usd)}</td>
      <td class="numeric pnl ${pnlClass}"><strong>${pnlSign}${money.format(item.realized_pnl_usd)}</strong><small>${pnlSign}${number(item.realized_roi_pct, 2)}%</small></td>
      <td class="date-cell">${dateTime(item.closed_at)}</td>
      <td><a class="transaction-link" href="https://solscan.io/tx/${encodeURIComponent(item.source_signature)}" target="_blank" rel="noopener noreferrer">Solscan ↗</a></td>
    </tr>`;
  }).join("");
}

function toggleOpenSort(key) {
  const current = positionState.openSort;
  positionState.openSort = {
    key,
    direction: current.key === key && current.direction === "desc" ? "asc" : "desc",
  };
  updateOpenSortIndicators();
  if (positionState.data) render(positionState.data);
}

function toggleTraderSort(key) {
  const current = positionState.traderSort;
  positionState.traderSort = {
    key,
    direction: current.key === key && current.direction === "desc" ? "asc" : "desc",
  };
  updateTraderSortIndicators();
  if (positionState.data) render(positionState.data);
}

function toggleClosedSort(key) {
  const current = positionState.closedSort;
  positionState.closedSort = {
    key,
    direction: current.key === key && current.direction === "desc" ? "asc" : "desc",
  };
  updateClosedSortIndicators();
  if (positionState.data) render(positionState.data);
}

function selectPositionTab(tab) {
  const closed = tab === "closed";
  const traders = tab === "traders";
  const open = !closed && !traders;
  document.querySelector("#openPositionsTable").hidden = !open;
  document.querySelector("#closedPositionsTable").hidden = !closed;
  document.querySelector("#traderStatsTable").hidden = !traders;
  document.querySelector("#openPositionsTab").classList.toggle("active", open);
  document.querySelector("#closedPositionsTab").classList.toggle("active", closed);
  document.querySelector("#traderStatsTab").classList.toggle("active", traders);
  document.querySelector("#openPositionsTab").setAttribute("aria-selected", String(open));
  document.querySelector("#closedPositionsTab").setAttribute("aria-selected", String(closed));
  document.querySelector("#traderStatsTab").setAttribute("aria-selected", String(traders));
  document.querySelector("#positionsModeBadge").textContent = traders ? "TRADERS" : closed ? "HISTORY" : "LIVE";
  document.querySelector("#positionsModeTitle").textContent = traders ? "Результат за трейдерами" : closed ? "Закриті позиції" : "Відкриті позиції";
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
document.querySelector("#openPositionsTab").addEventListener("click", () => selectPositionTab("open"));
document.querySelector("#closedPositionsTab").addEventListener("click", () => selectPositionTab("closed"));
document.querySelector("#traderStatsTab").addEventListener("click", () => selectPositionTab("traders"));
document.querySelectorAll("[data-open-sort]").forEach((button) => {
  button.addEventListener("click", () => toggleOpenSort(button.dataset.openSort));
});
document.querySelectorAll("[data-trader-sort]").forEach((button) => {
  button.addEventListener("click", () => toggleTraderSort(button.dataset.traderSort));
});
document.querySelectorAll("[data-closed-sort]").forEach((button) => {
  button.addEventListener("click", () => toggleClosedSort(button.dataset.closedSort));
});
