/* VC_Hero 单页应用
 * 视图：landing（网站介绍主页）/ auth / settings（个人信息+简历）/ chat（面试）
 * 会话通过 /session/<id> 路由渲染，从列表进入时在新标签页打开。
 * 聊天交互：Enter 发送、Ctrl+Enter 换行；发送后立即上屏并显示考官"思考中"气泡。
 */
(function () {
  "use strict";

  const app = document.getElementById("app");
  const state = {
    user: null,
    resumes: [],
    sessions: [],           // 面试会话
    trainingSessions: [],   // 学习会话
    tab: "interview",       // 主页当前 tab：interview / training
    current: null,        // 当前面试会话详情
    view: "landing",      // landing / auth / settings / chat
    busy: false,
    actionError: "",
    draft: "",
    atBottom: true,
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
        <div class="logo" id="logo"><span class="logo-mark">VC</span><span class="logo-text">Hero</span></div>
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
      renderSettings();
    });
    q("#logout").addEventListener("click", async () => {
      if (!confirm("确定要退出登录吗？")) return;
      await api("/logout", { method: "POST" });
      state.user = null;
      location.href = "/";
    });
  }

  // 未登录时的简易顶栏（右上角登录/注册）
  function navTopbarHtml() {
    return `
      <div class="topbar">
        <div class="logo"><span class="logo-mark">VC</span><span class="logo-text">Hero</span></div>
        <div class="spacer"></div>
        <button class="ghost small" id="nav-login">登录</button>
        <button class="small" id="nav-register">注册</button>
      </div>`;
  }

  // ---------- 网站介绍主页（双 tab） ----------
  const LANDING_TABS = {
    interview: {
      eyebrow: "AI 面试陪练 · 早期 VC Deal Sourcing",
      title: "在真正的面试之前，<br>先在这里输一次",
      desc: "VC Hero 是一位 AI 虚拟面试官，模拟早期投资机构 Deal Sourcing 团队的真实面试：先深挖你的简历，再把你放进真实的找人、判断、取舍场景，结束后给出 A-E 评级和具体反馈。",
      btn: { id: "hero-new", text: "立即开始模拟面试" },
      features: [
        ["feature_cv.svg", "简历深挖问答", "面试官把你的简历当作待验证的证据，追问个人贡献、方法、数字与失败细节，而不是机械地逐段提问。"],
        ["feature_task.svg", "场景化任务考核", "从 GitHub 找人、经营关键人脉到向合伙人推荐，按真实 Deal Sourcing 工作链条循序渐进，动态加难。"],
        ["feature_score.svg", "评级与千字反馈", "面试结束后按五项职业能力给出 A-E 评级，并指出你的能力链条断在哪里、下一步具体练什么。"],
      ],
    },
    training: {
      eyebrow: "Deal Sourcing 工作场景训练",
      title: "在真正面试之前，<br>先练成行业老炮",
      desc: "AI 训练官把你放进真实的 Deal Sourcing 工作场景：你先给出自己的做法，它逐次点评、纠正、讲解正确打法，并带你进入更难的场景。可以从空白开始，也可以导入过往面试记录，针对弱点专项训练。",
      btn: { id: "hero-train", text: "立即开始模拟训练" },
      features: [
        ["feature_task.svg", "真实工作场景", "GitHub 找人、搞定关键节点、第一次 founder 对话、pipeline 取舍——全部取自真实工作链条。"],
        ["feature_score.svg", "逐次点评讲解", "每次作答后得到直接、具体的纠正：哪里错、为什么错、正确的做法是什么，然后立刻进入下一步。"],
        ["feature_cv.svg", "上下文导入", "空白开始，或粘贴材料、上传文件、导入历史面试记录（含评级与反馈），定制你的训练重点。"],
      ],
    },
  };

  function tabContentHtml() {
    const t = LANDING_TABS[state.tab];
    const logged = !!state.user;
    const isTrain = state.tab === "training";
    const listId = isTrain ? "training-session-list" : "session-list";
    const newId = isTrain ? "new-training" : "new-session";
    const panelTitle = isTrain ? "学习会话" : "面试会话";
    const list = isTrain ? state.trainingSessions : state.sessions;
    const sess = logged ? `
      <div class="card section-card">
        <div class="spread">
          <h2 class="card-title" style="margin:0">${panelTitle} <span class="muted">(${list.length}/10)</span></h2>
          <button id="${newId}">新建${isTrain ? "学习" : "面试"}会话</button>
        </div>
        <div id="${listId}" style="margin-top:8px"></div>
      </div>` : "";
    return `
      <div class="tab-content">
        <div class="hero ${isTrain ? "training" : ""}">
          <div class="hero-text">
            <div class="hero-eyebrow">${t.eyebrow}</div>
            <h1>${t.title}</h1>
            <p>${t.desc}</p>
            <div class="row" style="margin-top:20px">
              ${logged
                ? `<button id="${t.btn.id}">${t.btn.text}</button>`
                : `<button id="hero-login">登录</button>
                   <button class="ink" id="hero-register">免费注册</button>`}
            </div>
          </div>
          <div class="hero-art"><img src="/static/img/hero.svg" alt="AI 面试示意"></div>
        </div>
        ${sess}
        <div class="features">
          ${t.features.map(([img, h3, p]) => `
            <div class="feature card">
              <img src="/static/img/${img}" alt="">
              <h3>${h3}</h3>
              <p>${p}</p>
            </div>`).join("")}
        </div>
      </div>`;
  }

  async function loadSessions() {
    const [r2, r3, r4] = await Promise.all([
      api("/resumes"), api("/sessions?kind=interview"), api("/sessions?kind=training"),
    ]);
    state.resumes = r2.resumes;
    state.sessions = r3.sessions;
    state.trainingSessions = r4.sessions;
  }

  function landingShellHtml() {
    return `
      ${state.user ? topbarHtml("landing") : navTopbarHtml()}
      <div class="page">
        <div class="tab-bar">
          <div class="tab-seg">
            <button class="seg-tab ${state.tab === "interview" ? "on" : ""}" data-ltab="interview">AI 面试官</button>
            <button class="seg-tab ${state.tab === "training" ? "on" : ""}" data-ltab="training">AI 训练官</button>
          </div>
        </div>
        <div id="tab-host"></div>
      </div>`;
  }

  // 绑定 hero 按钮与两个会话面板（tab 内容区每次切换后重新绑定）
  function bindTabContent() {
    q("#hero-login")?.addEventListener("click", () => renderAuth("login"));
    q("#hero-register")?.addEventListener("click", () => renderAuth("register"));
    q("#hero-new")?.addEventListener("click", () => openInterviewModal());
    q("#hero-train")?.addEventListener("click", () => openTrainingModal());
    q("#new-session")?.addEventListener("click", () => openInterviewModal());
    q("#new-training")?.addEventListener("click", () => openTrainingModal());
    renderSessionList();
    renderTrainingSessionList();
  }

  const wait = (ms) => new Promise(r => setTimeout(r, ms));

  // tab 切换：整页滑出再滑入，顶栏与切换器保持不动（无闪烁）
  async function switchTab(target) {
    if (state.tab === target) return;
    const host = q("#tab-host");
    const goingRight = target === "training";
    if (state.user) {
      host.classList.add(goingRight ? "slide-out-l" : "slide-out-r");
      try { await loadSessions(); } catch (e) { /* 列表刷新失败不阻塞切换 */ }
      await wait(240);
    }
    state.tab = target;
    app.querySelectorAll(".seg-tab").forEach(b =>
      b.classList.toggle("on", b.dataset.ltab === target));
    if (host) {
      host.className = "";
      host.innerHTML = tabContentHtml();
      if (state.user) host.classList.add(goingRight ? "slide-in-r" : "slide-in-l");
      bindTabContent();
      if (state.user) setTimeout(() => host.classList.remove("slide-in-l", "slide-in-r"), 340);
    }
  }

  function bindLanding() {
    app.querySelectorAll("[data-ltab]").forEach(b =>
      b.addEventListener("click", () => switchTab(b.dataset.ltab)));
    bindTabContent();
  }

  async function renderHome() {
    clearTimer();
    state.view = "landing";
    state.current = null;
    state.busy = false;
    if (state.user) {
      try { await loadSessions(); } catch (e) { /* 未加载出列表也可先渲染 */ }
    }
    app.innerHTML = landingShellHtml();
    q("#tab-host").innerHTML = tabContentHtml();
    if (state.user) bindTopbar("landing");
    else {
      q("#nav-login").addEventListener("click", () => renderAuth("login"));
      q("#nav-register").addEventListener("click", () => renderAuth("register"));
    }
    bindLanding();
  }
  // ---------- 登录 / 注册 ----------
  function renderAuth(mode) {
    clearTimer();
    state.view = "auth";
    app.innerHTML = `
      <div class="auth-wrap">
        <div class="card auth-card">
          <div class="auth-logo"><span class="logo-mark">VC</span> Hero</div>
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
        <div class="page-head">
          <button class="small" id="settings-back">‹ 返回主页</button>
          <h1 class="page-title">个人信息设置</h1>
        </div>
        <div class="card">
          <h2 class="card-title">基本信息</h2>
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
              <label class="plus-btn" title="选择 PDF 简历">
                <input type="file" id="resume-file" accept="application/pdf">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
                     stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
              </label>
              <span class="file-name" id="resume-file-name">选择文件后立即上传</span>
            </div>
            <div class="hint">仅支持 PDF，单份不超过 10MB，最多 5 份</div>
            <div id="resume-err"></div>
          </form>
        </div>
        <div style="text-align:center;padding-bottom:6px">
          <button class="ghost" id="settings-back2">‹ 返回主页</button>
        </div>
      </div>`;

    bindTopbar("settings");
    q("#settings-back").addEventListener("click", () => { location.href = "/"; });
    q("#settings-back2").addEventListener("click", () => { location.href = "/"; });
    q("#profile-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = Object.fromEntries(new FormData(e.target).entries());
      try {
        const d = await api("/profile", { method: "PUT", body: JSON.stringify(body) });
        state.user = d.user;
        q("#profile-msg").textContent = "已保存";
      } catch (err) { q("#profile-msg").textContent = err.message; }
    });
    q("#resume-file").addEventListener("change", uploadResume);
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

  // 选择文件后立即上传
  async function uploadResume(e) {
    const errBox = q("#resume-err");
    errBox.innerHTML = "";
    const nameEl = q("#resume-file-name");
    const f = e.target.files[0];
    if (!f) return;
    if (nameEl) nameEl.textContent = `上传中：${f.name}…`;
    try {
      const fd = new FormData();
      fd.append("file", f);
      const r = await fetch("/api/resumes", { method: "POST", body: fd });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "上传失败");
      renderSettings();
    } catch (err) {
      if (nameEl) nameEl.textContent = "选择文件后立即上传";
      e.target.value = "";
      errBox.innerHTML = `<div class="err-banner">${esc(err.message)}</div>`;
    }
  }

  // ---------- 会话列表 ----------
  const LEVEL_TEXT = { low: "低", medium: "中", high: "高" };
  const STATUS_TEXT = { created: "未开始", active: "进行中", scored: "已完成" };

  function sessionRowHtml(s, isTrain) {
    const meta = isTrain
      ? `${s.context_type === "none" ? "空白开始" : esc(s.context_label || "导入上下文")} · ${s.message_count} 条对话 · ${fmtTime(s.created_at)}`
      : `${esc(s.resume_name)} · 问题${LEVEL_TEXT[s.level] || ""}档 · ${s.task_count} 个任务
         ${s.time_limit_min ? " · 限时 " + s.time_limit_min + " 分钟" : ""} · ${fmtTime(s.created_at)}`;
    return `
      <div class="sess-item">
        <div class="meta">
          <div class="name">${esc(s.name)}
            <span class="badge ${s.status}">${STATUS_TEXT[s.status] || s.status}</span>
            ${s.result && !isTrain ? `<span class="badge scored">评级 ${esc(s.result.grade || "-")}</span>` : ""}
          </div>
          <div class="muted">${meta}</div>
        </div>
        <button class="ghost small" style="flex:none" data-rename="${s.id}">重命名</button>
        <button class="danger" style="flex:none" data-del-session="${s.id}">删除</button>
        <button class="small" style="flex:none" data-enter="${s.id}">
          ${s.status === "scored" ? (isTrain ? "查看总结" : "查看结果") : s.status === "active" ? (isTrain ? "继续训练" : "继续面试") : (isTrain ? "开始训练" : "开始面试")}
        </button>
      </div>`;
  }

  function bindSessionList(box, list, isTrain) {
    box.querySelectorAll("[data-enter]").forEach(b =>
      b.addEventListener("click", () => window.open("/session/" + b.dataset.enter, "_blank")));
    box.querySelectorAll("[data-rename]").forEach(b =>
      b.addEventListener("click", () => startInlineRename(b.closest(".sess-item"),
                                                           b.dataset.rename, list)));
    box.querySelectorAll("[data-del-session]").forEach(b =>
      b.addEventListener("click", async () => {
        if (!confirm("确定删除该会话？记录将一并删除。")) return;
        await api("/sessions/" + b.dataset.delSession, { method: "DELETE" });
        renderHome();
      }));
  }

  function renderSessionList() {
    const box = q("#session-list");
    if (!box) return;
    if (!state.sessions.length) {
      box.innerHTML = `<div class="empty">还没有会话。新建一个会话，选择简历后即可开始模拟面试。</div>`;
      return;
    }
    box.innerHTML = state.sessions.map(s => sessionRowHtml(s, false)).join("");
    bindSessionList(box, state.sessions, false);
  }

  function renderTrainingSessionList() {
    const box = q("#training-session-list");
    if (!box) return;
    if (!state.trainingSessions.length) {
      box.innerHTML = `<div class="empty">还没有学习会话。新建一个学习会话，从空白或导入上下文开始训练。</div>`;
      return;
    }
    box.innerHTML = state.trainingSessions.map(s => sessionRowHtml(s, true)).join("");
    bindSessionList(box, state.trainingSessions, true);
  }

  // 在会话名位置直接改名（Enter 保存，Esc 取消，失焦保存）
  function startInlineRename(row, id, list) {
    const s = list.find(x => x.id === id);
    const nameEl = row.querySelector(".name");
    if (!s || !nameEl) return;
    const input = document.createElement("input");
    input.className = "rename-input";
    input.value = s.name;
    nameEl.replaceWith(input);
    input.focus();
    input.select();
    let done = false;
    const commit = async (saveIt) => {
      if (done) return;
      done = true;
      if (saveIt) {
        const v = input.value.trim();
        if (v && v !== s.name) {
          try {
            await api("/sessions/" + id, { method: "PUT", body: JSON.stringify({ name: v }) });
          } catch (e) { /* 保存失败则回滚原显示 */ }
        }
      }
      renderHome();
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); commit(true); }
      else if (e.key === "Escape") commit(false);
    });
    input.addEventListener("blur", () => commit(true));
  }

  // ---------- 新建面试会话弹层 ----------
  function openInterviewModal() {
    if (!state.resumes.length) { openNoResumeModal(); return; }
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
      body.kind = "interview";
      try {
        const d = await api("/sessions", { method: "POST", body: JSON.stringify(body) });
        mask.remove();
        window.open("/session/" + d.session.id, "_blank");
        renderHome();
      } catch (err) {
        mask.querySelector("#session-err").innerHTML = `<div class="err-banner">${esc(err.message)}</div>`;
      }
    });
  }

  // 没有简历时的引导弹窗：一键去个人信息页上传
  function openNoResumeModal() {
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `
      <div class="card modal" style="text-align:center">
        <h2 class="card-title">还没有简历</h2>
        <p class="muted" style="margin-bottom:20px">创建面试会话需要先上传一份 PDF 简历，<br>去个人信息设置里上传吧。</p>
        <div class="row" style="justify-content:center">
          <button class="ghost" id="no-resume-cancel">取消</button>
          <button id="no-resume-go">去上传简历</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    mask.addEventListener("click", (e) => { if (e.target === mask) mask.remove(); });
    mask.querySelector("#no-resume-cancel").addEventListener("click", () => mask.remove());
    mask.querySelector("#no-resume-go").addEventListener("click", () => {
      mask.remove();
      renderSettings();
    });
  }

  // ---------- 新建学习会话弹层（训练官） ----------
  function openTrainingModal() {
    const interviewOpts = state.sessions.map(s =>
      `<option value="${s.id}">${esc(s.name)}（${STATUS_TEXT[s.status] || s.status}）</option>`).join("");
    const sessionOpts = interviewOpts
      || `<option value="">暂无面试会话（先去完成一场模拟面试）</option>`;
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `
      <div class="card modal">
        <h2 class="card-title">新建学习会话</h2>
        <form id="training-form">
          <div><label>会话名称</label><input name="name" placeholder="例如： sourcing 基础训练" required></div>
          <div>
            <label>上下文来源</label>
            <div class="radio-row">
              <label class="radio"><input type="radio" name="context_type" value="none" checked> 空白开始（无记忆）</label>
              <label class="radio"><input type="radio" name="context_type" value="import"> 导入预设上下文</label>
            </div>
          </div>
          <div id="context-box" style="display:none">
            <div class="radio-row">
              <label class="radio"><input type="radio" name="ctx_method" value="paste" checked> 粘贴文本</label>
              <label class="radio"><input type="radio" name="ctx_method" value="file"> 上传文件</label>
              <label class="radio"><input type="radio" name="ctx_method" value="session"> 从面试会话导入</label>
            </div>
            <div id="ctx-paste">
              <textarea name="context_text" placeholder="粘贴任何背景材料：简历片段、过往面试复盘、目标说明……"></textarea>
            </div>
            <div id="ctx-file" style="display:none">
              <div class="row">
                <label class="plus-btn" title="选择文件">
                  <input type="file" id="ctx-file-input" accept=".pdf,.txt,.md,.docx">
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
                       stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
                </label>
                <span class="file-name" id="ctx-file-status">支持 PDF / TXT / MD / DOCX</span>
              </div>
            </div>
            <div id="ctx-session" style="display:none">
              <select id="ctx-session-select">
                <option value="">选择要导入的面试会话（含对话、评级与反馈）</option>
                ${sessionOpts}
              </select>
            </div>
          </div>
          <div class="row" style="justify-content:flex-end;margin-top:6px">
            <button type="button" class="ghost" id="cancel-modal">取消</button>
            <button type="submit">创建并打开</button>
          </div>
          <div id="training-err"></div>
        </form>
      </div>`;
    document.body.appendChild(mask);

    const form = mask.querySelector("#training-form");
    const contextBox = mask.querySelector("#context-box");
    const fileStatus = mask.querySelector("#ctx-file-status");
    let uploadedText = "", uploadedName = "";

    form.querySelectorAll('input[name="context_type"]').forEach(r =>
      r.addEventListener("change", () => {
        contextBox.style.display = form.context_type.value === "import" ? "" : "none";
      }));
    form.querySelectorAll('input[name="ctx_method"]').forEach(r =>
      r.addEventListener("change", () => {
        const m = form.ctx_method.value;
        mask.querySelector("#ctx-paste").style.display = m === "paste" ? "" : "none";
        mask.querySelector("#ctx-file").style.display = m === "file" ? "" : "none";
        mask.querySelector("#ctx-session").style.display = m === "session" ? "" : "none";
      }));
    mask.querySelector("#ctx-file-input").addEventListener("change", async (e) => {
      const f = e.target.files[0];
      if (!f) return;
      fileStatus.textContent = "解析中…";
      uploadedText = "";
      try {
        const fd = new FormData();
        fd.append("file", f);
        const r = await fetch("/api/context-files", { method: "POST", body: fd });
        const d = await r.json();
        if (!r.ok) throw new Error(d.error || "解析失败");
        uploadedText = d.text;
        uploadedName = d.filename;
        fileStatus.textContent = `已解析「${d.filename}」（${d.text.length} 字）`;
      } catch (err) {
        fileStatus.textContent = err.message;
      }
    });

    mask.addEventListener("click", (e) => { if (e.target === mask) mask.remove(); });
    mask.querySelector("#cancel-modal").addEventListener("click", () => mask.remove());
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errBox = mask.querySelector("#training-err");
      errBox.innerHTML = "";
      const body = { kind: "training", name: form.name.value.trim() };
      if (form.context_type.value === "import") {
        const m = form.ctx_method.value;
        if (m === "paste") {
          const text = form.context_text.value.trim();
          if (text.length < 10) { errBox.innerHTML = `<div class="err-banner">请粘贴至少 10 个字的材料</div>`; return; }
          body.context_type = "text";
          body.context_text = text;
          body.context_label = "粘贴文本";
        } else if (m === "file") {
          if (!uploadedText) { errBox.innerHTML = `<div class="err-banner">请先选择并解析文件</div>`; return; }
          body.context_type = "text";
          body.context_text = uploadedText;
          body.context_label = uploadedName;
        } else {
          const sid = mask.querySelector("#ctx-session-select").value;
          if (!sid) { errBox.innerHTML = `<div class="err-banner">请选择要导入的面试会话</div>`; return; }
          body.context_type = "session";
          body.context_session_id = sid;
        }
      } else {
        body.context_type = "none";
      }
      try {
        const d = await api("/sessions", { method: "POST", body: JSON.stringify(body) });
        mask.remove();
        window.open("/session/" + d.session.id, "_blank");
        renderHome();
      } catch (err) {
        errBox.innerHTML = `<div class="err-banner">${esc(err.message)}</div>`;
      }
    });
  }

  // ---------- 面试页 ----------
  async function renderChat(sessionId) {
    clearTimer();
    state.view = "chat";
    state.busy = false;
    state.actionError = "";
    history.replaceState(null, "", "/session/" + sessionId);

    // 先渲染页面骨架：顶栏与容器立即出现，不再有白屏等待
    app.innerHTML = `
      <div class="topbar">
        <div class="back-btn" id="back">‹ 返回</div>
        <div class="title chat-title" id="chat-title"></div>
        <div class="spacer"></div>
        <div class="timer" id="timer"></div>
      </div>
      <div class="chat-body" id="chat-body">
        <div class="chat-scroll" id="chat-scroll"></div>
        <div id="chat-foot"><div class="boot-loading" style="padding:30px 0">加载会话中…</div></div>
      </div>`;
    q("#back").addEventListener("click", () => { location.href = "/"; });

    let s;
    try {
      const d = await api("/sessions/" + sessionId);
      s = d.session;
    } catch (err) {
      alert(err.message);
      location.href = "/";
      return;
    }
    state.current = s;
    const isTrain = s.kind === "training";

    q("#chat-title").innerHTML = `${esc(s.name)}${isTrain ? '<span class="badge active">训练</span>' : ""}`;
    if (s.status !== "scored") {
      q(".topbar").insertAdjacentHTML("beforeend",
        `<button class="ghost small" style="flex:none" id="finish-btn">${isTrain ? "结束训练" : "结束面试"}</button>`);
      q("#finish-btn").addEventListener("click", async () => {
        if (s.status === "created") { location.href = "/"; return; }
        if (!confirm(isTrain ? "确定结束训练？将生成训练总结。" : "确定结束面试？结束后将给出评级和反馈。")) return;
        await sendAction("/finish", {});
      });
    }

    renderMessages();
    renderChatFoot();

    // 滚动钉底：只有本来就停在底部附近时，新消息才自动滚到底
    state.atBottom = true;
    const scrollBox = q("#chat-scroll");
    if (scrollBox) {
      scrollBox.addEventListener("scroll", () => {
        state.atBottom = scrollBox.scrollHeight - scrollBox.scrollTop - scrollBox.clientHeight < 90;
      });
    }

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
    const stick = state.atBottom;
    box.innerHTML = s.messages.map(m => `
      <div class="msg ${m.role === "candidate" ? "me" : "ai"}">
        <div class="avatar">${m.role === "candidate" ? "我" : "VC"}</div>
        <div class="bubble">${esc(m.content)}</div>
      </div>`).join("");
    if (state.busy) appendThinking(box);
    if (stick) box.scrollTop = box.scrollHeight;
  }

  function appendThinking(box) {
    box.insertAdjacentHTML("beforeend", `
      <div class="msg ai" id="thinking-msg">
        <div class="avatar">VC</div>
        <div class="bubble"><span class="dots"><i></i><i></i><i></i></span></div>
      </div>`);
  }

  function renderChatFoot() {
    const foot = q("#chat-foot");
    if (!foot || !state.current) return;
    const s = state.current;
    const body = q("#chat-body");
    const isTrain = s.kind === "training";
    if (s.status === "created") {
      if (body) body.classList.add("starting");
    } else if (body) {
      body.classList.remove("starting");
    }
    if (s.status === "scored") {
      foot.innerHTML = "";
      q("#chat-body").classList.add("ended");
      const box = q("#chat-scroll");
      if (box && !box.querySelector(".result")) {
        box.insertAdjacentHTML("beforeend",
          isTrain ? trainingResultHtml(s.result) : resultHtml(s.result));
      }
      return;
    }
    if (s.status === "created") {
      if (state.busy) {
        // 已开始：隐藏开始卡片，对话界面全屏，思考气泡在消息流中
        foot.innerHTML = "";
        return;
      }
      // 考试开始页：信息 + 居中显眼的开始按钮
      const chips = isTrain
        ? `<span class="chip">${esc(s.context_label || "空白开始")}</span>
           <span class="chip">自由回合 · 无题数限制</span>
           <span class="chip">不限时</span>`
        : `<span class="chip">${esc(s.resume_name)}</span>
           <span class="chip">问题约 ${s.cv_target_min}-${s.cv_target_max} 题</span>
           <span class="chip">${s.task_count} 个场景任务</span>
           <span class="chip">${s.time_limit_min ? "限时 " + s.time_limit_min + " 分钟" : "不限时"}</span>`;
      const rules = isTrain
        ? `<li>训练官把你放进真实 Deal Sourcing 工作场景，你先给出自己的做法</li>
           <li>每次作答后，训练官会点评对错、讲解正确打法，再推进到下一步</li>
           <li>可以先导入过往面试记录，针对暴露的弱点专项训练</li>
           <li>随时点击右上角"结束训练"生成训练总结</li>`
        : `<li>面试分两部分：先围绕你的简历深挖问答，再进入真实 Deal Sourcing 场景任务</li>
           <li>一问一答：考官提问后你作答一次，考官再继续</li>
           <li>过程中考官不会评价你的回答，反馈在结束后统一给出</li>
           <li>面试结束或到时后，考官会给出 A-E 评级与具体反馈</li>`;
      foot.innerHTML = `
        <div class="start-wrap">
          <div class="card start-card">
            <div class="start-eyebrow">${isTrain ? "场景训练" : "模拟面试"}</div>
            <h2>${esc(s.name)}</h2>
            <div class="chips">${chips}</div>
            <ul class="start-rules">${rules}</ul>
            <button id="start-btn" class="big-btn">${isTrain ? "开始训练" : "开始面试"}</button>
            <div id="action-err">${state.actionError ? `<div class="err-banner">${esc(state.actionError)}</div>` : ""}</div>
          </div>
        </div>`;
      const btn = foot.querySelector("#start-btn");
      if (btn) btn.addEventListener("click", () => sendAction("/start", {}));
      return;
    }
    // 进行中：轮到考生。考官思考时输入框保持可编辑，仅拦截发送并提示。
    foot.innerHTML = `
      <div class="composer" id="composer">
        <textarea id="answer-input" rows="2" placeholder="输入你的回答…">${esc(state.draft || "")}</textarea>
        <div class="composer-foot">
          <span class="composer-hint">Enter 发送 · Ctrl+Enter 换行</span>
          <button id="send-btn" class="send-circle" title="发送" aria-label="发送">
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
                 stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
          </button>
        </div>
      </div>
      <div id="action-err">${state.actionError ? `<div class="err-banner">${esc(state.actionError)}</div>` : ""}</div>`;
    const ta = foot.querySelector("#answer-input");
    const send = () => {
      if (state.busy) { showToast("考官正在思考，请稍候再发送"); return; }
      const v = ta.value.trim();
      if (!v) return;
      state.draft = "";
      state.atBottom = true;
      sendAction("/answer", { content: v }, { optimistic: v });
    };
    foot.querySelector("#send-btn").addEventListener("click", send);
    ta.addEventListener("keydown", (e) => {
      // Enter 发送；Ctrl/Cmd/Shift+Enter 换行
      if (e.key === "Enter" && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
    ta.addEventListener("input", () => { state.draft = ta.value; });
    ta.focus();
  }

  // 发送受限提示：发送按钮上方的小气泡，几秒自动淡出
  function showToast(msg) {
    const host = q(".composer-foot");
    if (!host) return;
    const old = q(".mini-toast");
    if (old) old.remove();
    const t = document.createElement("div");
    t.className = "mini-toast";
    t.textContent = msg;
    host.appendChild(t);
    setTimeout(() => {
      t.classList.add("fade");
      setTimeout(() => t.remove(), 550);
    }, 2000);
  }

  async function sendAction(action, body, opts) {
    opts = opts || {};
    if (state.busy || !state.current) return;
    const sid = state.current.id;
    state.busy = true;
    state.actionError = "";
    if (opts.optimistic) {
      state.current.messages.push({ role: "candidate", content: opts.optimistic,
                                    ts: Date.now() / 1000 });
    }
    renderMessages();
    renderChatFoot();
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
      if (opts.optimistic) state.current.messages.pop();
      state.actionError = err.message;
      renderMessages();
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
        <span class="score-num">${isFinite(v) ? v : "-"}</span></div>`;
    }).join("");
    return `
      <div class="result card">
        <div class="result-head">
          <div class="grade-ring grade-${esc(grade)}"><span>${esc(grade)}</span></div>
          <div>
            <div class="result-title">面试结果</div>
            <div class="result-sub">${result.total != null ? "总分 " + esc(result.total) + " · " : ""}评级 A-E，A 为最高</div>
          </div>
        </div>
        <div class="score-board">${rows}</div>
        <div class="feedback-text">${esc(result.feedback || "")}</div>
      </div>`;
  }

  function trainingResultHtml(result) {
    if (!result) return "";
    return `
      <div class="result card">
        <div class="result-head">
          <div>
            <div class="result-title">训练总结</div>
            <div class="result-sub">来自 AI 训练官 · 可导入新的学习会话继续针对性训练</div>
          </div>
        </div>
        <div class="feedback-text">${esc(result.summary || "")}</div>
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
