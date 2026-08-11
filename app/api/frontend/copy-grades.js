const state = { data: null, query: "" };
const labels = {
  "A/A": "Сильні в обох оцінках",
  "B/A": "Copy сильніший за основну",
  "A/B": "Сильна основна, ручний контроль",
  "B/B": "Стабільні кандидати B-рівня",
};
const modeLabels = {
  automatic: "авто",
  manual: "ручний",
  unsuitable: "не рекомендовано",
};
const KYIV_TIMEZONE = "Europe/Kyiv";

const escapeHtml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function renderSummary(groups) {
  document.querySelector("#summary").innerHTML = groups.map((group) => `
    <article class="stat-card" data-grade="${group.grade_pair}">
      <span class="stat-label">${group.grade_pair}</span>
      <strong class="stat-value">${group.count}</strong>
    </article>
  `).join("");
}

function walletRow(item, index) {
  const wallet = escapeHtml(item.wallet);
  const mode = modeLabels[item.copy_mode] || item.copy_mode || "—";
  return `
    <tr>
      <td class="rank">${String(index + 1).padStart(2, "0")}</td>
      <td class="wallet-cell">
        <a class="wallet" href="https://solscan.io/account/${wallet}" target="_blank" rel="noreferrer">${wallet}</a>
        <button class="copy-button" type="button" data-wallet="${wallet}" aria-label="Копіювати адресу">copy</button>
      </td>
      <td class="score main-score">${item.main_score.toFixed(2)} <small>${item.main_grade}</small></td>
      <td class="score copy-score">${item.copy_score.toFixed(2)} <small>${item.copy_grade}</small></td>
      <td><span class="mode">${escapeHtml(mode)}</span></td>
      <td class="transactions">${item.transactions.toLocaleString("uk-UA")}</td>
    </tr>`;
}

function renderGroups() {
  if (!state.data) return;
  const query = state.query.trim().toLowerCase();
  document.querySelector("#groups").innerHTML = state.data.groups.map((group) => {
    const items = group.items.filter((item) => item.wallet.toLowerCase().includes(query));
    const body = items.length
      ? `<div class="table-wrap"><table>
          <thead><tr><th>#</th><th>Гаманець</th><th>Основна</th><th>Copy</th><th>Режим</th><th>Транзакції</th></tr></thead>
          <tbody>${items.map(walletRow).join("")}</tbody>
        </table></div>`
      : `<div class="empty">${query ? "За цим запитом нічого не знайдено" : "У цій категорії поки немає гаманців"}</div>`;
    return `
      <article class="grade-section" data-grade="${group.grade_pair}">
        <header class="grade-header">
          <div class="grade-title"><span class="grade-badge">${group.grade_pair}</span><span class="grade-name">${labels[group.grade_pair]}</span></div>
          <span class="grade-count">${items.length} / ${group.count}</span>
        </header>
        ${body}
      </article>`;
  }).join("");
}

async function loadData() {
  const status = document.querySelector("#connection");
  const error = document.querySelector("#error");
  try {
    const response = await fetch("/api/v1/copy-grades", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    renderSummary(state.data.groups);
    renderGroups();
    status.textContent = "LIVE";
    status.classList.remove("offline");
    error.hidden = true;
    document.querySelector("#walletTotal").textContent = `${state.data.total} гаманців`;
    document.querySelector("#tokensTotal").textContent = state.data.tokens_total;
    document.querySelector("#tokensCompleted").textContent = state.data.tokens_completed;
    document.querySelector("#tokensInProgress").textContent = state.data.tokens_in_progress;
    document.querySelector("#updatedAt").textContent = state.data.updated_at
      ? `Оновлено ${new Date(state.data.updated_at).toLocaleString("uk-UA")}`
      : "Дані очікуються";
  } catch (reason) {
    status.textContent = "OFFLINE";
    status.classList.add("offline");
    error.textContent = `Не вдалося оновити дані: ${reason.message}`;
    error.hidden = false;
  }
}

function formatKyivTime(date) {
  return new Intl.DateTimeFormat("uk-UA", {
    timeZone: KYIV_TIMEZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function scheduleHalfHourRefresh() {
  const now = new Date();
  const next = new Date(now);
  next.setSeconds(0, 0);
  if (now.getMinutes() < 30) next.setMinutes(30);
  else {
    next.setMinutes(0);
    next.setHours(next.getHours() + 1);
  }
  document.querySelector("#nextRefresh").textContent = `${formatKyivTime(next)} · Київ`;
  setTimeout(async () => {
    await loadData();
    scheduleHalfHourRefresh();
  }, Math.max(1_000, next.getTime() - now.getTime()));
}

document.querySelector("#searchInput").addEventListener("input", (event) => {
  state.query = event.target.value;
  renderGroups();
});

document.querySelector("#groups").addEventListener("click", async (event) => {
  const button = event.target.closest(".copy-button");
  if (!button) return;
  await navigator.clipboard.writeText(button.dataset.wallet);
  button.textContent = "copied";
  setTimeout(() => { button.textContent = "copy"; }, 1200);
});

loadData();
scheduleHalfHourRefresh();
