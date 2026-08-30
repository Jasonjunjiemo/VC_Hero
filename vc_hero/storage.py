"""基于本地文件系统的数据存储：用户、登录令牌、简历、会话。"""
import hashlib
import json
import os
import secrets
import time
import uuid

from . import config


def _ensure_dirs():
    for d in ("tokens", "users"):
        os.makedirs(os.path.join(config.DATA_DIR, d), exist_ok=True)


def new_id():
    return uuid.uuid4().hex[:12]


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ---------------- 用户 ----------------

def _user_dir(user_id):
    return os.path.join(config.DATA_DIR, "users", user_id)


def _user_path(user_id):
    return os.path.join(_user_dir(user_id), "user.json")


def _hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 10000
    ).hex()


def find_user_by_name(username):
    users_root = os.path.join(config.DATA_DIR, "users")
    if not os.path.isdir(users_root):
        return None
    for uid in os.listdir(users_root):
        u = read_json(_user_path(uid))
        if u and u.get("username") == username:
            return u
    return None


def get_user(user_id):
    return read_json(_user_path(user_id))


def create_user(username, password):
    salt = secrets.token_hex(8)
    user = {
        "id": new_id(),
        "username": username,
        "salt": salt,
        "pass_hash": _hash_password(password, salt),
        "profile": {"name": "", "org": "", "email": "", "phone": "", "bio": ""},
        "created_at": time.time(),
    }
    write_json(_user_path(user["id"]), user)
    return user


def verify_user(username, password):
    u = find_user_by_name(username)
    if not u:
        return None
    if _hash_password(password, u["salt"]) != u["pass_hash"]:
        return None
    return u


def update_profile(user_id, profile):
    u = get_user(user_id)
    if not u:
        return None
    u["profile"].update({k: str(v)[:500] for k, v in profile.items()
                         if k in ("name", "org", "email", "phone", "bio")})
    write_json(_user_path(user_id), u)
    return u


# ---------------- 登录令牌 ----------------

def create_token(user_id):
    token = secrets.token_hex(24)
    path = os.path.join(config.DATA_DIR, "tokens", token + ".json")
    write_json(path, {"user_id": user_id, "created": time.time(),
                      "expires": time.time() + config.TOKEN_TTL_SECONDS})
    return token


def get_token_user(token):
    if not token:
        return None
    t = read_json(os.path.join(config.DATA_DIR, "tokens", token + ".json"))
    if not t or t.get("expires", 0) < time.time():
        return None
    return get_user(t["user_id"])


def delete_token(token):
    try:
        os.remove(os.path.join(config.DATA_DIR, "tokens", token + ".json"))
    except OSError:
        pass


# ---------------- 简历 ----------------

def resumes_dir(user_id):
    return os.path.join(_user_dir(user_id), "resumes")


def list_resumes(user_id):
    d = resumes_dir(user_id)
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if f.endswith(".json"):
            meta = read_json(os.path.join(d, f))
            if meta:
                out.append(meta)
    out.sort(key=lambda m: m.get("created_at", 0), reverse=True)
    return out


def save_resume(user_id, filename, pdf_bytes, text):
    rid = new_id()
    d = resumes_dir(user_id)
    os.makedirs(d, exist_ok=True)
    pdf_path = os.path.join(d, rid + ".pdf")
    txt_path = os.path.join(d, rid + ".txt")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)
    meta = {
        "id": rid,
        "filename": filename,
        "size": len(pdf_bytes),
        "chars": len(text),
        "created_at": time.time(),
    }
    write_json(os.path.join(d, rid + ".json"), meta)
    return meta


def delete_resume(user_id, resume_id):
    d = resumes_dir(user_id)
    for ext in (".pdf", ".txt", ".json"):
        try:
            os.remove(os.path.join(d, resume_id + ext))
        except OSError:
            pass


def get_resume_text(user_id, resume_id):
    path = os.path.join(resumes_dir(user_id), resume_id + ".txt")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


# ---------------- 会话 ----------------

def sessions_dir(user_id):
    return os.path.join(_user_dir(user_id), "sessions")


def _session_path(user_id, session_id):
    return os.path.join(sessions_dir(user_id), session_id + ".json")


def list_sessions(user_id, kind=None):
    d = sessions_dir(user_id)
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if f.endswith(".json"):
            s = read_json(os.path.join(d, f))
            if s and (kind is None or s.get("kind", "interview") == kind):
                out.append(s)
    out.sort(key=lambda s: s.get("created_at", 0), reverse=True)
    return out


def create_session(user_id, name, kind="interview", resume_id=None, level="medium",
                   task_count=2, time_limit_min=None, context_type="none",
                   context_text="", context_label=""):
    tmin, tmax, cap = config.LEVEL_RANGES.get(level, config.LEVEL_RANGES["medium"])
    s = {
        "id": new_id(),
        "user_id": user_id,
        "name": name,
        "kind": kind,          # interview / training
        "resume_id": resume_id or "",
        "resume_name": "",
        "level": level,
        "cv_target_min": tmin,
        "cv_target_max": tmax,
        "cv_cap": cap,
        "task_count": task_count,
        "time_limit_min": time_limit_min,
        "context_type": context_type,   # none / text / session（训练会话）
        "context_text": context_text,
        "context_label": context_label,
        "tasks": [],
        "status": "created",   # created / active / scored
        "phase": "cv",         # cv / task
        "cv_asked": 0,
        "task_index": 0,
        "task_turns": 0,
        "messages": [],
        "result": None,
        "created_at": time.time(),
        "started_at": None,
        "ended_at": None,
    }
    save_session(s)
    return s


def get_session(user_id, session_id):
    return read_json(_session_path(user_id, session_id))


def save_session(s):
    write_json(_session_path(s["user_id"], s["id"]), s)


def delete_session(user_id, session_id):
    try:
        os.remove(_session_path(user_id, session_id))
    except OSError:
        pass
