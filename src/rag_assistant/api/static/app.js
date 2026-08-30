const VIEWS = [
  ["chat", "问答"],
  ["knowledge", "知识库"],
  ["chunks", "切片浏览"],
];

const state = {
  view: "chat",
  kbs: [],
  kbId: "policies",
  messages: [],
  detail: null,
  preview: null,
  docs: [],
  chunks: null,
  chunkQ: "",
  status: "",
  error: "",
  busy: false,
};

async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const msg = typeof detail === "string" ? detail : JSON.stringify(detail || res.statusText);
    throw new Error(msg);
  }
  return data;
}

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content;
}

function renderNav() {
  const nav = document.getElementById("nav");
  nav.innerHTML = "";
  for (const [id, label] of VIEWS) {
    const btn = document.createElement("button");
    btn.textContent = label;
    btn.className = state.view === id ? "active" : "";
    btn.onclick = () => {
      state.view = id;
      state.error = "";
      render();
    };
    nav.appendChild(btn);
  }
}

function renderChat(root) {
  const messages = state.messages
    .map((m) => `<div class="bubble ${m.role}">${escapeHtml(m.content)}</div>`)
    .join("");
  const detail = state.detail;
  let side = "<p>提交后显示改写问句、工具与切片。</p>";
  if (detail) {
    side = "";
    if (detail.rewritten_query) side += `<p>检索问句：${escapeHtml(detail.rewritten_query)}</p>`;
    if (detail.routed_tool) {
      side += `<p>工具：<code>${escapeHtml(detail.routed_tool)}</code>${detail.routed_kb_id ? ` · ${escapeHtml(detail.routed_kb_id)}` : ""}</p>`;
    }
    if (detail.refusal_note) side += `<p class="status err">拒答：${escapeHtml(detail.refusal_note)}</p>`;
    for (const c of detail.chunks || []) {
      side += `<div class="chunk"><header><span>${escapeHtml(c.filename || "")}</span><span>${typeof c.score === "number" ? c.score.toFixed(3) : ""}</span></header><pre>${escapeHtml(c.preview || "")}</pre></div>`;
    }
  }
  root.appendChild(el(`
    <section>
      <h1>问答</h1>
      <p class="lede">与 CLI <code>--react</code> 同一条路径：Agent 选工具，答案带来源。</p>
      <div class="chat-layout">
        <div>
          <div class="messages" id="messages">${messages || '<div class="status">试着问：年假有多少天？周凯的隔级上级是谁？</div>'}</div>
          <div class="composer">
            <textarea id="chat-input" placeholder="输入内部问题…"></textarea>
            <button class="primary" id="chat-send"${state.busy ? " disabled" : ""}>${state.busy ? "检索中…" : "发送"}</button>
          </div>
          ${state.error ? `<p class="status err">${escapeHtml(state.error)}</p>` : ""}
        </div>
        <aside class="card"><h3>本轮检索</h3>${side}</aside>
      </div>
    </section>
  `));
  const input = root.querySelector("#chat-input");
  const send = async () => {
    const text = input.value.trim();
    if (!text || state.busy) return;
    input.value = "";
    state.messages.push({ role: "user", content: text });
    state.busy = true;
    state.error = "";
    render();
    try {
      const history = state.messages.slice(0, -1);
      const result = await api("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history }),
      });
      state.messages.push({ role: "assistant", content: result.answer });
      state.detail = result;
    } catch (err) {
      state.error = err.message;
    } finally {
      state.busy = false;
      render();
    }
  };
  root.querySelector("#chat-send").onclick = send;
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });
}

function renderKnowledge(root) {
  const cards = state.kbs
    .map(
      (item) => `
      <button class="card ${item.id === state.kbId ? "selected" : ""}" data-kb="${item.id}">
        <h3>${escapeHtml(item.name)}</h3>
        <p>${escapeHtml(item.tool_name)}</p>
        <p>${item.document_count} 篇 · ${item.chunk_count} 切片</p>
        <p>允许 ${(item.allowed_suffixes || []).join(" ")}</p>
      </button>`,
    )
    .join("");
  const kb = state.kbs.find((k) => k.id === state.kbId);
  const docs = (state.docs || [])
    .map((d) => `<tr><td>${escapeHtml(d.filename)}</td><td>${escapeHtml(d.kind || "")}</td><td>${d.chunk_count}</td></tr>`)
    .join("");
  let previewHtml = "";
  if (state.preview) {
    previewHtml = `<div style="margin-top:20px"><div class="row"><strong>入库前预览</strong>
      <button class="primary" id="commit"${state.busy ? " disabled" : ""}>确认入库</button>
      <button class="ghost" id="cancel-preview">取消</button></div>`;
    for (const file of state.preview.files) {
      previewHtml += `<div style="margin-top:16px"><h3>${escapeHtml(file.filename)} · ${escapeHtml(file.strategy)} · ${file.chunks.length} 块${file.empty ? " · 正文为空" : ""}</h3>`;
      for (const c of file.chunks) {
        previewHtml += `<div class="chunk"><header><span>#${c.index}</span><span>${c.chars} 字</span></header><pre>${escapeHtml(c.text)}</pre></div>`;
      }
      previewHtml += "</div>";
    }
    previewHtml += "</div>";
  }
  root.appendChild(el(`
    <section>
      <h1>知识库</h1>
      <p class="lede">先选对库，再上传。格式不对会被拒绝，避免制度、PDF、表格混进同一个索引。</p>
      <div class="cards">${cards}</div>
      <div class="drop" style="margin-top:20px">
        <p>选择文件，将按 <strong>${escapeHtml(kb?.name || "")}</strong> 的切块策略预览（此时还不写向量库）。</p>
        <input type="file" multiple id="file-input" ${state.busy ? "disabled" : ""} />
      </div>
      ${state.status ? `<p class="status ${state.status.startsWith("完成") ? "ok" : ""}">${escapeHtml(state.status)}</p>` : ""}
      ${previewHtml}
      <h3 style="margin-top:28px">已入库文档</h3>
      <table class="table"><thead><tr><th>文件</th><th>类型</th><th>切片数</th></tr></thead>
      <tbody>${docs || '<tr><td colspan="3">这个库还没有可列出的文档。</td></tr>'}</tbody></table>
    </section>
  `));
  root.querySelectorAll("[data-kb]").forEach((btn) => {
    btn.onclick = async () => {
      state.kbId = btn.dataset.kb;
      state.preview = null;
      await loadDocs();
      render();
    };
  });
  root.querySelector("#file-input").onchange = async (e) => {
    const files = [...e.target.files];
    if (!files.length) return;
    const body = new FormData();
    body.append("kb_id", state.kbId);
    files.forEach((f) => body.append("files", f));
    state.busy = true;
    state.status = "";
    render();
    try {
      state.preview = await api("/api/preview", { method: "POST", body });
      state.status = `已按「${kb?.name || ""}」Profile 切块，请核对后再入库。`;
    } catch (err) {
      state.preview = null;
      state.status = err.message;
    } finally {
      state.busy = false;
      render();
    }
  };
  const commit = root.querySelector("#commit");
  if (commit) {
    commit.onclick = async () => {
      state.busy = true;
      render();
      try {
        const started = await api("/api/ingest", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kb_id: state.preview.kb_id, staging_id: state.preview.staging_id }),
        });
        state.status = "入库任务已提交…";
        for (let i = 0; i < 120; i += 1) {
          const job = await api(`/api/jobs/${started.job_id}`);
          if (job.status === "done") {
            const r = job.result || {};
            state.status = `完成：${r.docs ?? r.documents ?? 0} 篇 / ${r.chunks ?? "—"} 切片`;
            state.preview = null;
            await reloadKbs();
            await loadDocs();
            break;
          }
          if (job.status === "error") {
            state.status = job.message || "入库失败";
            break;
          }
          await new Promise((r) => setTimeout(r, 500));
        }
      } catch (err) {
        state.status = err.message;
      } finally {
        state.busy = false;
        render();
      }
    };
  }
  const cancel = root.querySelector("#cancel-preview");
  if (cancel) {
    cancel.onclick = () => {
      state.preview = null;
      render();
    };
  }
}

function renderChunks(root) {
  const options = state.kbs
    .map((k) => `<option value="${k.id}" ${k.id === state.kbId ? "selected" : ""}>${escapeHtml(k.name)}</option>`)
    .join("");
  const items = (state.chunks?.items || [])
    .map(
      (c) => `<div class="chunk"><header><span>${escapeHtml(c.filename || "")} · #${c.chunk_index}</span><span>${c.chars} 字</span></header><pre>${escapeHtml(c.text || "")}</pre></div>`,
    )
    .join("");
  root.appendChild(el(`
    <section>
      <h1>切片浏览</h1>
      <p class="lede">看索引里真正存了什么。切坏了再回去知识库重传，比猜检索分数更直接。</p>
      <div class="row" style="margin-bottom:16px">
        <select id="chunk-kb">${options}</select>
        <input type="text" id="chunk-q" placeholder="在切片正文中筛选" value="${escapeHtml(state.chunkQ)}" />
        <button class="ghost" id="chunk-search">筛选</button>
      </div>
      ${state.error ? `<p class="status err">${escapeHtml(state.error)}</p>` : ""}
      ${state.chunks ? `<p class="status">共 ${state.chunks.total} 条</p>` : ""}
      ${items}
      <div class="row">
        <button class="ghost" id="prev-page">上一页</button>
        <button class="ghost" id="next-page">下一页</button>
      </div>
    </section>
  `));
  const load = async (offset = 0) => {
    const kb = document.getElementById("chunk-kb").value;
    state.kbId = kb;
    state.chunkQ = document.getElementById("chunk-q").value;
    const query = new URLSearchParams({ offset: String(offset), limit: "20" });
    if (state.chunkQ.trim()) query.set("q", state.chunkQ.trim());
    try {
      state.chunks = await api(`/api/kbs/${kb}/chunks?${query}`);
      state.error = "";
    } catch (err) {
      state.error = err.message;
    }
    render();
  };
  root.querySelector("#chunk-kb").onchange = () => load(0);
  root.querySelector("#chunk-search").onclick = () => load(0);
  root.querySelector("#prev-page").onclick = () => {
    const page = state.chunks;
    if (!page || page.offset <= 0) return;
    load(Math.max(0, page.offset - page.limit));
  };
  root.querySelector("#next-page").onclick = () => {
    const page = state.chunks;
    if (!page || page.offset + page.limit >= page.total) return;
    load(page.offset + page.limit);
  };
}

function render() {
  renderNav();
  const main = document.getElementById("main");
  main.innerHTML = "";
  if (state.view === "chat") renderChat(main);
  if (state.view === "knowledge") renderKnowledge(main);
  if (state.view === "chunks") renderChunks(main);
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function reloadKbs() {
  const data = await api("/api/kbs");
  state.kbs = data.items || [];
  if (!state.kbs.some((k) => k.id === state.kbId) && state.kbs[0]) {
    state.kbId = state.kbs[0].id;
  }
}

async function loadDocs() {
  const data = await api(`/api/kbs/${state.kbId}/documents`);
  state.docs = data.items || [];
}

async function boot() {
  try {
    await reloadKbs();
    await loadDocs();
    state.chunks = await api(`/api/kbs/${state.kbId}/chunks?limit=20`);
  } catch (err) {
    state.error = `无法连接 API：${err.message}`;
  }
  render();
}

boot();
