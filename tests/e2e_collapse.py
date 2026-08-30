"""面板收缩功能专项验证（最小化）。"""
import base64
import json
import os
import subprocess
import time
import urllib.request

import websocket

BASE = "http://127.0.0.1:5001"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9666


class CDP:
    def __init__(self):
        self.proc = subprocess.Popen(
            [CHROME, "--headless=new", f"--remote-debugging-port={PORT}",
             "--remote-allow-origins=*", "--window-size=1440,940",
             "--hide-scrollbars", "--disable-gpu",
             "--disable-backgrounding-occluded-windows",
             "--disable-renderer-backgrounding",
             "--disable-background-timer-throttling",
             "--user-data-dir=" + os.path.join(os.environ["TEMP"], "vc_collapse")],
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
        # 刚出结果（scored，无后续消息）：面板应展开
        c.cmd("Page.navigate", url=BASE + "/session/ivx1")
        time.sleep(3)
        r1 = c.eval("""JSON.stringify({
          url: location.pathname,
          hasPanel: !!document.querySelector('.result'),
          collapsed: document.querySelector('.result')?.classList.contains('collapsed') || false
        })""")
        print("scored页(新结果):", r1, flush=True)

        # 点击继续 → 等新消息 → 旧面板应自动收起
        c.eval("document.querySelector('#continue-btn')?.click()")
        for _ in range(20):
            time.sleep(1.5)
            if c.eval("!!document.querySelector('#answer-input') && !document.querySelector('#thinking-msg')"):
                break
        r2 = c.eval("""JSON.stringify({
          autoCollapsed: document.querySelector('.result')?.classList.contains('collapsed') || false,
          bodyVisible: (() => { const b = document.querySelector('.result .panel-body'); return b ? getComputedStyle(b).display !== 'none' : null; })()
        })""")
        print("继续后:", r2, flush=True)

        # 点头部展开 → 再点收起
        c.eval("document.querySelector('.result .panel-head')?.click()")
        time.sleep(0.3)
        r3 = c.eval("!document.querySelector('.result').classList.contains('collapsed')")
        c.eval("document.querySelector('.result .panel-head')?.click()")
        time.sleep(0.3)
        r4 = c.eval("document.querySelector('.result').classList.contains('collapsed')")
        print("手动展开:", r3, "| 再收起:", r4, flush=True)

        # 重进后：面板仍收起（自动规则），手动状态本次会话内保留
        c.cmd("Page.navigate", url=BASE + "/session/ivx1")
        time.sleep(3)
        r5 = c.eval("JSON.stringify({collapsed: document.querySelector('.result')?.classList.contains('collapsed') || false, url: location.pathname})")
        print("重进:", r5, flush=True)
    finally:
        c.close()


if __name__ == "__main__":
    main()
