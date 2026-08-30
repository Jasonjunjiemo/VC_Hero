"""HTTP 路由：账号、个人信息、简历、会话、面试交互。"""
import functools
import os
import tempfile

from flask import (Blueprint, current_app, jsonify, request, send_from_directory)

from . import config, interview, pdfutil, storage

bp = Blueprint("api", __name__, url_prefix="/api")


# ---------------- 鉴权 ----------------

def _client():
    return current_app.extensions["kimi_client"]


def current_user():
    token = request.cookies.get(config.SESSION_COOKIE, "")
    return storage.get_token_user(token)


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


# ---------------- 会话 ----------------

def _session_view(s, detail=False):
    v = {
        "id": s["id"],
        "name": s["name"],
        "resume_id": s["resume_id"],
        "resume_name": s["resume_name"],
        "level": s["level"],
        "cv_total": s["cv_total"],
        "task_count": s["task_count"],
        "time_limit_min": s["time_limit_min"],
        "status": s["status"],
        "created_at": s["created_at"],
        "started_at": s["started_at"],
        "ended_at": s["ended_at"],
        "message_count": len(s["messages"]),
    }
    if s.get("result"):
        v["result"] = s["result"]
    if detail:
        v["messages"] = s["messages"]
        v["phase"] = s["phase"]
        v["cv_asked"] = s["cv_asked"]
        v["task_index"] = s["task_index"]
        v["task_total"] = len(s["tasks"])
    return v


@bp.get("/sessions")
@login_required
def sessions():
    return jsonify({"sessions": [_session_view(s) for s in storage.list_sessions(current_user()["id"])]})


@bp.post("/sessions")
@login_required
def create_session():
    user_id = current_user()["id"]
    if len(storage.list_sessions(user_id)) >= config.MAX_SESSIONS_PER_USER:
        return _bad(f"最多创建 {config.MAX_SESSIONS_PER_USER} 个会话")

    body = request.json or {}
    name = (body.get("name") or "").strip()[:50]
    resume_id = body.get("resume_id") or ""
    level = body.get("level") or "medium"
    task_count = body.get("task_count")
    time_limit_min = body.get("time_limit_min")

    if not name:
        return _bad("请填写会话名称")
    resume = next((r for r in storage.list_resumes(user_id) if r["id"] == resume_id), None)
    if not resume:
        return _bad("请选择一份简历")
    if level not in config.QUESTION_LEVELS:
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

    s = storage.create_session(user_id, name, resume_id, level, task_count, time_limit_min)
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


# ---------------- 面试 ----------------

@bp.post("/sessions/<session_id>/start")
@login_required
def start_interview(session_id):
    try:
        s = interview.start_session(_client(), current_user()["id"], session_id)
        return jsonify({"ok": True, "session": _session_view(s, detail=True)})
    except interview.InterviewError as e:
        return _bad(str(e))


@bp.post("/sessions/<session_id>/answer")
@login_required
def answer(session_id):
    try:
        s = interview.answer(_client(), current_user()["id"], session_id,
                             (request.json or {}).get("content"))
        return jsonify({"ok": True, "session": _session_view(s, detail=True)})
    except interview.InterviewError as e:
        return _bad(str(e))


@bp.post("/sessions/<session_id>/finish")
@login_required
def finish(session_id):
    try:
        s = interview.finish(_client(), current_user()["id"], session_id)
        return jsonify({"ok": True, "session": _session_view(s, detail=True)})
    except interview.InterviewError as e:
        return _bad(str(e))


# ---------------- 前端 ----------------

@bp.get("/health")
def health():
    return jsonify({"ok": True})


def static_view(filename):
    return send_from_directory(config.STATIC_DIR, filename)
