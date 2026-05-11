const state = {
  selectedPath: "",
  scope: "all",
  query: "",
};

const els = {
  health: document.querySelector("#health"),
  aiProvider: document.querySelector("#aiProvider"),
  searchForm: document.querySelector("#searchForm"),
  uploadForm: document.querySelector("#uploadForm"),
  queryInput: document.querySelector("#queryInput"),
  scopeInput: document.querySelector("#scopeInput"),
  targetInput: document.querySelector("#targetInput"),
  fileInput: document.querySelector("#fileInput"),
  refreshBtn: document.querySelector("#refreshBtn"),
  rebuildIndexBtn: document.querySelector("#rebuildIndexBtn"),
  heroRefreshBtn: document.querySelector("#heroRefreshBtn"),
  heroRebuildBtn: document.querySelector("#heroRebuildBtn"),
  results: document.querySelector("#results"),
  resultCount: document.querySelector("#resultCount"),
  selectedPath: document.querySelector("#selectedPath"),
  preview: document.querySelector("#preview"),
  aiOutput: document.querySelector("#aiOutput"),
  toast: document.querySelector("#toast"),
  statTotalFiles: document.querySelector("#statTotalFiles"),
  statTextFiles: document.querySelector("#statTextFiles"),
  statRawFiles: document.querySelector("#statRawFiles"),
  statWikiFiles: document.querySelector("#statWikiFiles"),
  statIndexedFiles: document.querySelector("#statIndexedFiles"),
  statTotalBytes: document.querySelector("#statTotalBytes"),
  areas: document.querySelector("#areas"),
  suffixes: document.querySelector("#suffixes"),
  recentFiles: document.querySelector("#recentFiles"),
  indexDbPath: document.querySelector("#indexDbPath"),
  indexStatePill: document.querySelector("#indexStatePill"),
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
  return String(value)
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
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `${response.status} ${response.statusText}`);
  }
  return data;
}

function formatSummary(summary) {
  if (!summary) return "-";
  if (summary.rebuild) {
    return `重建完成，扫描 ${summary.scanned} 项`;
  }
  if (summary.scanned) {
    return `最近同步 ${summary.scanned} 项，更新 ${summary.updated + summary.inserted}`;
  }
  return "-";
}

function renderIndexStatus(index) {
  if (!index) return;
  els.indexDbPath.textContent = index.db_path || "未配置数据库路径";
  els.indexLastIndexed.textContent = index.last_indexed_at || "-";
  els.indexLastRebuild.textContent = index.last_rebuild_at || "-";
  els.indexLastSummary.textContent = formatSummary(index.last_sync_summary);
  els.indexStatePill.textContent = index.exists ? "索引已就绪" : "未建立索引";
  els.indexStatePill.classList.toggle("ok", Boolean(index.exists));
  els.statIndexedFiles.textContent = String(index.indexed_files || 0);
}

async function loadHealth() {
  const data = await requestJson("/api/health");
  els.health.textContent = `${data.files} 个已索引文件 · ${data.repo_root}`;
  els.aiProvider.textContent = data.ai_provider;
  renderIndexStatus(data.index);
}

function renderListBlock(container, items, emptyText, renderItem) {
  if (!items || !items.length) {
    container.innerHTML = `<div class="empty">${escapeHtml(emptyText)}</div>`;
    return;
  }
  container.innerHTML = items.map(renderItem).join("");
}

function renderDashboard(data) {
  const summary = data.summary || {};
  els.statTotalFiles.textContent = String(summary.total_files || 0);
  els.statTextFiles.textContent = String(summary.text_files || 0);
  els.statRawFiles.textContent = String(summary.raw_files || 0);
  els.statWikiFiles.textContent = String(summary.wiki_files || 0);
  els.statTotalBytes.textContent = formatBytes(summary.total_bytes || 0);
  renderIndexStatus(data.index_status || {});

  renderListBlock(
    els.areas,
    data.areas || [],
    "暂无目录统计。",
    (item) => `
      <article class="list-row">
        <div>
          <strong>${escapeHtml(item.name)}</strong>
          <span>${formatBytes(item.bytes)} · ${item.files} 个文件</span>
        </div>
        <span class="badge">${item.files}</span>
      </article>
    `
  );

  renderListBlock(
    els.suffixes,
    data.suffixes || [],
    "暂无格式统计。",
    (item) => `
      <article class="list-row">
        <div>
          <strong>${escapeHtml(item.suffix)}</strong>
          <span>${item.files} 个文件</span>
        </div>
        <span class="badge">${item.files}</span>
      </article>
    `
  );

  renderListBlock(
    els.recentFiles,
    data.recent_files || [],
    "暂无最近更新。",
    (item) => `
      <article class="list-row">
        <div>
          <strong>${escapeHtml(item.title || item.path)}</strong>
          <span>${escapeHtml(item.path)}</span>
          <span>${escapeHtml(item.modified)} · ${formatBytes(item.size)}</span>
        </div>
        <span class="badge">${escapeHtml(item.section)}</span>
      </article>
    `
  );
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
      const previewButton = item.text
        ? `<button data-action="preview" data-path="${escapeHtml(item.path)}">预览</button>`
        : "";
      const aiButton = item.text
        ? `<button data-action="ai" data-path="${escapeHtml(item.path)}">AI建议</button>`
        : "";
      const summary = item.summary ? `<div class="summary">${escapeHtml(item.summary)}</div>` : "";
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
    <h3>${escapeHtml(data.title || "未命名材料")}</h3>
    <div>类型：${escapeHtml(data.material_type || "unknown")}</div>
    <div>建议归档：${escapeHtml(data.suggested_archive || "raw/inbox")}</div>
    <div>来源页：${escapeHtml(data.source_page || "")}</div>
    <div>摘要：${escapeHtml(data.summary || "")}</div>
    <div>
      <strong>建议关联</strong>
      <ul>${targets || "<li>暂不提升到其他页面</li>"}</ul>
    </div>
    <div>
      <strong>下一步</strong>
      <ul>${actions}</ul>
    </div>
    <div>
      <strong>来源页草稿</strong>
      <pre class="draft">${escapeHtml(data.source_draft || "")}</pre>
    </div>
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
  els.indexStatePill.textContent = "索引重建中...";
  els.indexStatePill.classList.remove("ok");
  const data = await requestJson("/api/index/rebuild", { method: "POST" });
  showToast(`索引重建完成：扫描 ${data.scanned} 项，耗时 ${data.duration_ms}ms`);
  await refreshAll();
}

async function refreshAll() {
  await Promise.all([loadHealth(), loadDashboard(), loadFiles()]);
}

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

async function handleRefresh() {
  try {
    await refreshAll();
    showToast("已刷新工作台。");
  } catch (error) {
    showToast(error.message);
  }
}

els.refreshBtn.addEventListener("click", handleRefresh);
els.heroRefreshBtn.addEventListener("click", handleRefresh);

async function handleRebuild() {
  try {
    await rebuildIndex();
  } catch (error) {
    showToast(error.message);
  }
}

els.rebuildIndexBtn.addEventListener("click", handleRebuild);
els.heroRebuildBtn.addEventListener("click", handleRebuild);

els.results.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const action = button.dataset.action;
  const path = button.dataset.path;
  try {
    if (action === "preview") await previewFile(path);
    if (action === "ai") await suggestWithAi(path);
    if (action === "delete") await deleteFile(path);
  } catch (error) {
    showToast(error.message);
  }
});

refreshAll().catch((error) => {
  els.health.textContent = `连接失败：${error.message}`;
  showToast(error.message);
});
