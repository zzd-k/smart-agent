/* SmartAgent Web Demo 前端逻辑：SSE 流式对话 + 打字机 + Markdown 渲染 + 工具轨迹可视化 */
(() => {
  const chatEl = document.getElementById("chat");
  const welcomeEl = document.getElementById("welcome");
  const inputEl = document.getElementById("input");
  const sendBtn = document.getElementById("send");
  const newChatBtn = document.getElementById("newChat");
  const envTip = document.getElementById("envTip");
  const modelBadge = document.getElementById("modelBadge");
  const memBadge = document.getElementById("memBadge");

  // 会话隔离：localStorage 记忆 session_id
  const SKEY = "smartagent_session";
  let sessionId = localStorage.getItem(SKEY) || newSession();
  let busy = false;

  function newSession() {
    const sid = crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36);
    localStorage.setItem(SKEY, sid);
    return sid;
  }

  // 读取后端状态（模型名 / 是否已配置 Key）
  fetch("/api/health")
    .then((r) => r.json())
    .then((d) => {
      if (d.model) modelBadge.textContent = d.model;
      if (d.status === "need_config") {
        envTip.textContent = "⚠️ " + d.issues.join(" ");
        envTip.style.color = "#ffb86b";
        modelBadge.style.color = "#ffb86b";
      }
    })
    .catch(() => {
      modelBadge.textContent = "offline";
    });

  newChatBtn.addEventListener("click", () => {
    sessionId = newSession();
    chatEl.querySelectorAll(".msg, .tool, .thinking-chip").forEach((n) => n.remove());
    welcomeEl.style.display = "";
    updateMemBadge([]);
  });

  // ---------- 工具函数 ----------
  function escapeHtml(s) {
    return String(s).replace(
      /[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  /** 极简 Markdown 渲染：代码块 / 行内代码 / 加粗 / 标题 / 列表 / 引用 / 表格分隔 */
  function renderMarkdown(src) {
    let html = escapeHtml(src);

    // 围栏代码块（先占位，避免内部被后续规则处理）
    const blocks = [];
    html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
      blocks.push(`<pre><code${lang ? ` class="lang-${lang}"` : ""}>${code.replace(/\n$/, "")}</code></pre>`);
      return `\u0000BLOCK${blocks.length - 1}\u0000`;
    });

    html = html
      .replace(/`([^`\n]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*\n]+)\*/g, "<em>$1</em>")
      .replace(/^#### (.*)$/gm, "<h5>$1</h5>")
      .replace(/^### (.*)$/gm, "<h4>$1</h4>")
      .replace(/^## (.*)$/gm, "<h3>$1</h3>")
      .replace(/^# (.*)$/gm, "<h3>$1</h3>")
      .replace(/^&gt; (.*)$/gm, "<blockquote>$1</blockquote>")
      .replace(/^\s*[-*+] (.*)$/gm, "<li>$1</li>")
      .replace(/^\s*(\d+)[.、] (.*)$/gm, "<li>$2</li>")
      .replace(/(?:<li>[\s\S]*?<\/li>\n?)+/g, (m) => `<ul>${m.replace(/\n/g, "")}</ul>`)
      .replace(/\n{2,}/g, "<br><br>");

    // 还原代码块
    html = html.replace(/\u0000BLOCK(\d+)\u0000/g, (_, i) => blocks[Number(i)]);
    return html;
  }

  function scrollBottom() {
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  function updateMemBadge(facts) {
    const n = (facts || []).length;
    memBadge.textContent = `记忆 ${n} 条`;
    memBadge.title = n ? facts.join("\n") : "Agent 长期记忆（facts），对话中提及偏好/身份会自动记住";
    memBadge.classList.toggle("active", n > 0);
  }

  // ---------- 渲染 ----------
  function hideWelcome() {
    if (welcomeEl) welcomeEl.style.display = "none";
  }

  function addUserMsg(text) {
    hideWelcome();
    const m = document.createElement("div");
    m.className = "msg user";
    m.innerHTML = `<div class="avatar">我</div><div class="bubble"></div>`;
    m.querySelector(".bubble").textContent = text;
    chatEl.appendChild(m);
    scrollBottom();
  }

  function addAssistantContainer() {
    hideWelcome();
    const m = document.createElement("div");
    m.className = "msg assistant";
    m.innerHTML = `<div class="avatar">◆</div><div class="bubble"></div>`;
    chatEl.appendChild(m);
    scrollBottom();
    return m;
  }

  function addToolCall(tool, args) {
    const wrap = document.createElement("div");
    wrap.className = "tool";
    const argsStr = JSON.stringify(args || {}, (k, v) =>
      typeof v === "string" && v.length > 80 ? v.slice(0, 80) + "…" : v
    );
    wrap.innerHTML = `<span class="tool-inline">🔧 ${escapeHtml(tool)}</span>
      <div class="tool-detail"><code>${escapeHtml(tool)}</code> <span class="tool-args">${escapeHtml(argsStr)}</span></div>`;
    chatEl.appendChild(wrap);
    scrollBottom();
    return wrap;
  }

  function addThinking() {
    const chip = document.createElement("div");
    chip.className = "thinking-chip";
    chip.innerHTML = `<span class="spinner"></span>思考中…`;
    chatEl.appendChild(chip);
    scrollBottom();
    return chip;
  }

  // ---------- 打字机 ----------
  function createTypewriter(el) {
    let pending = "";
    let typed = "";
    let speed = 18;
    const timer = setInterval(() => {
      if (!pending) return;
      // 文本越长，每次输出越多，保证总时长可控
      const chars = Math.max(1, Math.ceil(pending.length / 60));
      typed += pending.slice(0, chars);
      pending = pending.slice(chars);
      el.textContent = typed;
      scrollBottom();
    }, speed);
    return {
      push(text) {
        pending += text;
      },
      finish(onDone) {
        const wait = setInterval(() => {
          if (pending) return;
          clearInterval(timer);
          clearInterval(wait);
          if (typed) el.innerHTML = renderMarkdown(typed);
          onDone && onDone(typed);
        }, 40);
      },
    };
  }

  // ---------- 发送 ----------
  async function send() {
    const text = inputEl.value.trim();
    if (!text || busy) return;
    busy = true;
    sendBtn.disabled = true;
    inputEl.value = "";
    autoGrow();

    addUserMsg(text);
    const aMsg = addAssistantContainer();
    const bubble = aMsg.querySelector(".bubble");
    const thinking = addThinking();
    const typer = createTypewriter(bubble);
    let gotAny = false;

    const finish = () => {
      typer.finish(() => {
        busy = false;
        sendBtn.disabled = false;
        inputEl.focus();
      });
    };

    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let idx;
        while ((idx = buffer.indexOf("\n\n")) >= 0) {
          const rawEvent = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);

          let type = "";
          let data = "";
          for (const l of rawEvent.split("\n")) {
            if (l.startsWith("event: ")) type = l.slice(7);
            if (l.startsWith("data: ")) data += l.slice(6);
          }
          if (!data) continue;
          let payload;
          try {
            payload = JSON.parse(data);
          } catch {
            continue;
          }

          if (type === "token" && payload.text) {
            thinking.remove();
            typer.push(payload.text);
            gotAny = true;
          } else if (type === "tool_start") {
            thinking.remove();
            addToolCall(payload.tool, payload.args);
          } else if (type === "tool_result" && payload.result) {
            const nodes = chatEl.querySelectorAll(".tool");
            const last = nodes[nodes.length - 1];
            if (last) {
              const d = last.querySelector(".tool-detail");
              if (d) {
                const res = document.createElement("div");
                res.className = "tool-result";
                res.textContent = "→ " + payload.result;
                d.appendChild(res);
              }
            }
          } else if (type === "done") {
            sessionId = payload.session_id || sessionId;
            localStorage.setItem(SKEY, sessionId);
            updateMemBadge(payload.facts || []);
          }
        }
      }

      if (!gotAny) {
        thinking.remove();
        bubble.textContent = "（未能生成回复，请检查 .env 中的模型配置）";
      }
    } catch (e) {
      thinking.remove();
      bubble.textContent = "⚠️ 请求失败：" + e.message;
    } finally {
      thinking.remove();
      finish();
    }
  }

  // ---------- 输入框 ----------
  function autoGrow() {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + "px";
  }
  inputEl.addEventListener("input", autoGrow);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });
  sendBtn.addEventListener("click", send);
  inputEl.focus();
})();
