"""VC_Hero 启动入口：python app.py（可用环境变量 PORT/HOST 覆盖）"""
import os

from vc_hero import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "0.0.0.0"),
            port=int(os.environ.get("PORT", 5000)),
            threaded=True)
