"""用无头 Chrome 给 VC_Hero 关键页面截图（供 README 使用）。

驱动 DevTools 协议：走完整流程（首页两个 tab → 注册 → 建会话 → 开始面试 → 作答 → 评分），
截图保存到 docs/screenshots/。
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

import websocket

BASE = "http://127.0.0.1:5000"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "docs", "screenshots")
os.makedirs(OUT_DIR, exist_ok=True)

DEBUG_PORT = 9333


class CDP:
    def __init__(self):
        proc = subprocess.Popen(
            [CHROME, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}",
             "--remote-allow-origins=*",
             "--window-size=1440,940", "--hide-scrollbars", "--disable-gpu",
             "--user-data-dir=" + os.path.join(os.environ["TEMP"], "vc_hero_shots")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.proc = proc
        ws_url = None
        for _ in range(50):
            try:
                tabs = json.loads(urllib.request.urlopen(
                    f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=2).read())
                page = next(t for t in tabs if t["type"] == "page")
                ws_url = page["webSocketDebuggerUrl"]
                break
            except Exception:
                time.sleep(0.3)
        self.ws = websocket.create_connection(ws_url, timeout=60)
        self.mid = 0

    def cmd(self, method, **params):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.mid:
                return msg.get("result", {})

    def goto(self, url):
        self.cmd("Page.navigate", url=url)
        time.sleep(2.5)

    def eval(self, expr):
        r = self.cmd("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def shot(self, name):
        time.sleep(0.4)
        data = self.cmd("Page.captureScreenshot", format="png")["data"]
        path = os.path.join(OUT_DIR, name)
        with open(path, "wb") as f:
            f.write(base64.b64decode(data))
        print("saved", name, flush=True)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        self.proc.terminate()


def main():
    c = CDP()
    try:
        # 1. 首页（面试官 tab，未登录）
        c.goto(BASE + "/")
        c.eval("window.scrollTo(0,0)")
        c.shot("01-home-interview.png")

        # 2. 登录 + 训练官 tab
        c.eval("""(async () => {
          let r = await fetch('/api/register', {method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({username:'readme_shot', password:'pw123'})});
          if (!r.ok) r = await fetch('/api/login', {method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({username:'readme_shot', password:'pw123'})});
          location.href = '/';
        })()""")
        time.sleep(2.5)
        c.eval("document.querySelector('.seg-tab[data-ltab=\"training\"]')?.click()")
        time.sleep(1.2)
        c.eval("window.scrollTo(0,0)")
        c.shot("02-home-training.png")

        # 3. 上传简历 + 建面试会话 → 开始卡片
        sid = c.eval("""(async () => {
          const text = 'Zhao Lei. Harbin Institute of Technology. Built 900 person robotics community. ' +
            'Contacted 75 industry speakers over 10 months. Organized 18 events.';
          const stream = 'BT /F1 12 Tf 72 720 Td (' + text + ') Tj ET';
          const objs = ['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
            '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
            '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
            '<< /Length ' + stream.length + ' >>\\nstream\\n' + stream + '\\nendstream'];
          let pdf = '%PDF-1.4\\n'; const offs = [];
          objs.forEach((b, i) => { offs.push(pdf.length); pdf += (i+1) + ' 0 obj\\n' + b + '\\nendobj\\n'; });
          const xref = pdf.length; pdf += 'xref\\n0 6\\n0000000000 65535 f \\n';
          offs.forEach(o => pdf += String(o).padStart(10,'0') + ' 00000 n \\n');
          pdf += 'trailer\\n<< /Size 6 /Root 1 0 R >>\\nstartxref\\n' + xref + '\\n%%EOF';
          const fd = new FormData();
          fd.append('file', new Blob([new TextEncoder().encode(pdf)], {type:'application/pdf'}), 'cv_zhaolei.pdf');
          const up = await fetch('/api/resumes', {method:'POST', body: fd});
          const rid = (await up.json()).resume.id;
          const cr = await fetch('/api/sessions', {method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({kind:'interview', name:'README 截图面试', resume_id: rid,
                                  level:'low', task_count:1, time_limit_min:null})});
          return (await cr.json()).session.id;
        })()""")
        c.goto(BASE + "/session/" + sid)
        time.sleep(1.5)
        c.shot("03-start-card.png")

        # 4. 开始面试 → 等首问真正到达（无思考气泡且有内容）
        c.eval("document.querySelector('.big-btn')?.click()")
        for _ in range(90):
            time.sleep(2)
            ready = c.eval("!!document.querySelector('#answer-input') && "
                           "!document.querySelector('#thinking-msg') && "
                           "(document.querySelector('.msg.ai .bubble')||{textContent:''}).textContent.trim().length > 10")
            if ready:
                break
        c.eval("window.scrollTo(0,0)")
        c.shot("04-chat.png")

        # 5. 作答两轮（等每轮考官回复到达再发下一条）
        for answer in [
            "最开始是在学院社团内部逐个邀请的，前 100 人基本都是我认识的同学和他们的室友。",
            "后来主要靠每周的技术分享会，我负责邀请嘉宾，前后联系了 75 位行业人士，最后稳定合作的有 12 位。",
        ]:
            c.eval("""(async () => {
              const ta = document.querySelector('#answer-input');
              if (!ta) return;
              ta.value = %s;
              ta.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
            })()""" % json.dumps(answer))
            for _ in range(60):
                time.sleep(2)
                ready = c.eval("!document.querySelector('#thinking-msg') && "
                               "document.querySelectorAll('.msg.ai .bubble').length >= "
                               "document.querySelectorAll('.msg.me').length")
                if ready:
                    break
        c.eval("window.scrollTo(0,0)")
        c.shot("05-chat-answered.png")

        # 6. 结束面试 → 等评分完成 → 结果页
        c.eval("""fetch('/api/sessions/""" + str(sid) + """/finish', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'})""")
        for _ in range(30):
            time.sleep(2)
            done = c.eval(
                "(async()=>((await (await fetch('/api/sessions/%s')).json()).session.status))()" % sid)
            if done == "scored":
                break
        time.sleep(1)
        c.goto(BASE + "/session/" + str(sid))
        time.sleep(2)
        c.eval("document.querySelector('.result')?.scrollIntoView({block:'start'})")
        time.sleep(0.5)
        c.shot("06-result.png")
        print("ALL DONE")
    finally:
        c.close()


if __name__ == "__main__":
    main()
