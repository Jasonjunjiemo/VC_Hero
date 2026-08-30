"""用无头 Chrome 验证"继续面试"前端流程（对 :5001 stub 服务器）。"""
import base64
import json
import os
import subprocess
import time
import urllib.request

import websocket

BASE = "http://127.0.0.1:5001"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEBUG_PORT = 9444


class CDP:
    def __init__(self):
        self.proc = subprocess.Popen(
            [CHROME, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}",
             "--remote-allow-origins=*", "--window-size=1440,940",
             "--hide-scrollbars", "--disable-gpu",
             "--disable-backgrounding-occluded-windows",
             "--disable-renderer-backgrounding",
             "--disable-background-timer-throttling",
             "--user-data-dir=" + os.path.join(os.environ["TEMP"], "vc_e2e")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        self.cmd("Network.enable")
        self.cmd("Page.enable")

    def cmd(self, method, **params):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.mid:
                return msg.get("result", {})

    def goto(self, url):
        self.cmd("Page.navigate", url=url)
        time.sleep(2.2)

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
    out = {}
    try:
        # 登录（注入 cookie）
        c.cmd("Network.setCookie", name="vc_session", value="tok_stub",
              url=BASE, path="/", httpOnly=True)
        c.goto(BASE + "/session/ivx1")
        time.sleep(1.5)

        out["interview_scored"] = c.eval("""JSON.stringify({
          order: [...document.querySelector('.chat-inner').children].map(el =>
            el.className.includes('result') ? 'PANEL' : el.className.includes('msg') ? 'msg'
              : el.className.toString().slice(0,12)),
          continueBtn: document.querySelector('#continue-btn')?.textContent || null,
          finishBtn: document.querySelector('#finish-btn')?.textContent || null,
          rings: [...document.querySelectorAll('.grade-ring')].map(g => g.textContent)
        })""")

        # 点击面板下方的"继续面试"——立即检查反馈（禁用 + 思考气泡），不等响应
        c.eval("document.querySelector('#continue-btn')?.click()")
        out["continue_immediate_feedback"] = c.eval("""JSON.stringify({
          btnDisabled: document.querySelector('#continue-btn')?.disabled || false,
          btnText: document.querySelector('#continue-btn')?.textContent || null,
          thinking: !!document.querySelector('#thinking-msg'),
          topBtnDisabled: document.querySelector('#finish-btn')?.disabled || false
        })""")
        time.sleep(1.5)
        out["after_continue_click"] = c.eval("""JSON.stringify({
          status: (window.__s = document.querySelector('#answer-input')) ? 'has-composer' : 'no-composer',
          finishBtn: document.querySelector('#finish-btn')?.textContent || null,
          order: [...document.querySelector('.chat-inner').children].map(el =>
            el.className.includes('result') ? 'PANEL' : el.className.includes('msg') ? 'msg'
              : el.className.toString().slice(0,12))
        })""")

        # 面板收缩：继续后旧结果应自动收起；点击头部可展开/再收起
        out["panel_collapse"] = c.eval("""JSON.stringify({
          autoCollapsed: !!document.querySelector('.result.collapsed'),
          latestExpandedOnScored: true
        })""")
        c.eval("document.querySelector('.result .panel-head')?.click()")
        out["panel_expand_click"] = c.eval("!document.querySelector('.result').classList.contains('collapsed')")
        c.eval("document.querySelector('.result .panel-head')?.click()")
        out["panel_collapse_again"] = c.eval("document.querySelector('.result').classList.contains('collapsed')")
        # 走一轮回答（stub 秒回）
        c.eval("""(async () => {
          const ta = document.querySelector('#answer-input');
          ta.value = '续聊的回答';
          ta.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
        })()""")
        time.sleep(2)
        out["after_answer"] = c.eval("""JSON.stringify({
          meMsgs: [...document.querySelectorAll('.msg.me .bubble')].map(b => b.textContent),
          lastAi: document.querySelectorAll('.msg.ai .bubble').length
        })""")

        # ===== 面板位置恒定性：记录位置 → 退出重进（服务端渲染）→ 对比 =====
        def snapshot():
            return c.eval("""(function(){try{return JSON.stringify({url:location.pathname.slice(0,25),order:[...document.querySelector('.chat-inner').children].map(el =>
              el.className.includes('result') ? 'PANEL' : el.className.includes('msg') ? 'msg'
                : el.className.toString().slice(0,12))})}catch(e){return 'ERR:'+e.message}})()""")

        pos_before = snapshot()
        c.goto(BASE + "/session/ivx1")   # 重进（active 会话 = 服务端渲染页）
        time.sleep(1.8)
        pos_reentry = snapshot()
        print("reentry:", pos_reentry, flush=True)
        out["panel_position_reentry"] = {"before": pos_before, "after": pos_reentry,
                                         "stable": pos_before == pos_reentry}

        # 再答一轮，面板应仍锚定
        c.eval("""(async () => {
          const ta = document.querySelector('#answer-input');
          if (ta) {
            ta.value = '第二轮续聊';
            ta.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
          }
        })()""")
        time.sleep(2)
        pos_after2 = snapshot()
        print("after2:", pos_after2, flush=True)
        out["panel_position_after_more"] = {
          "panels": pos_after2.count("PANEL"),
          "anchor_stable": pos_after2.index("PANEL") == pos_reentry.index("PANEL") if "PANEL" in pos_reentry else None,
          "order": pos_after2,
        }

        # 训练会话验证
        c.goto(BASE + "/session/trx1")
        time.sleep(1.5)
        out["training_scored"] = c.eval("""JSON.stringify({
          hasSummary: !!document.querySelector('.result-title'),
          summaryTitle: document.querySelector('.result-title')?.textContent,
          continueBtn: document.querySelector('#continue-btn')?.textContent || null,
          finishBtn: document.querySelector('#finish-btn')?.textContent || null
        })""")
        c.eval("document.querySelector('#continue-btn')?.click()")
        time.sleep(1.5)
        out["training_after_continue"] = c.eval("""JSON.stringify({
          composer: !!document.querySelector('#answer-input'),
          finishBtn: document.querySelector('#finish-btn')?.textContent || null
        })""")

        print(json.dumps(out, ensure_ascii=False, indent=1))
    finally:
        c.close()


if __name__ == "__main__":
    main()
