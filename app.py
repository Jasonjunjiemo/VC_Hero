"""VC_Hero 启动入口：python app.py"""
from vc_hero import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
