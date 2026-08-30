"""VC_Hero 应用工厂。"""
import os

from flask import Flask, send_from_directory

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

    app = Flask(__name__, static_folder=config.STATIC_DIR, static_url_path="/static")
    app.extensions["kimi_client"] = KimiClient(api_key, RateLimiter())
    app.register_blueprint(routes.bp)

    @app.route("/")
    def index():
        return send_from_directory(config.STATIC_DIR, "index.html")

    @app.route("/<path:filename>")
    def static_files(filename):
        if filename.startswith("api/"):
            return {"error": "not found"}, 404
        return send_from_directory(config.STATIC_DIR, filename)

    return app
