"""线上审查 part2：CDP 截图 + UI 交互检查（用 part1 生成的会话与 token）。"""
import base64
import json
import os
import subprocess
import time
import urllib.request

import websocket

BASE = "http://152.136.60.146"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEBUG_PORT = 9555
SHOT_DIR = os.path.join(os.environ["TEMP"], "vc_audit")
os.makedirs(SHOT_DIR, exist_ok=True)

STATE = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "_audit_state.json"), encoding="utf-8"))
FINDINGS = []


def finding(area, severity, desc):
    FINDINGS.append({"area": area, "severity": severity, "desc": desc})
    print(f"[{severity}] {area}: {desc}", flush=True)


class CDP:
    def __init__(self):
        self.proc = subprocess.Popen(
            [CHROME, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}",
             "--remote-allow-origins=*", "--window-size=1440,940",
             "--hide-scrollbars", "--disable-gpu",
             "--disable-backgrounding-occluded-windows",
             "--disable-renderer-backgrounding",
             "--disable-background-timer-throttling",
             "--user-data-dir=" + os.path.join(os.environ["TEMP"], "vc_audit_profile")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(60):
            try:
                tabs = json.loads(urllib.request.urlopen(
                    f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=2).read())
                page = next(t for t in tabs if t["type"] == "page")
                ws_url = page["webSocketDebuggerUrl"]
                break
            except Exception:
                time.sleep(0.3)
        self.ws = websocket.create_connection(ws_url, timeout=90)
        self.mid = 0

    def cmd(self, method, **params):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("method") == "Page.javascriptDialogOpening":
                self.ws.send(json.dumps({"id": 99999, "method": "Page.handleJavaScriptDialog",
                                         "params": {"accept": False}}))
                finding("dialog", "low", f"弹出确认框: {msg['params'].get('message','')[:50]}")
                continue
            if msg.get("id") == self.mid:
                return msg.get("result", {})

    def goto(self, url, wait=2.5):
        self.cmd("Page.navigate", url=url)
        time.sleep(wait)

    def eval(self, expr):
        r = self.cmd("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if r.get("exceptionDetails"):
            return "EXC:" + str(r["exceptionDetails"].get("exception", {}).get("description", ""))[:100]
        return r.get("result", {}).get("value")

    def shot(self, name):
        data = self.cmd("Page.captureScreenshot", format="png")["data"]
        with open(os.path.join(SHOT_DIR, name), "wb") as f:
            f.write(base64.b64decode(data))
        print("  shot:", name, flush=True)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        self.proc.terminate()


def main():
    c = CDP()
    try:
        c.cmd("Network.setCookie", name="vc_session", value=STATE["token"],
              url=BASE, path="/", httpOnly=True)

        # 首页（登录态）
        c.goto(BASE + "/")
        c.shot("20-home.png")
        # 训练 tab
        c.eval("document.querySelector('.seg-tab[data-ltab=\"training\"]').click()")
        time.sleep(1.0)
        c.shot("21-home-training.png")
        c.eval("document.querySelector('.seg-tab[data-ltab=\"interview\"]').click()")
        time.sleep(0.8)

        # 设置页
        c.eval("document.querySelector('#user-btn')?.click()")
        time.sleep(1.2)
        c.shot("22-settings.png")
        c.eval("location.href = '/'")
        time.sleep(2)

        # 面试会话：结果页（scored 后 SPA）
        sid = STATE["interview_sid"]
        c.goto(BASE + "/session/" + sid)
        time.sleep(2)
        order = c.eval("""[...document.querySelector('.chat-inner').children].map(el =>
          el.className.includes('result') ? 'PANEL' : el.className.includes('msg') ? 'msg'
            : el.className.toString().slice(0,12)).join(',')""")
        finding("interview", "info", f"结果页顺序: {order}")
        c.eval("document.querySelector('.result')?.scrollIntoView({block:'start'})")
        time.sleep(0.4)
        c.shot("23-result.png")

        # 点击继续（即时反馈）
        c.eval("document.querySelector('#continue-btn')?.click()")
        time.sleep(0.5)
        fb = c.eval("JSON.stringify({btn: document.querySelector('#continue-btn')?.textContent, dis: document.querySelector('#continue-btn')?.disabled, thinking: !!document.querySelector('#thinking-msg')})")
        finding("interview", "info", f"继续即时反馈: {fb}")
        for _ in range(40):
            time.sleep(3)
            if c.eval("!!document.querySelector('#answer-input') && !document.querySelector('#thinking-msg')"):
                break
        order2 = c.eval("""[...document.querySelector('.chat-inner').children].map(el =>
          el.className.includes('result') ? 'PANEL' : el.className.includes('msg') ? 'msg'
            : el.className.toString().slice(0,12)).join(',')""")
        finding("interview", "info", f"继续后顺序: {order2}")
        c.shot("24-continued.png")

        # 退出重进
        c.goto(BASE + "/session/" + sid, wait=3)
        order3 = c.eval("""[...document.querySelector('.chat-inner').children].map(el =>
          el.className.includes('result') ? 'PANEL' : el.className.includes('msg') ? 'msg'
            : el.className.toString().slice(0,12)).join(',')""")
        finding("interview", "info", f"重进顺序: {order3}")
        if order2 != order3:
            finding("interview", "high", f"重进后面板/消息顺序变化: {order2} -> {order3}")
        c.shot("25-reentry.png")

        # busy 中重复发送
        c.eval("""(async () => {
          const ta = document.querySelector('#answer-input');
          if (ta) {
            ta.value = '重进后回答一轮';
            ta.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
          }
        })()""")
        time.sleep(0.5)
        c.eval("""(async () => {
          const ta = document.querySelector('#answer-input');
          if (ta && !ta.disabled) {
            ta.value = '重复发送测试';
            ta.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
          }
        })()""")
        time.sleep(1)
        toast = c.eval("document.querySelector('.mini-toast')?.textContent || null")
        finding("interview", "info", f"busy重复发送提示: {toast}")
        for _ in range(40):
            time.sleep(3)
            if c.eval("!document.querySelector('#thinking-msg') && !!document.querySelector('#answer-input')"):
                break

        # 训练总结页
        c.goto(BASE + "/session/" + STATE["training_tid"])
        time.sleep(2)
        has_summary = c.eval("!!document.querySelector('.result-title')")
        if not has_summary:
            finding("training", "high", "训练总结页无总结面板")
        c.eval("document.querySelector('.result')?.scrollIntoView({block:'start'})")
        time.sleep(0.4)
        c.shot("26-training-summary.png")
        cont2 = c.eval("document.querySelector('#continue-btn')?.textContent || null")
        finding("training", "info", f"训练继续按钮: {cont2}")

        # 训练弹层 UI
        c.goto(BASE + "/")
        time.sleep(2)
        c.eval("document.querySelector('.seg-tab[data-ltab=\"training\"]').click()")
        time.sleep(1)
        c.eval("document.querySelector('#new-training')?.click()")
        time.sleep(0.6)
        c.shot("27-training-modal.png")
        import_radio = c.eval("""(async () => {
          const r = document.querySelector('#training-form input[name="context_type"][value="import"]');
          r.checked = true; r.dispatchEvent(new Event('change', {bubbles:true}));
          const m = document.querySelector('#training-form input[name="ctx_method"][value="session"]');
          m.checked = true; m.dispatchEvent(new Event('change', {bubbles:true}));
          await new Promise(res => setTimeout(res, 200));
          return document.querySelector('#ctx-session-select')?.value;
        })()""")
        finding("training", "info", f"导入面试记录下拉首个值: {import_radio!r}")
        c.eval("document.querySelector('.modal-mask')?.remove()")

        # 内联重命名
        time.sleep(0.5)
        c.eval("document.querySelector('[data-rename]')?.click()")
        time.sleep(0.4)
        if not c.eval("!!document.querySelector('.rename-input')"):
            finding("ui", "medium", "重命名未出现内联输入框")
        else:
            c.eval("""(async () => {
              const inp = document.querySelector('.rename-input');
              inp.value = '线上审查改名';
              inp.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}));
            })()""")
            time.sleep(1.5)
        c.shot("28-home-final.png")

        # 移动端窄屏快速检查
        c.cmd("Emulation.setDeviceMetricsOverride", width=390, height=844,
              deviceScaleFactor=2, mobile=True)
        c.goto(BASE + "/", wait=2.5)
        c.shot("29-mobile-home.png")
        c.goto(BASE + "/session/" + sid, wait=3)
        c.shot("30-mobile-session.png")
        c.cmd("Emulation.clearDeviceMetricsOverride")

        print("\nshots at", SHOT_DIR, flush=True)
    finally:
        c.close()
    with open(os.path.join(SHOT_DIR, "findings2.json"), "w", encoding="utf-8") as f:
        json.dump(FINDINGS, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
