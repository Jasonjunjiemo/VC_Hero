/* VC_Hero 单页应用
 * 视图：landing（网站介绍主页）/ auth / settings（个人信息+简历）/ chat（面试）
 * 会话通过 /session/<id> 路由渲染，从列表进入时在新标签页打开。
 */
(function () {
  "use strict";

  const app = document.getElementById("app");
  const state = {
    user: null,
    resumes: [],
    sessions: [],
    current: null,        // 当前面试会话详情
    view: "landing",      // landing / auth / settings / chat
    busy: false,
    actionError: "",
    timerId: null,
  };

  // ---------- 工具 ----------
  async function api(path, opts = {}) {
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers);
    const r = await fetch("/api" + path, opts);
    let data = {};
    try { data = await r.json(); } catch (e) { /* ignore */ }
    if (!r.ok) throw new Error(data.error || ("请求失败 " + r.status));
    return data;
  }

  const q = (sel) => document.querySelector(sel);
  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const fmtTime = (ts) => ts ? new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false }) : "";

  function fmtCountdown(ms) {
    if (ms < 0) ms = 0;
    const m = Math.floor(ms / 60000), s = Math.floor((ms % 60000) / 1000);
    return m + ":" + String(s).padStart(2, "0");
  }

  function clearTimer() {
    if (state.timerId) { clearInterval(state.timerId); state.timerId = null; }
  }

  function sessionTimeLeft(s) {
    if (!s.time_limit_min || !s.started_at) return null;
    return s.started_at * 1000 + s.time_limit_min * 60000 - Date.now();
  }

  // ---------- 顶栏 ----------
  function topbarHtml(active) {
    const u = state.user;
    return `
      <div class="topbar">
        <div class="logo" id="logo">VC <span>Hero</span></div>
        <div class="spacer"></div>
        <button class="user-btn ${active === "settings" ? "on" : ""}" id="user-btn" title="个人信息设置">
          <span class="user-avatar">${esc((u.username || "?")[0].toUpperCase())}</span>
          <span>${esc(u.username)}</span>
        </button>
        <button class="ghost small" id="logout">退出</button>
      </div>`;
  }

  function bindTopbar(active) {
    q("#logo").addEventListener("click", () => { location.href = "/"; });
    q("#user-btn").addEventListener("click", () => {
      if (active === "settings") return;
      history.pushState({ view: "settings" }, "", "/");
      renderSettings();
    });
    q("#logout").addEventListener("click", async () => {
      await api("/logout", { method: "POST" });
      state.user = null;
      location.href = "/";
    });
  }

  // ---------- 网站介绍主页 ----------
  function landingBodyHtml() {
    const logged = !!state.user;
    const sess = logged ? `
      <div class="card" style="margin-top:18px">
        <div class="spread">
          <h2 class="card-title" style="margin:0">面试会话 <span class="muted">(${state.sessions.length}/10)</span></h2>
          <button id="new-session">新建会话</button>
        </div>
        <div id="session-list" style="margin-top:8px"></div>
      </div>` : "";
    return `
      <div class="page">
        <div class="hero">
          <div class="hero-text">
            <h1>在真正的面试之前，<br>先在这里输一次</h1>
            <p>VC Hero 是一位 AI 虚拟面试官，模拟早期投资机构 Deal Sourcing 团队的真实面试：先深挖你的简历，再把你放进真实的找人、判断、取舍场景，结束后给出 A-E 评级和具体反馈。</p>
            <div class="row" style="margin-top:16px">
              ${logged
                ? `<button id="hero-new">立即开始模拟面试</button>`
                : `<button id="hero-login">登录</button>
                   <button class="ghost" id="hero-register">免费注册</button>`}
            </div>
          </div>
          <img class="hero-img" src="/static/img/hero.svg" alt="AI 面试示意">
        </div>
        <div class="features">
          <div class="feature card">
            <img src="/static/img/feature_cv.svg" alt="">
            <h3>简历深挖问答</h3>
            <p>面试官把你的简历当作待验证的证据，追问个人贡献、方法、数字与失败细节，而不是机械地逐段提问。</p>
          </div>
          <div class="feature card">
            <img src="/static/img/feature_task.svg" alt="">
            <h3>场景化任务考核</h3>
            <p>从 GitHub 找人、经营关键人脉到向合伙人推荐，按真实 Deal Sourcing 工作链条循序渐进，动态加难。</p>
          </div>
          <div class="feature card">
            <img src="/static/img/feature_score.svg" alt="">
            <h3>评级与千字反馈</h3>
            <p>面试结束后按五项职业能力给出 A-E 评级，并指出你的能力链条断在哪里、下一步具体练什么。</p>
          </div>
        </div>
        ${sess}
      </div>`;
  }

  function bindLanding() {
    const hl = q("#hero-login"), hr = q("#hero-register"), hn = q("#hero-new");
    if (hl) hl.addEventListener("click", () => renderAuth("login"));
    if (hr) hr.addEventListener("click", () => renderAuth("register"));
    if (hn) hn.addEventListener("click", () => openSessionModal());
    const ns = q("#new-session");
    if (ns) ns.addEventListener("click", () => openSessionModal());
    renderSessionList();
  }

  async function renderHome() {
    clearTimer();
    state.view = "landing";
    state.current = null;
    state.busy = false;
    if (state.user) {
      const [r2, r3] = await Promise.all([api("/resumes"), api("/sessions")]);
      state.resumes = r2.resumes;
      state.sessions = r3.sessions;
    }
    app.innerHTML = (state.user ? topbarHtml("landing") : "") + landingBodyHtml();
    if (state.user) bindTopbar("landing");
    bindLanding();
  }

  // ---------- 登录 / 注册 ----------
  function renderAuth(mode) {
    clearTimer();
    state.view = "auth";
    app.innerHTML = `
      <div class="auth-wrap">
        <div class="card auth-card">
          <div class="auth-logo">VC <span>Hero</span></div>
          <div class="auth-sub">AI 虚拟面试官 · 早期 VC Deal Sourcing 面试陪练</div>
          <div class="auth-tabs">
            <button class="${mode === "login" ? "on" : ""}" data-tab="login">登录</button>
            <button class="${mode === "register" ? "on" : ""}" data-tab="register">注册</button>
          </div>
          <form id="auth-form">
            <input name="username" placeholder="用户名" autocomplete="username" required>
            <input name="password" type="password" placeholder="密码" autocomplete="current-password" required>
            <button type="submit">${mode === "login" ? "登录" : "创建账户"}</button>
          </form>
          <div id="auth-err"></div>
          <div class="auth-note">无需任何验证，随手创建即可开始练习 · <a href="/" id="auth-back">返回首页</a></div>
        </div>
      </div>`;
    app.querySelectorAll("[data-tab]").forEach(b =>
      b.addEventListener("click", () => renderAuth(b.dataset.tab)));
    q("#auth-back").addEventListener("click", (e) => { e.preventDefault(); location.href = "/"; });
    q("#auth-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      try {
        const data = await api("/" + mode, {
          method: "POST",
          body: JSON.stringify({ username: fd.get("username").trim(), password: fd.get("password") }),
        });
        state.user = data.user;
        location.href = "/";
      } catch (err) {
        q("#auth-err").innerHTML = `<div class="err-banner">${esc(err.message)}</div>`;
      }
    });
  }

  // ---------- 设置页（个人信息 + 简历） ----------
  async function renderSettings() {
    clearTimer();
    state.view = "settings";
    state.current = null;
    const [r1, r2] = await Promise.all([api("/me"), api("/resumes")]);
    state.user = r1.user;
    state.resumes = r2.resumes;
    const p = state.user.profile;

    app.innerHTML = topbarHtml("settings") + `
      <div class="page" style="max-width:820px">
        <div class="card">
          <h2 class="card-title">个人信息</h2>
          <form class="profile-form" id="profile-form">
            <input name="name" placeholder="姓名" value="${esc(p.name)}">
            <input name="org" placeholder="学校 / 公司" value="${esc(p.org)}">
            <input name="email" placeholder="邮箱" value="${esc(p.email)}">
            <input name="phone" placeholder="电话" value="${esc(p.phone)}">
            <textarea class="full" name="bio" placeholder="一句话介绍自己（选填）">${esc(p.bio)}</textarea>
            <div class="full"><button type="submit" class="small">保存</button> <span id="profile-msg" class="muted"></span></div>
          </form>
        </div>
        <div class="card">
          <h2 class="card-title">我的简历 <span class="muted">(${state.resumes.length}/5)</span></h2>
          <div id="resume-list"></div>
          <form id="resume-form" style="margin-top:10px">
            <div class="row">
              <input type="file" name="file" accept="application/pdf" required>
              <button type="submit" class="small" style="flex:none">上传</button>
            </div>
            <div class="hint">仅支持 PDF，单份不超过 10MB</div>
            <div id="resume-err"></div>
          </form>
        </div>
      </div>`;

    bindTopbar("settings");
    q("#profile-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = Object.fromEntries(new FormData(e.target).entries());
      try {
        const d = await api("/profile", { method: "PUT", body: JSON.stringify(body) });
        state.user = d.user;
        q("#profile-msg").textContent = "已保存";
      } catch (err) { q("#profile-msg").textContent = err.message; }
    });
    q("#resume-form").addEventListener("submit", uploadResume);
    renderResumeList();
  }

  function renderResumeList() {
    const box = q("#resume-list");
    if (!box) return;
    if (!state.resumes.length) {
      box.innerHTML = `<div class="empty">还没有简历，先上传一份 PDF 吧</div>`;
      return;
    }
    box.innerHTML = state.resumes.map(r => `
      <div class="res-item">
        <div class="icon">PDF</div>
        <div class="meta">
          <div class="name">${esc(r.filename)}</div>
          <div class="muted">${(r.size / 1048576).toFixed(1)}MB · ${fmtTime(r.created_at)}</div>
        </div>
        <button class="danger" style="flex:none" data-del-resume="${r.id}">删除</button>
      </div>`).join("");
    box.querySelectorAll("[data-del-resume]").forEach(b =>
      b.addEventListener("click", async () => {
        if (!confirm("确定删除这份简历？")) return;
        await api("/resumes/" + b.dataset.delResume, { method: "DELETE" });
        renderSettings();
      }));
  }

  async function uploadResume(e) {
    e.preventDefault();
    const errBox = q("#resume-err");
    errBox.innerHTML = "";
    const f = new FormData(e.target).get("file");
    if (!f) return;
    try {
      const fd = new FormData();
      fd.append("file", f);
      const r = await fetch("/api/resumes", { method: "POST", body: fd });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "上传失败");
      renderSettings();
    } catch (err) {
      errBox.innerHTML = `<div class="err-banner">${esc(err.message)}</div>`;
    }
  }

  // ---------- 会话列表 ----------
  const LEVEL_TEXT = { low: "低", medium: "中", high: "高" };
  const STATUS_TEXT = { created: "未开始", active: "进行中", scored: "已完成" };

  function renderSessionList() {
    const box = q("#session-list");
    if (!box) return;
    if (!state.sessions.length) {
      box.innerHTML = `<div class="empty">还没有会话。新建一个会话，选择简历后即可开始模拟面试。</div>`;
      return;
    }
    box.innerHTML = state.sessions.map(s => `
      <div class="sess-item">
        <div class="meta">
          <div class="name">${esc(s.name)}
            <span class="badge ${s.status}">${STATUS_TEXT[s.status] || s.status}</span>
            ${s.result ? `<span class="badge scored">评级 ${esc(s.result.grade || "-")}</span>` : ""}
          </div>
          <div class="muted">${esc(s.resume_name)} · 问题${LEVEL_TEXT[s.level] || ""}档 · ${s.task_count} 个任务
            ${s.time_limit_min ? " · 限时 " + s.time_limit_min + " 分钟" : ""} · ${fmtTime(s.created_at)}</div>
        </div>
        <button class="ghost small" style="flex:none" data-rename="${s.id}">重命名</button>
        <button class="danger" style="flex:none" data-del-session="${s.id}">删除</button>
        <button class="small" style="flex:none" data-enter="${s.id}" data-newtab="1">
          ${s.status === "scored" ? "查看结果" : s.status === "active" ? "继续面试" : "开始面试"}
        </button>
      </div>`).join("");

    box.querySelectorAll("[data-enter]").forEach(b =>
      b.addEventListener("click", () => openSessionTab(b.dataset.enter)));
    box.querySelectorAll("[data-rename]").forEach(b =>
      b.addEventListener("click", () => renameSession(b.dataset.rename)));
    box.querySelectorAll("[data-del-session]").forEach(b =>
      b.addEventListener("click", async () => {
        if (!confirm("确定删除该会话？对话记录将一并删除。")) return;
        await api("/sessions/" + b.dataset.delSession, { method: "DELETE" });
        renderHome();
      }));
  }

  function openSessionTab(id) {
    window.open("/session/" + id, "_blank");
  }

  async function renameSession(id) {
    const s = state.sessions.find(x => x.id === id);
    const name = prompt("新的会话名称：", s ? s.name : "");
    if (!name || !name.trim()) return;
    await api("/sessions/" + id, { method: "PUT", body: JSON.stringify({ name: name.trim() }) });
    renderHome();
  }

  // ---------- 新建会话弹层 ----------
  function openSessionModal() {
    if (!state.resumes.length) { alert("请先在个人信息设置里上传至少一份简历"); return; }
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `
      <div class="card modal">
        <h2 class="card-title">新建面试会话</h2>
        <form id="session-form">
          <div><label>会话名称</label><input name="name" placeholder="例如：第一次模拟面试" required></div>
          <div><label>选择简历</label>
            <select name="resume_id">
              ${state.resumes.map(r => `<option value="${r.id}">${esc(r.filename)}</option>`).join("")}
            </select>
          </div>
          <div class="row3">
            <div><label>问题数量</label>
              <select name="level">
                <option value="low">低</option>
                <option value="medium" selected>中</option>
                <option value="high">高</option>
              </select>
            </div>
            <div><label>任务数量</label>
              <select name="task_count">
                ${[1, 2, 3, 4, 5].map(n => `<option value="${n}" ${n === 2 ? "selected" : ""}>${n} 个</option>`).join("")}
              </select>
            </div>
            <div><label>时长</label>
              <select name="limit_mode" id="limit-mode">
                <option value="" selected>不限时</option>
                <option value="limit">限时</option>
              </select>
            </div>
          </div>
          <div id="limit-box" style="display:none">
            <label>时长（分钟，1-180）</label>
            <input name="time_limit_min" id="limit-input" type="number" min="1" max="180" value="30">
          </div>
          <div class="row" style="justify-content:flex-end;margin-top:6px">
            <button type="button" class="ghost" id="cancel-modal">取消</button>
            <button type="submit">创建并打开</button>
          </div>
          <div id="session-err"></div>
        </form>
      </div>`;
    document.body.appendChild(mask);
    const modeSel = mask.querySelector("#limit-mode");
    const limitBox = mask.querySelector("#limit-box");
    modeSel.addEventListener("change", () => {
      limitBox.style.display = modeSel.value === "limit" ? "" : "none";
    });
    mask.addEventListener("click", (e) => { if (e.target === mask) mask.remove(); });
    mask.querySelector("#cancel-modal").addEventListener("click", () => mask.remove());
    mask.querySelector("#session-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = Object.fromEntries(new FormData(e.target).entries());
      if (body.limit_mode !== "limit") {
        body.time_limit_min = null;
      }
      delete body.limit_mode;
      try {
        const d = await api("/sessions", { method: "POST", body: JSON.stringify(body) });
        mask.remove();
        // 新标签页立即打开会话界面
        window.open("/session/" + d.session.id, "_blank");
        renderHome();
      } catch (err) {
        mask.querySelector("#session-err").innerHTML = `<div class="err-banner">${esc(err.message)}</div>`;
      }
    });
  }

  // ---------- 面试页 ----------
  async function renderChat(sessionId) {
    clearTimer();
    let s;
    try {
      const d = await api("/sessions/" + sessionId);
      s = d.session;
    } catch (err) {
      alert(err.message);
      location.href = "/";
      return;
    }
    state.view = "chat";
    state.current = s;
    state.busy = false;
    state.actionError = "";

    history.replaceState({ view: "chat" }, "", "/session/" + sessionId);
    app.innerHTML = `
      <div class="topbar">
        <div class="back-btn" id="back">‹ 返回</div>
        <div class="title" style="font-weight:600">${esc(s.name)}</div>
        <div class="spacer"></div>
        <div class="timer" id="timer"></div>
        ${s.status !== "scored" ? `<button class="ghost small" style="flex:none" id="finish-btn">结束面试</button>` : ""}
      </div>
      <div class="chat-page">
        <div class="chat-scroll" id="chat-scroll"></div>
        <div id="chat-foot"></div>
      </div>`;

    q("#back").addEventListener("click", () => { location.href = "/"; });
    const fb = q("#finish-btn");
    if (fb) fb.addEventListener("click", async () => {
      if (s.status === "created") { location.href = "/"; return; }
      if (!confirm("确定结束面试？结束后将给出评级和反馈。")) return;
      await sendAction("/finish", {});
    });

    renderMessages();
    renderChatFoot();

    const tick = () => {
      if (state.view !== "chat" || !state.current) return clearTimer();
      const t = q("#timer");
      if (!t) return clearTimer();
      const left = sessionTimeLeft(state.current);
      if (left == null) { t.textContent = "不限时"; }
      else {
        t.textContent = "剩余 " + fmtCountdown(left);
        t.classList.toggle("warn", left < 5 * 60000);
        if (left <= 0 && state.current.status === "active") {
          clearTimer();
          t.textContent = "时间到";
          sendAction("/finish", {});
        }
      }
    };
    tick();
    state.timerId = setInterval(tick, 1000);
  }

  function renderMessages() {
    const box = q("#chat-scroll");
    if (!box || !state.current) return;
    const s = state.current;
    box.innerHTML = s.messages.map(m => `
      <div class="msg ${m.role === "candidate" ? "me" : "ai"}">
        <div class="avatar">${m.role === "candidate" ? "我" : "VC"}</div>
        <div class="bubble">${esc(m.content)}</div>
      </div>`).join("");
    box.scrollTop = box.scrollHeight;
  }

  function renderChatFoot() {
    const foot = q("#chat-foot");
    if (!foot || !state.current) return;
    const s = state.current;
    if (s.status === "scored") { foot.innerHTML = resultHtml(s.result); return; }
    if (state.busy) {
      foot.innerHTML = `<div class="typing">考官正在思考（回复经过多轮自检，可能需要一两分钟）…</div>`;
      return;
    }
    if (s.status === "created") {
      foot.innerHTML = `
        <div class="chat-input">
          <div style="flex:1;text-align:center" class="muted">准备好后开始面试，考官会基于你的简历提出第一个问题</div>
          <button id="start-btn" style="flex:none">开始面试</button>
        </div>
        <div id="action-err">${state.actionError ? `<div class="err-banner">${esc(state.actionError)}</div>` : ""}`;
      foot.querySelector("#start-btn").addEventListener("click", () => sendAction("/start", {}));
      return;
    }
    // 进行中：轮到考生
    foot.innerHTML = `
      <div class="chat-input">
        <textarea id="answer-input" placeholder="输入你的回答，提交后考官会继续提问…"></textarea>
        <button id="send-btn" style="flex:none">提交回答</button>
      </div>
      <div id="action-err">${state.actionError ? `<div class="err-banner">${esc(state.actionError)}</div>` : ""}`;
    const ta = foot.querySelector("#answer-input");
    const send = () => {
      const v = ta.value.trim();
      if (!v) return;
      sendAction("/answer", { content: v });
    };
    foot.querySelector("#send-btn").addEventListener("click", send);
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send();
    });
    ta.focus();
  }

  async function sendAction(action, body) {
    if (state.busy || !state.current) return;
    state.busy = true;
    state.actionError = "";
    renderChatFoot();
    const sid = state.current.id;
    try {
      const d = await api("/sessions/" + sid + action, {
        method: "POST", body: JSON.stringify(body),
      });
      state.busy = false;
      // 请求期间用户可能已离开会话页：只在仍处于该会话页时渲染
      if (state.view !== "chat" || !state.current || state.current.id !== sid) return;
      state.current = d.session;
      renderMessages();
      renderChatFoot();
    } catch (err) {
      state.busy = false;
      if (state.view !== "chat" || !state.current || state.current.id !== sid) return;
      state.actionError = err.message;
      renderChatFoot();
    }
  }

  // ---------- 结果 ----------
  const DIMS = [
    ["task_understanding", "任务理解与目标拆解"],
    ["signal_identification", "关键信号识别"],
    ["prioritization", "优先级与取舍"],
    ["judgment_update", "新信息判断调整"],
    ["decision_expression", "决策与表达"],
  ];

  function resultHtml(result) {
    if (!result) return "";
    const grade = (result.grade || "-").toUpperCase();
    const scores = result.scores || {};
    const rows = DIMS.map(([k, label]) => {
      const v = Number(scores[k]);
      const pct = isFinite(v) ? Math.max(0, Math.min(100, v)) : 0;
      return `<div class="score-line"><span>${label}</span>
        <div class="bar"><i style="width:${pct}%"></i></div>
        <span>${isFinite(v) ? v : "-"}</span></div>`;
    }).join("");
    return `
      <div class="card result">
        <h2 class="card-title">面试结果</h2>
        <div class="grade-row">
          <div class="grade ${esc(grade)}">${esc(grade)}</div>
          <div>
            <div style="font-size:18px;font-weight:600">${result.total != null ? "总分 " + esc(result.total) : ""}</div>
            <div class="muted">评级 A-E，A 为最高</div>
          </div>
        </div>
        ${rows}
        <div class="feedback">${esc(result.feedback || "")}</div>
      </div>`;
  }

  // ---------- 启动路由 ----------
  (async function init() {
    const m = location.pathname.match(/^\/session\/([a-zA-Z0-9]+)/);
    let user = null;
    try {
      user = (await api("/me")).user;
    } catch (e) { /* 未登录 */ }
    state.user = user;
    if (m && user) {
      renderChat(m[1]);
    } else {
      if (m && !user) alert("请先登录");
      renderHome();
    }
  })();
})();
