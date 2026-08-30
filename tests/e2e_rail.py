"""结果速览侧边栏专项验证。"""
import json
import os
import subprocess
import time
import urllib.request

import websocket

BASE = "http://127.0.0.1:5001"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9777


class CDP:
    def __init__(self):
        self.proc = subprocess.Popen(
            [CHROME, "--headless=new", f"--remote-debugging-port={PORT}",
             "--remote-allow-origins=*", "--window-size=1440,940",
             "--hide-scrollbars", "--disable-gpu",
             "--disable-backgrounding-occluded-windows",
             "--disable-renderer-backgrounding",
             "--disable-background-timer-throttling",
             "--user-data-dir=" + os.path.join(os.environ["TEMP"], "vc_rail")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(60):
            try:
                tabs = json.loads(urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/json", timeout=2).read())
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

    def eval(self, expr):
        r = self.cmd("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        self.proc.terminate()


def main():
    c = CDP()
    try:
        c.cmd("Network.setCookie", name="vc_session", value="tok_stub", url=BASE,
              path="/", httpOnly=True)
        c.cmd("Page.navigate", url=BASE + "/session/ivx1")
        time.sleep(3)

        # 1. 侧边栏存在、默认收起（抽屉关）、列表两项
        r1 = c.eval("""JSON.stringify({
          railExists: !!document.querySelector('#result-rail'),
          drawerOpen: document.querySelector('#result-rail')?.classList.contains('open') || false,
          tabText: document.querySelector('#result-rail .rail-tab span')?.textContent || null,
          itemCount: document.querySelectorAll('#result-rail .rail-item').length,
          itemTexts: [...document.querySelectorAll('#result-rail .rail-item')].map(b => b.textContent.trim())
        })""")
        print("1.初始:", r1, flush=True)

        # 2. 点开抽屉
        c.eval("document.querySelector('#rail-tab')?.click()")
        time.sleep(0.3)
        print("2.抽屉打开:", c.eval("document.querySelector('#result-rail').classList.contains('open')"), flush=True)

        # 3. 点击第一项（历史结果 C 64.2，boundary=4，其后有消息 → 面板收起）→ 应自动展开并收起抽屉
        c.eval("document.querySelector('.rail-item[data-boundary=\"4\"]')?.click()")
        time.sleep(0.8)
        r3 = c.eval("""JSON.stringify({
          drawerClosed: !document.querySelector('#result-rail').classList.contains('open'),
          targetExpanded: !(document.querySelector('.result[data-boundary="4"]')||{classList:{contains:()=>null}}).classList.contains('collapsed'),
          targetVisible: (() => { const p = document.querySelector('.result[data-boundary="4"]'); if (!p) return false;
            const r = p.getBoundingClientRect(); return r.top >= 0 && r.bottom <= window.innerHeight; })()
        })""")
        print("3.点击跳转:", r3, flush=True)

        # 4. 无结果会话（新建未开始的会话页）：侧边栏应不存在
        sid2 = c.eval("""(async () => {
          const r = await fetch('/api/sessions', {method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({kind:'training', name:'无结果会话', context_type:'none'})});
          return (await r.json()).session.id;
        })()""")
        c.cmd("Page.navigate", url=BASE + "/session/" + sid2)
        time.sleep(2.5)
        print("4.无结果页侧边栏(应为false):",
              c.eval("!!document.querySelector('#result-rail')"), flush=True)
    finally:
        c.close()


if __name__ == "__main__":
    main()
