const state = {
  selectedPath: "",
  scope: "inbox",
  query: "",
  authenticated: false,
};

const els = {
  loginView: document.querySelector("#loginView"),
  appShell: document.querySelector("#appShell"),
  loginForm: document.querySelector("#loginForm"),
  loginUser: document.querySelector("#loginUser"),
  loginPassword: document.querySelector("#loginPassword"),
  loginMessage: document.querySelector("#loginMessage"),
  logoutBtn: document.querySelector("#logoutBtn"),
  authLabel: document.querySelector("#authLabel"),
  health: document.querySelector("#health"),
  aiProvider: document.querySelector("#aiProvider"),
  aiHint: document.querySelector("#aiHint"),
  searchForm: document.querySelector("#searchForm"),
  uploadForm: document.querySelector("#uploadForm"),
  queryInput: document.querySelector("#queryInput"),
  scopeInput: document.querySelector("#scopeInput"),
  targetInput: document.querySelector("#targetInput"),
  fileInput: document.querySelector("#fileInput"),
  refreshBtn: document.querySelector("#refreshBtn"),
  rebuildIndexBtn: document.querySelector("#rebuildIndexBtn"),
  results: document.querySelector("#results"),
  resultCount: document.querySelector("#resultCount"),
  selectedPath: document.querySelector("#selectedPath"),
  preview: document.querySelector("#preview"),
  aiOutput: document.querySelector("#aiOutput"),
  toast: document.querySelector("#toast"),
  statTotalFiles: document.querySelector("#statTotalFiles"),
  statIndexedFiles: document.querySelector("#statIndexedFiles"),
  pipelineInboxCount: document.querySelector("#pipelineInboxCount"),
  pipelineGapCount: document.querySelector("#pipelineGapCount"),
  pipelineText: document.querySelector("#pipelineText"),
  sourceGaps: document.querySelector("#sourceGaps"),
  recentFiles: document.querySelector("#recentFiles"),
  indexDbPath: document.querySelector("#indexDbPath"),
  indexLastIndexed: document.querySelector("#indexLastIndexed"),
  indexLastRebuild: document.querySelector("#indexLastRebuild"),
  indexLastSummary: document.querySelector("#indexLastSummary"),
};

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.setTimeout(() => els.toast.classList.remove("show"), 2600);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: {
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) {
    showLogin();
    throw new Error(data.error || "请先登录。");
  }
  if (!response.ok) {
    throw new Error(data.error || `${response.status} ${response.statusText}`);
  }
  return data;
}

function showLogin(message = "") {
  state.authenticated = false;
  els.loginView.classList.remove("hidden");
  els.appShell.classList.add("hidden");
  els.authLabel.textContent = "未登录";
  els.loginMessage.textContent = message;
  window.setTimeout(() => els.loginPassword.focus(), 0);
}

function showApp(username) {
  state.authenticated = true;
  els.loginView.classList.add("hidden");
  els.appShell.classList.remove("hidden");
  els.authLabel.textContent = username ? `已登录：${username}` : "已登录";
}

function formatSummary(summary) {
  if (!summary) return "-";
  if (summary.rebuild) {
    return `重建完成，扫描 ${summary.scanned} 项`;
  }
  if (summary.scanned) {
    return `同步 ${summary.scanned} 项，新增 ${summary.inserted}，更新 ${summary.updated}`;
  }
  return "-";
}

function renderIndexStatus(index) {
  if (!index) return;
  els.indexDbPath.textContent = index.db_path || "未配置索引数据库路径";
  els.indexLastIndexed.textContent = index.last_indexed_at || "-";
  els.indexLastRebuild.textContent = index.last_rebuild_at || "-";
  els.indexLastSummary.textContent = formatSummary(index.last_sync_summary);
  els.statIndexedFiles.textContent = String(index.indexed_files || 0);
}

async function loadAuthStatus() {
  const data = await requestJson("/api/auth/status");
  if (data.authenticated) {
    showApp(data.username);
    return data;
  }
  showLogin(data.required ? "" : "当前未启用登录。");
  return data;
}

async function loadHealth() {
  const data = await requestJson("/api/health");
  els.health.textContent = `${data.files} 个文件已索引 · ${data.repo_root}`;
  els.aiProvider.textContent = data.ai_provider;
  els.aiHint.textContent =
    data.ai_provider === "local-rules"
      ? "当前未配置外部 AI Key，使用本地规则生成建议。"
      : `已接入 ${data.ai_provider}${data.ai_model ? ` · ${data.ai_model}` : ""}`;
  renderIndexStatus(data.index);
}

function renderDashboard(data) {
  const summary = data.summary || {};
  els.statTotalFiles.textContent = String(summary.total_files || 0);
  renderIndexStatus(data.index_status || {});

  const recent = data.recent_files || [];
  if (!recent.length) {
    els.recentFiles.innerHTML = `<div class="empty">暂无最近更新。</div>`;
    return;
  }
  els.recentFiles.innerHTML = recent
    .map(
      (item) => `
        <button class="mini-row" data-action="preview" data-path="${escapeHtml(item.path)}">
          <strong>${escapeHtml(item.title || item.path)}</strong>
          <span>${escapeHtml(item.path)} · ${formatBytes(item.size)}</span>
        </button>
      `
    )
    .join("");
}

function renderPipeline(status) {
  els.pipelineInboxCount.textContent = String(status.inbox_count || 0);
  els.pipelineGapCount.textContent = String(status.source_gaps_count || 0);
  els.pipelineText.textContent = `隐藏样例 ${status.examples_hidden || 0} 个；AI 提供方：${status.ai_provider}`;
  const gaps = status.source_gaps || [];
  if (!gaps.length) {
    els.sourceGaps.innerHTML = `<div class="empty">没有发现缺来源页的 raw 文件。</div>`;
    return;
  }
  els.sourceGaps.innerHTML = gaps
    .slice(0, 6)
    .map(
      (item) => `
        <button class="mini-row" data-action="preview" data-path="${escapeHtml(item.path)}">
          <strong>${escapeHtml(item.name)}</strong>
          <span>${escapeHtml(item.source_page)}</span>
        </button>
      `
    )
    .join("");
}

function renderResults(items) {
  els.resultCount.textContent = `${items.length} 项`;
  if (!items.length) {
    els.results.innerHTML = `<div class="empty">没有找到匹配文件。</div>`;
    return;
  }

  els.results.innerHTML = items
    .map((item) => {
      const matches = item.matches && item.matches.length
        ? `<div class="matches">${item.matches
            .map((match) => `<div class="match">L${match.line}: ${escapeHtml(match.snippet)}</div>`)
            .join("")}</div>`
        : "";
      const summary = item.summary ? `<p class="summary">${escapeHtml(item.summary)}</p>` : "";
      const previewButton = item.text
        ? `<button data-action="preview" data-path="${escapeHtml(item.path)}">预览</button>`
        : "";
      const aiButton = item.text
        ? `<button data-action="ai" data-path="${escapeHtml(item.path)}">建议</button>`
        : "";
      const processButton = item.path.startsWith("raw/")
        ? `<button class="primary-mini" data-action="process" data-path="${escapeHtml(item.path)}">处理</button>`
        : "";
      return `
        <article class="file-row">
          <div class="file-main">
            <div class="path">${escapeHtml(item.path)}</div>
            <div class="meta">${escapeHtml(item.area || item.section)} · ${formatBytes(item.size)} · ${escapeHtml(item.modified)}</div>
            ${summary}
            ${matches}
          </div>
          <div class="actions">
            ${previewButton}
            ${aiButton}
            ${processButton}
            <button class="danger" data-action="delete" data-path="${escapeHtml(item.path)}">删除</button>
          </div>
        </article>
      `;
    })
    .join("");
}

async function loadFiles() {
  const params = new URLSearchParams();
  params.set("scope", state.scope);
  if (state.query) params.set("q", state.query);
  const data = await requestJson(`/api/files?${params.toString()}`);
  renderResults(data.items || []);
}

async function loadDashboard() {
  const data = await requestJson("/api/dashboard");
  renderDashboard(data);
}

async function loadPipeline() {
  const data = await requestJson("/api/pipeline/status");
  renderPipeline(data);
}

async function previewFile(path) {
  const data = await requestJson(`/api/file?path=${encodeURIComponent(path)}`);
  state.selectedPath = data.path;
  els.selectedPath.textContent = data.path;
  els.preview.textContent = data.content + (data.truncated ? "\n\n[预览已截断]" : "");
}

function renderAiSuggestion(data) {
  const targets = (data.wiki_targets || []).map((target) => `<li>${escapeHtml(target)}</li>`).join("");
  const actions = (data.actions || []).map((action) => `<li>${escapeHtml(action)}</li>`).join("");
  els.aiOutput.innerHTML = `
    <h3>${escapeHtml(data.title || "未命名资料")}</h3>
    <dl class="kv inline">
      <div><dt>提供方</dt><dd>${escapeHtml(data.provider || "unknown")}</dd></div>
      <div><dt>类型</dt><dd>${escapeHtml(data.material_type || "unknown")}</dd></div>
      <div><dt>归档</dt><dd>${escapeHtml(data.suggested_archive || "raw/inbox")}</dd></div>
      <div><dt>来源页</dt><dd>${escapeHtml(data.source_page || "")}</dd></div>
    </dl>
    <p>${escapeHtml(data.summary || "")}</p>
    <strong>建议关联</strong>
    <ul>${targets || "<li>暂不提升到其他页面</li>"}</ul>
    <strong>下一步</strong>
    <ul>${actions || "<li>人工复核后再处理。</li>"}</ul>
    <details>
      <summary>查看来源页草稿</summary>
      <pre class="draft">${escapeHtml(data.source_draft || "")}</pre>
    </details>
  `;
}

async function suggestWithAi(path) {
  els.aiOutput.textContent = "正在生成建议...";
  const data = await requestJson("/api/ai/suggest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  renderAiSuggestion(data);
}

function renderProcessResult(data) {
  const actions = (data.actions || [])
    .map((action) => `<li>${escapeHtml(action.type)}：${escapeHtml(action.to || action.path || action.reason || "")}</li>`)
    .join("");
  els.aiOutput.innerHTML = `
    <h3>处理完成</h3>
    <p>原始路径：${escapeHtml(data.path)}</p>
    <p>当前路径：${escapeHtml(data.final_path)}</p>
    <p>来源页：${escapeHtml(data.source_page)}</p>
    <ul>${actions}</ul>
  `;
}

async function processFile(path) {
  const data = await requestJson("/api/pipeline/process", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, create_source: true, archive: true }),
  });
  renderProcessResult(data);
  showToast("资料处理完成。");
  await refreshAll();
}

async function deleteFile(path) {
  const confirmed = window.confirm(`将文件移入回收站：\n${path}`);
  if (!confirmed) return;
  const data = await requestJson(`/api/file?path=${encodeURIComponent(path)}`, { method: "DELETE" });
  showToast(`已移入回收站：${data.trash_path}`);
  if (state.selectedPath === path) {
    state.selectedPath = "";
    els.selectedPath.textContent = "未选择文件";
    els.preview.textContent = "选择一个文本文件查看内容。";
  }
  await refreshAll();
}

async function rebuildIndex() {
  const data = await requestJson("/api/index/rebuild", { method: "POST" });
  showToast(`索引重建完成：扫描 ${data.scanned} 项，耗时 ${data.duration_ms}ms`);
  await refreshAll();
}

async function refreshAll() {
  await Promise.all([loadHealth(), loadDashboard(), loadPipeline(), loadFiles()]);
}

els.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  els.loginMessage.textContent = "正在登录...";
  try {
    const data = await requestJson("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: els.loginUser.value.trim(),
        password: els.loginPassword.value,
      }),
    });
    showApp(data.username);
    els.loginPassword.value = "";
    await refreshAll();
  } catch (error) {
    els.loginMessage.textContent = error.message;
  }
});

els.logoutBtn.addEventListener("click", async () => {
  try {
    await requestJson("/api/auth/logout", { method: "POST" });
  } finally {
    showLogin("已退出。");
  }
});

els.searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  state.query = els.queryInput.value.trim();
  state.scope = els.scopeInput.value;
  try {
    await loadFiles();
  } catch (error) {
    showToast(error.message);
  }
});

els.uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = els.fileInput.files[0];
  if (!file) {
    showToast("请选择文件。");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  formData.append("target_dir", els.targetInput.value);
  try {
    await requestJson("/api/upload", { method: "POST", body: formData });
    els.fileInput.value = "";
    showToast("上传完成。");
    await refreshAll();
  } catch (error) {
    showToast(error.message);
  }
});

els.refreshBtn.addEventListener("click", async () => {
  try {
    await refreshAll();
    showToast("已刷新工作台。");
  } catch (error) {
    showToast(error.message);
  }
});

els.rebuildIndexBtn.addEventListener("click", async () => {
  try {
    await rebuildIndex();
  } catch (error) {
    showToast(error.message);
  }
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const action = button.dataset.action;
  const path = button.dataset.path;
  try {
    if (action === "preview") await previewFile(path);
    if (action === "ai") await suggestWithAi(path);
    if (action === "process") await processFile(path);
    if (action === "delete") await deleteFile(path);
  } catch (error) {
    showToast(error.message);
  }
});

loadAuthStatus()
  .then((data) => {
    if (data.authenticated) return refreshAll();
    return null;
  })
  .catch((error) => {
    showLogin(error.message);
  });
