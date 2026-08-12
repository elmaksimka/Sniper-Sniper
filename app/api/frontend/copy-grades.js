const state = {
  data: null,
  query: "",
  tokenFilter: null,
  selectedTokenIndex: null,
  gradeFilter: null,
  sorts: [],
};
const labels = {
  "A/A": "Сильні в обох оцінках · усі режими",
  "B/A": "Copy сильніший за основну · усі режими",
  "A/B": "Сильна основна, Copy B · усі режими",
};
const modeLabels = {
  automatic: "авто",
  manual: "ручний",
  unsuitable: "не рекомендовано",
};
const KYIV_TIMEZONE = "Europe/Kyiv";

function addedAtText(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("uk-UA", {
    timeZone: KYIV_TIMEZONE,
    dateStyle: "short",
  }).format(new Date(value));
}

const escapeHtml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function renderSummary(groups) {
  document.querySelector("#summary").innerHTML = groups.map((group) => `
    <button type="button" class="stat-card" data-grade="${group.grade_pair}" data-grade-filter="${group.grade_pair}">
      <span class="stat-label">${group.grade_pair}</span>
      <strong class="stat-value">${group.count}</strong>
    </button>
  `).join("");
}

const scoreText = (value) => value === null || value === undefined
  ? "—"
  : String(value);

function tokenTraderRow(trader) {
  const wallet = escapeHtml(trader.wallet);
  const identity = trader.label
    ? `${escapeHtml(trader.label)} <small>${wallet}</small>`
    : wallet;
  const mainGrade = trader.main_grade ? ` <small>${escapeHtml(trader.main_grade)}</small>` : "";
  const copyGrade = trader.copy_grade ? ` <small>${escapeHtml(trader.copy_grade)}</small>` : "";
  const progress = `${trader.transactions.toLocaleString("uk-UA")} / ${
    trader.total_transactions === null || trader.total_transactions === undefined
      ? "рахується"
      : trader.total_transactions.toLocaleString("uk-UA")
  }`;
  return `
    <tr>
      <td class="rank">${String(trader.rank).padStart(2, "0")}</td>
      <td class="wallet-cell token-wallet"><a class="wallet" href="https://solscan.io/account/${encodeURIComponent(trader.wallet)}" target="_blank" rel="noreferrer">${identity}</a></td>
      <td class="score main-score">${scoreText(trader.main_score)}${mainGrade}</td>
      <td class="score copy-score">${scoreText(trader.copy_score)}${copyGrade}</td>
      <td><span class="mode">${escapeHtml(modeLabels[trader.copy_mode] || trader.copy_mode || "—")}</span></td>
      <td class="transactions">${progress}</td>
      <td class="added-at">${addedAtText(trader.added_at)}</td>
    </tr>`;
}

function tokenMatchesGrade(token, gradePair) {
  return token.traders.some((trader) =>
    `${trader.main_grade || ""}/${trader.copy_grade || ""}` === gradePair
  );
}

function renderTokenDetails(filter) {
  if (!state.data) return;
  state.tokenFilter = filter;
  state.selectedTokenIndex = null;
  let tokens = (state.data.tokens || []).map((token, index) => ({ token, index }));
  let title = "Усі монети аудиту";
  if (filter === "completed") {
    tokens = tokens.filter(({ token }) => token.complete);
    title = "Пройдені монети";
  } else if (filter === "in-progress") {
    tokens = tokens.filter(({ token }) => !token.complete);
    title = "Монети у роботі / черзі";
  } else if (filter && filter.includes("/")) {
    tokens = tokens.filter(({ token }) => tokenMatchesGrade(token, filter));
    title = `Монети з трейдерами категорії ${filter}`;
  }

  document.querySelector("#tokenDetailsTitle").textContent = `${title} · ${tokens.length}`;
  document.querySelector("#backToTokens").hidden = true;
  document.querySelector("#tokenList").innerHTML = tokens.length ? tokens.map(({ token, index }) => {
    const symbol = escapeHtml(token.symbol || "Без назви");
    return `
      <button type="button" class="token-list-item" data-token-index="${index}">
        <strong>${symbol}</strong>
      </button>`;
  }).join("") : `<div class="empty">Для цього лічильника монет поки немає</div>`;

  const details = document.querySelector("#tokenDetails");
  details.hidden = false;
  details.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSelectedToken(index) {
  const token = state.data?.tokens?.[index];
  if (!token) return;
  state.selectedTokenIndex = index;
  let traders = token.traders || [];
  if (state.tokenFilter && state.tokenFilter.includes("/")) {
    traders = traders.filter((trader) =>
      `${trader.main_grade || ""}/${trader.copy_grade || ""}` === state.tokenFilter
    );
  }
  traders = [...traders].sort((left, right) => left.rank - right.rank).slice(0, 10);
  const symbol = escapeHtml(token.symbol || "Без назви");
  const address = escapeHtml(token.token_address);
  const rows = traders.length
    ? traders.map(tokenTraderRow).join("")
    : `<tr><td colspan="7" class="empty">Трейдерів для цієї монети ще немає</td></tr>`;
  document.querySelector("#tokenDetailsTitle").textContent = `${symbol} · топ-10 трейдерів`;
  document.querySelector("#backToTokens").hidden = false;
  document.querySelector("#tokenList").innerHTML = `
    <article class="token-card">
      <header class="token-header">
        <div><h3>${symbol}</h3><a href="https://solscan.io/token/${encodeURIComponent(token.token_address)}" target="_blank" rel="noreferrer">${address || "Адреса очікується"}</a></div>
        <span class="token-progress ${token.complete ? "complete" : ""}">${token.completed_traders} / ${token.total_traders} перевірено</span>
      </header>
      <div class="table-wrap"><table>
        <thead><tr><th>#</th><th>Трейдер</th><th>Основна оцінка</th><th>Copy-оцінка</th><th>Режим</th><th>Проаналізовано / всі</th><th>Додано</th></tr></thead>
        <tbody>${rows}</tbody>
       </table></div>
     </article>`;
  document.querySelector("#tokenDetails").scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

function walletRow(item, index) {
  const wallet = escapeHtml(item.wallet);
  const mode = modeLabels[item.copy_mode] || item.copy_mode || "—";
  const transactionProgress = `${item.transactions.toLocaleString("uk-UA")} / ${
    item.total_transactions === null || item.total_transactions === undefined
      ? "рахується"
      : item.total_transactions.toLocaleString("uk-UA")
  }`;
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
      <td class="transactions">${transactionProgress}</td>
      <td class="added-at">${addedAtText(item.added_at)}</td>
    </tr>`;
}

function renderGroups() {
  if (!state.data) return;
  if (!state.gradeFilter) {
    document.querySelector("#groups").innerHTML = `<div class="empty category-prompt">Оберіть категорію A/A, B/A або A/B, щоб побачити її трейдерів</div>`;
    return;
  }
  const query = state.query.trim().toLowerCase();
  document.querySelector("#groups").innerHTML = state.data.groups
    .filter((group) => group.grade_pair === state.gradeFilter)
    .map((group) => {
    const items = group.items
      .filter((item) => item.wallet.toLowerCase().includes(query));
    if (state.sorts.length) {
      const sort = state.sorts[0];
      items.sort((left, right) => {
        const difference = sortValue(left, sort.key) - sortValue(right, sort.key);
        if (difference !== 0) {
          return sort.direction === "desc" ? -difference : difference;
        }
        return left.wallet.localeCompare(right.wallet);
      });
    }
    const sortIndicator = (key) => {
      const index = state.sorts.findIndex((sort) => sort.key === key);
      if (index < 0) return "";
      return state.sorts[index].direction === "desc" ? " ↓" : " ↑";
    };
    const body = items.length
      ? `<div class="table-wrap"><table>
          <thead><tr><th>#</th><th>Гаманець</th><th><button class="sort-button" type="button" data-sort="main_score" title="↓ більше, ↑ менше, третій клік — вимкнути">Основна${sortIndicator("main_score")}</button></th><th><button class="sort-button" type="button" data-sort="copy_score" title="↓ більше, ↑ менше, третій клік — вимкнути">Copy${sortIndicator("copy_score")}</button></th><th>Режим</th><th><button class="sort-button" type="button" data-sort="transactions" title="↓ більше проаналізовано, ↑ менше, третій клік — вимкнути">Проаналізовано / всі${sortIndicator("transactions")}</button></th><th><button class="sort-button" type="button" data-sort="added_at" title="↓ новіші, ↑ старіші, третій клік — вимкнути">Додано${sortIndicator("added_at")}</button></th></tr></thead>
          <tbody>${items.map(walletRow).join("")}</tbody>
        </table></div>`
      : `<div class="empty">${query ? "За цим запитом нічого не знайдено" : "У цій категорії поки немає гаманців"}</div>`;
    return `
      <article class="grade-section" data-grade="${group.grade_pair}">
        <header class="grade-header">
          <div class="grade-title"><span class="grade-badge">${group.grade_pair}</span><span class="grade-name">${labels[group.grade_pair]}</span></div>
          <span class="grade-count">${items.length}</span>
        </header>
        ${body}
      </article>`;
  }).join("");
}

function sortValue(item, key) {
  if (key === "added_at") return Date.parse(item.added_at || "") || 0;
  return item[key];
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
      ? `Оцінки оновлено ${new Intl.DateTimeFormat("uk-UA", {
          timeZone: KYIV_TIMEZONE,
          dateStyle: "short",
          timeStyle: "medium",
        }).format(new Date(state.data.updated_at))} · Київ`
      : "Дані очікуються";
  } catch (reason) {
    status.textContent = "OFFLINE";
    status.classList.add("offline");
    error.textContent = `Не вдалося оновити дані: ${reason.message}`;
    error.hidden = false;
  }
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
  const sortButton = event.target.closest(".sort-button");
  if (sortButton) {
    const key = sortButton.dataset.sort;
    const index = state.sorts.findIndex((sort) => sort.key === key);
    if (index < 0) {
      state.sorts = [{ key, direction: "desc" }];
    } else if (state.sorts[index].direction === "desc") {
      state.sorts = [{ key, direction: "asc" }];
    } else {
      state.sorts = [];
    }
    renderGroups();
    return;
  }
  const button = event.target.closest(".copy-button");
  if (!button) return;
  await navigator.clipboard.writeText(button.dataset.wallet);
  button.textContent = "copied";
  setTimeout(() => { button.textContent = "copy"; }, 1200);
});

document.addEventListener("click", (event) => {
  const counter = event.target.closest("[data-token-filter]");
  if (counter) {
    state.gradeFilter = null;
    document.querySelectorAll(".stat-card").forEach((item) => {
      item.classList.remove("active");
    });
    renderGroups();
    document.querySelector("#groups").hidden = true;
    renderTokenDetails(counter.dataset.tokenFilter);
  }
});

document.querySelector("#tokenList").addEventListener("click", (event) => {
  const token = event.target.closest("[data-token-index]");
  if (token) renderSelectedToken(Number(token.dataset.tokenIndex));
});

document.querySelector("#summary").addEventListener("click", (event) => {
  const card = event.target.closest("[data-grade-filter]");
  if (!card) return;
  state.gradeFilter = card.dataset.gradeFilter;
  document.querySelector("#tokenDetails").hidden = true;
  document.querySelector("#groups").hidden = false;
  document.querySelectorAll(".stat-card").forEach((item) => {
    item.classList.toggle("active", item === card);
  });
  renderGroups();
  document.querySelector("#groups").scrollIntoView({ behavior: "smooth", block: "start" });
});

document.querySelector("#closeTokenDetails").addEventListener("click", () => {
  state.tokenFilter = null;
  state.selectedTokenIndex = null;
  document.querySelector("#tokenDetails").hidden = true;
  document.querySelector("#groups").hidden = false;
});

document.querySelector("#backToTokens").addEventListener("click", () => {
  renderTokenDetails(state.tokenFilter || "all");
});

document.querySelector("#homeButton").addEventListener("click", () => {
  state.gradeFilter = null;
  state.tokenFilter = null;
  state.selectedTokenIndex = null;
  state.query = "";
  state.sorts = [];
  document.querySelector("#searchInput").value = "";
  document.querySelector("#tokenDetails").hidden = true;
  document.querySelector("#groups").hidden = false;
  document.querySelectorAll(".stat-card").forEach((item) => {
    item.classList.remove("active");
  });
  renderGroups();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

loadData();
scheduleHalfHourRefresh();
