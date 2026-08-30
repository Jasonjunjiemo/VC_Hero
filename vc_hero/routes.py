"""HTTP 路由：账号、个人信息、简历、会话、面试交互。"""
import functools
import os
import tempfile

from flask import (Blueprint, current_app, jsonify, request, send_from_directory)

from . import config, interview, pdfutil, storage, training

bp = Blueprint("api", __name__, url_prefix="/api")


# ---------------- 鉴权 ----------------

def _client():
    return current_app.extensions["kimi_client"]


def token_from_cookie():
    return request.cookies.get(config.SESSION_COOKIE, "")


def token_user_id(token):
    user = storage.get_token_user(token)
    return user["id"] if user else None


def current_user():
    return storage.get_token_user(token_from_cookie())


def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return jsonify({"error": "未登录"}), 401
        return fn(*args, **kwargs)
    return wrapper


def _bad(msg):
    return jsonify({"error": msg}), 400


# ---------------- 账号 ----------------

@bp.post("/register")
def register():
    username = (request.json.get("username") or "").strip()
    password = request.json.get("password") or ""
    if not username or len(username) > 30:
        return _bad("用户名不能为空且不超过 30 字")
    if not password or len(password) > 100:
        return _bad("密码不能为空")
    if storage.find_user_by_name(username):
        return _bad("用户名已存在")
    user = storage.create_user(username, password)
    return _auth_response(user, "注册成功")


@bp.post("/login")
def login():
    user = storage.verify_user(request.json.get("username") or "",
                               request.json.get("password") or "")
    if not user:
        return jsonify({"error": "用户名或密码错误"}), 401
    return _auth_response(user, "登录成功")


@bp.post("/logout")
def logout():
    token = request.cookies.get(config.SESSION_COOKIE, "")
    storage.delete_token(token)
    resp = jsonify({"ok": True})
    resp.delete_cookie(config.SESSION_COOKIE)
    return resp


def _auth_response(user, msg):
    token = storage.create_token(user["id"])
    resp = jsonify({"ok": True, "msg": msg, "user": _user_view(user)})
    resp.set_cookie(config.SESSION_COOKIE, token,
                    max_age=config.TOKEN_TTL_SECONDS, httponly=True, samesite="Lax")
    return resp


def _user_view(user):
    return {"id": user["id"], "username": user["username"],
            "profile": user["profile"]}


@bp.get("/me")
def me():
    user = current_user()
    if not user:
        return jsonify({"error": "未登录"}), 401
    return jsonify({"user": _user_view(user)})


@bp.put("/profile")
@login_required
def update_profile():
    storage.update_profile(current_user()["id"], request.json or {})
    return jsonify({"ok": True, "user": _user_view(storage.get_user(current_user()["id"]))})


# ---------------- 简历 ----------------

@bp.get("/resumes")
@login_required
def resumes():
    return jsonify({"resumes": storage.list_resumes(current_user()["id"])})


@bp.post("/resumes")
@login_required
def upload_resume():
    user_id = current_user()["id"]
    if len(storage.list_resumes(user_id)) >= config.MAX_RESUMES_PER_USER:
        return _bad(f"最多上传 {config.MAX_RESUMES_PER_USER} 份简历")

    f = request.files.get("file")
    if not f or not f.filename:
        return _bad("请选择文件")
    if not f.filename.lower().endswith(".pdf"):
        return _bad("简历必须是 PDF 文件")
    data = f.read()
    if len(data) > config.RESUME_MAX_MB * 1024 * 1024:
        return _bad(f"简历超过 {config.RESUME_MAX_MB}MB 限制")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    try:
        tmp.write(data)
        tmp.close()
        try:
            text = pdfutil.extract_text(tmp.name)
        except pdfutil.PdfExtractError as e:
            return _bad(str(e))
        meta = storage.save_resume(user_id, f.filename, data, text)
        return jsonify({"ok": True, "resume": meta})
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass


@bp.delete("/resumes/<resume_id>")
@login_required
def remove_resume(resume_id):
    storage.delete_resume(current_user()["id"], resume_id)
    return jsonify({"ok": True})


# ---------------- 训练上下文文件 ----------------

@bp.post("/context-files")
@login_required
def upload_context_file():
    f = request.files.get("file")
    if not f or not f.filename:
        return _bad("请选择文件")
    data = f.read()
    if len(data) > config.RESUME_MAX_MB * 4 * 1024 * 1024:
        return _bad("文件过大（最大 40MB）")
    try:
        text = pdfutil.extract_uploaded_text(f.filename, data)
    except pdfutil.PdfExtractError as e:
        return _bad(str(e))
    return jsonify({"ok": True, "text": text[:30000], "filename": f.filename})


# ---------------- 会话 ----------------

def _session_view(s, detail=False):
    v = {
        "id": s["id"],
        "kind": s.get("kind", "interview"),
        "name": s["name"],
        "resume_id": s.get("resume_id", ""),
        "resume_name": s.get("resume_name", ""),
        "level": s.get("level", ""),
        "cv_target_min": s.get("cv_target_min"),
        "cv_target_max": s.get("cv_target_max"),
        "task_count": s.get("task_count"),
        "time_limit_min": s.get("time_limit_min"),
        "context_type": s.get("context_type", "none"),
        "context_label": s.get("context_label", ""),
        "status": s["status"],
        "created_at": s["created_at"],
        "started_at": s["started_at"],
        "ended_at": s["ended_at"],
        "message_count": len(s["messages"]),
    }
    if s.get("result"):
        v["result"] = s["result"]
    if s.get("results_history"):
        v["results_history"] = s["results_history"]
    if s.get("continuation_mode"):
        v["continuation_mode"] = True
    if detail:
        v["messages"] = s["messages"]
        v["phase"] = s.get("phase")
        v["cv_asked"] = s.get("cv_asked")
        v["task_index"] = s.get("task_index")
        v["task_total"] = len(s.get("tasks", []))
        v["result_boundary"] = s.get("result_boundary")
    return v


@bp.get("/sessions")
@login_required
def sessions():
    kind = request.args.get("kind", "interview")
    if kind not in ("interview", "training"):
        return _bad("kind 不合法")
    return jsonify({"sessions": [_session_view(s) for s in storage.list_sessions(current_user()["id"], kind)]})


def _interview_import_text(s):
    """把一场完整面试会话（对话 + 每一次面试结果）转成训练上下文文本。"""
    lines = [f"面试会话：{s['name']}", ""]
    for m in s["messages"]:
        who = "面试官" if m["role"] == "interviewer" else "候选人"
        lines.append(f"【{who}】{m['content']}")
    history = s.get("results_history", [])
    for i, h in enumerate(history, 1):
        r = h["result"]
        lines += ["", f"【第{i}次面试结果】评级 {r.get('grade', '-')}（总分 {r.get('total', '-')}）",
                  f"【第{i}次反馈】{r.get('feedback', '')}"]
    r = s.get("result")
    if r:
        n = len(history) + 1
        prefix = f"【第{n}次面试结果（最新）】" if history else "【最终评级】"
        lines += ["", f"{prefix}{r.get('grade', '-')}（总分 {r.get('total', '-')}）",
                  f"【最新反馈】{r.get('feedback', '')}"]
    return "\n".join(lines)


@bp.post("/sessions")
@login_required
def create_session():
    user_id = current_user()["id"]
    body = request.json or {}
    kind = body.get("kind", "interview")
    if kind not in ("interview", "training"):
        return _bad("kind 不合法")
    if len(storage.list_sessions(user_id, kind)) >= config.MAX_SESSIONS_PER_USER:
        return _bad(f"最多创建 {config.MAX_SESSIONS_PER_USER} 个会话")

    name = (body.get("name") or "").strip()[:50]
    if not name:
        return _bad("请填写会话名称")

    if kind == "training":
        context_type = body.get("context_type", "none")
        context_text, context_label = "", ""
        if context_type == "text":
            context_text = (body.get("context_text") or "").strip()[:20000]
            context_label = (body.get("context_label") or "导入的材料").strip()[:50]
            if len(context_text) < 10:
                return _bad("导入的材料内容太短")
        elif context_type == "session":
            src = storage.get_session(user_id, body.get("context_session_id") or "")
            if not src or src.get("kind", "interview") != "interview":
                return _bad("请选择要导入的面试会话")
            context_text = _interview_import_text(src)[:20000]
            context_label = "面试记录：" + src["name"]
        elif context_type != "none":
            return _bad("context_type 不合法")

        # 可选：附带已上传的简历作为训练上下文
        resume_names = []
        for rid_ in (body.get("context_resume_ids") or [])[:5]:
            r = next((x for x in storage.list_resumes(user_id) if x["id"] == rid_), None)
            if not r:
                return _bad("勾选的简历不存在")
            text = storage.get_resume_text(user_id, rid_)
            if text:
                block = f"===== 简历：{r['filename']} =====\n{text[:8000]}"
                context_text = (context_text + "\n\n" + block).strip() if context_text else block
                resume_names.append(r["filename"])
        if resume_names:
            if context_type == "none":
                context_type = "text"
            if not context_label:
                context_label = "简历：" + "、".join(resume_names)

        s = storage.create_session(user_id, name, kind="training",
                                   context_type=context_type,
                                   context_text=context_text,
                                   context_label=context_label)
        return jsonify({"ok": True, "session": _session_view(s)})

    # ---- 面试会话 ----
    resume_id = body.get("resume_id") or ""
    level = body.get("level") or "medium"
    task_count = body.get("task_count")
    time_limit_min = body.get("time_limit_min")

    resume = next((r for r in storage.list_resumes(user_id) if r["id"] == resume_id), None)
    if not resume:
        return _bad("请选择一份简历")
    if level not in config.LEVEL_RANGES:
        return _bad("问题数量档位不合法")
    try:
        task_count = int(task_count)
    except (TypeError, ValueError):
        return _bad("任务数量不合法")
    if not (config.TASK_COUNT_MIN <= task_count <= config.TASK_COUNT_MAX):
        return _bad(f"任务数量需在 {config.TASK_COUNT_MIN}-{config.TASK_COUNT_MAX} 之间")
    if time_limit_min in (None, "", 0):
        time_limit_min = None
    else:
        try:
            time_limit_min = int(time_limit_min)
        except (TypeError, ValueError):
            return _bad("时长限制不合法")
        if not (1 <= time_limit_min <= config.TIME_LIMIT_MAX_MIN):
            return _bad(f"时长需在 1-{config.TIME_LIMIT_MAX_MIN} 分钟之间")

    s = storage.create_session(user_id, name, kind="interview", resume_id=resume_id,
                               level=level, task_count=task_count,
                               time_limit_min=time_limit_min)
    s["resume_name"] = resume["filename"]
    s["tasks"] = interview.pick_tasks(task_count)
    storage.save_session(s)
    return jsonify({"ok": True, "session": _session_view(s)})


@bp.get("/sessions/<session_id>")
@login_required
def session_detail(session_id):
    s = storage.get_session(current_user()["id"], session_id)
    if not s:
        return jsonify({"error": "会话不存在"}), 404
    return jsonify({"session": _session_view(s, detail=True)})


@bp.put("/sessions/<session_id>")
@login_required
def rename_session(session_id):
    user_id = current_user()["id"]
    s = storage.get_session(user_id, session_id)
    if not s:
        return jsonify({"error": "会话不存在"}), 404
    name = (request.json.get("name") or "").strip()[:50]
    if not name:
        return _bad("名称不能为空")
    s["name"] = name
    storage.save_session(s)
    return jsonify({"ok": True, "session": _session_view(s)})


@bp.delete("/sessions/<session_id>")
@login_required
def remove_session(session_id):
    storage.delete_session(current_user()["id"], session_id)
    return jsonify({"ok": True})


# ---------------- 面试 / 训练交互 ----------------

def _engine_for(user_id, session_id):
    """按会话 kind 返回对应引擎模块与校验后的会话。"""
    s = storage.get_session(user_id, session_id)
    if not s:
        raise interview.InterviewError("会话不存在")
    if s.get("kind", "interview") == "training":
        return training, s
    return interview, s


@bp.post("/sessions/<session_id>/start")
@login_required
def start_interview(session_id):
    try:
        engine, _ = _engine_for(current_user()["id"], session_id)
        s = engine.start_session(_client(), current_user()["id"], session_id)
        return jsonify({"ok": True, "session": _session_view(s, detail=True)})
    except interview.InterviewError as e:
        return _bad(str(e))


@bp.post("/sessions/<session_id>/answer")
@login_required
def answer(session_id):
    try:
        engine, _ = _engine_for(current_user()["id"], session_id)
        s = engine.answer(_client(), current_user()["id"], session_id,
                          (request.json or {}).get("content"))
        return jsonify({"ok": True, "session": _session_view(s, detail=True)})
    except interview.InterviewError as e:
        return _bad(str(e))


@bp.post("/sessions/<session_id>/continue")
@login_required
def continue_session(session_id):
    try:
        engine, s = _engine_for(current_user()["id"], session_id)
        s = engine.continue_session(_client(), current_user()["id"], session_id)
        return jsonify({"ok": True, "session": _session_view(s, detail=True)})
    except interview.InterviewError as e:
        return _bad(str(e))


@bp.post("/sessions/<session_id>/finish")
@login_required
def finish(session_id):
    try:
        engine, _ = _engine_for(current_user()["id"], session_id)
        s = engine.finish(_client(), current_user()["id"], session_id)
        return jsonify({"ok": True, "session": _session_view(s, detail=True)})
    except interview.InterviewError as e:
        return _bad(str(e))


# ---------------- 前端 ----------------

@bp.get("/health")
def health():
    return jsonify({"ok": True})


def static_view(filename):
    return send_from_directory(config.STATIC_DIR, filename)
