"""VC_Hero 应用工厂。"""
import json
import os

from flask import Flask, render_template, send_from_directory

from . import config, routes, storage
from .kimi import KimiClient
from .ratelimit import RateLimiter


def create_app():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    storage._ensure_dirs()

    with open(config.KEY_FILE, "r", encoding="utf-8") as f:
        api_key = f.read().strip()
    if not api_key:
        raise RuntimeError(f"缺少 Kimi API key 文件: {config.KEY_FILE}")

    app = Flask(__name__, static_folder=config.STATIC_DIR, static_url_path="/static",
                template_folder=os.path.join(config.BASE_DIR, "templates"))
    # 静态资源不缓存 + 版本号防缓存：版本取文件当前修改时间，任何编辑立即生效
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    def static_version():
        return str(max(
            int(os.path.getmtime(os.path.join(config.STATIC_DIR, "app.js"))),
            int(os.path.getmtime(os.path.join(config.STATIC_DIR, "style.css"))),
        ))

    app.extensions["kimi_client"] = KimiClient(api_key, RateLimiter())
    app.register_blueprint(routes.bp)

    @app.after_request
    def no_cache_html(resp):
        # HTML 一律不缓存：防止浏览器启发式缓存旧页面、旧页面再引用旧静态资源
        if resp.content_type and "text/html" in resp.content_type:
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    @app.route("/")
    def index():
        return render_template("index.html", v=static_version())

    @app.route("/session/<session_id>")
    def session_page(session_id):
        # 已开始的会话：服务端渲染首屏（顶栏、消息、输入框一次到位）
        token = routes.token_from_cookie()
        s = storage.get_session(routes.token_user_id(token), session_id) if token else None
        if (s and s.get("kind", "interview") in ("interview", "training")
                and s["status"] == "active" and s["messages"]):
            return render_template(
                "session.html",
                title=s["name"],
                kind=s.get("kind", "interview"),
                name=s["name"],
                v=static_version(),
                messages=s["messages"],
                messages_json=json.dumps(s["messages"], ensure_ascii=False),
                result_json=json.dumps(s.get("result"), ensure_ascii=False),
                results_history_json=json.dumps(s.get("results_history", []), ensure_ascii=False),
                result_boundary=s.get("result_boundary"),
            )
        # 未开始/无消息：返回应用入口，由前端渲染开始卡片
        return render_template("index.html", v=static_version())

    @app.route("/<path:filename>")
    def static_files(filename):
        if filename.startswith("api/"):
            return {"error": "not found"}, 404
        return send_from_directory(config.STATIC_DIR, filename)

    return app
