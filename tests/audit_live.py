"""线上站点人工排查脚本：注册 → 全功能试玩 → 截图 + DOM 检查。
只报告，不修改。截图存 %TEMP%/vc_audit/。
"""
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
                                         "params": {"accept": True}}))
                finding("dialog", "info", f"页面弹出对话框: {msg['params'].get('message','')[:60]}")
                continue
            if msg.get("id") == self.mid:
                return msg.get("result", {})

    def goto(self, url, wait=2.5):
        self.cmd("Page.navigate", url=url)
        time.sleep(wait)

    def eval(self, expr):
        r = self.cmd("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        res = r.get("result", {})
        if r.get("exceptionDetails"):
            return "EXC:" + str(r["exceptionDetails"].get("exception", {}).get("description", ""))[:120]
        return res.get("value")

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
        ts = str(int(time.time()))[-6:]
        USER = f"audit{ts}"
        PW = "audit12345"

        # ---- 1. 注册 / 登录 ----
        c.goto(BASE + "/")
        c.shot("01-landing.png")
        c.eval(f"""(async () => {{
          const r = await fetch('/api/register', {{method:'POST', headers:{{'Content-Type':'application/json'}},
            body: JSON.stringify({{username: {json.dumps(USER)}, password: {json.dumps(PW)}}})}});
          return r.status;
        }})()""")
        time.sleep(1.5)
        c.eval("location.href = '/'")
        time.sleep(2)
        me = c.eval("(await (await fetch('/api/me')).json()).user.username")
        if me != USER:
            finding("auth", "high", f"注册后登录态异常: me={me}")
        c.shot("02-home-loggedin.png")

        # tab 切换
        c.eval("document.querySelector('.seg-tab[data-ltab=\"training\"]').click()")
        time.sleep(1.0)
        c.shot("03-home-training.png")
        c.eval("document.querySelector('.seg-tab[data-ltab=\"interview\"]').click()")
        time.sleep(1.0)

        # ---- 2. 设置页 + 简历 ----
        c.eval("document.querySelector('#user-btn').click()")
        time.sleep(1.2)
        c.shot("04-settings.png")
        # 无效文件上传（文本文件伪装 pdf）
        r = c.eval("""(async () => {
          const blob = new Blob(['not a real pdf'], {type:'application/pdf'});
          const fd = new FormData(); fd.append('file', blob, 'fake.pdf');
          const r = await fetch('/api/resumes', {method:'POST', body: fd});
          const d = await r.json();
          return r.status + ':' + (d.error || 'ok');
        })()""")
        if not str(r).startswith("400"):
            finding("resume", "medium", f"伪PDF未被拒绝: {r}")
        # 真简历
        r = c.eval("""(async () => {
          const text = 'Audit User. Fudan. Founded 800 person product community. Contacted 68 speakers over 9 months. Organized 22 events. Won 3 hackathons.';
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
          fd.append('file', new Blob([new TextEncoder().encode(pdf)], {type:'application/pdf'}), 'cv_audit.pdf');
          const r = await fetch('/api/resumes', {method:'POST', body: fd});
          return r.status;
        })()""")
        if str(r) != "200":
            finding("resume", "high", f"真实PDF上传失败: {r}")

        # ---- 3. 面试全流程 ----
        c.eval("location.href = '/'")
        time.sleep(2)
        sid = c.eval("""(async () => {
          const rid = (await (await fetch('/api/resumes')).json()).resumes[0].id;
          const r = await fetch('/api/sessions', {method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({kind:'interview', name:'审查面试', resume_id: rid, level:'low', task_count:1, time_limit_min:null})});
          return (await r.json()).session.id;
        })()""")
        finding("flow", "info", f"面试会话 id={sid}")
        c.goto(BASE + "/session/" + sid)
        time.sleep(1.5)
        c.shot("05-start-card.png")
        # 开始（真实 LLM，等待）
        c.eval("document.querySelector('.big-btn')?.click()")
        # 即时反馈检查
        time.sleep(0.5)
        fb = c.eval("JSON.stringify({thinking: !!document.querySelector('#thinking-msg'), composer: !!document.querySelector('#answer-input')})")
        finding("flow", "info", f"开始即时反馈: {fb}")
        for _ in range(60):
            time.sleep(3)
            ok = c.eval("!!document.querySelector('#answer-input') && !document.querySelector('#thinking-msg')")
            if ok:
                break
        q1 = c.eval("document.querySelector('.msg.ai .bubble')?.textContent?.slice(0,80)")
        finding("flow", "info", f"首问: {q1}")
        c.shot("06-first-question.png")
        # 回答三轮（每轮等回复）
        for i, a in enumerate([
            "最开始逐个邀请熟人，前100人来自同学和室友。",
            "后来靠每周分享会增长，我联系了68位嘉宾，稳定合作15位。",
            "踩过的坑是早期活动来的人少，后来先小范围验证主题再放大。",
        ]):
            c.eval(f"""(async () => {{
              const ta = document.querySelector('#answer-input');
              if (!ta) return 'no-ta';
              ta.value = {json.dumps(a)};
              ta.dispatchEvent(new KeyboardEvent('keydown', {{key:'Enter', bubbles:true, cancelable:true}}));
            }})()""")
            for _ in range(40):
                time.sleep(3)
                done = c.eval("!document.querySelector('#thinking-msg') && !!document.querySelector('#answer-input')")
                if done:
                    break
        c.shot("07-chat.png")
        # 结束面试
        c.eval(f"fetch('/api/sessions/{sid}/finish', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:'{{}}'}})")
        for _ in range(30):
            time.sleep(3)
            st = c.eval(f"(async()=>((await (await fetch('/api/sessions/{sid}')).json()).session.status))()")
            if st == "scored":
                break
        c.goto(BASE + "/session/" + sid)
        time.sleep(2)
        c.eval("document.querySelector('.result')?.scrollIntoView()")
        time.sleep(0.5)
        c.shot("08-result.png")
        grade = c.eval("document.querySelector('.grade-ring span')?.textContent")
        finding("flow", "info", f"评级: {grade}")
        # 继续面试 → 检查面板保留 + 新消息在下方
        c.eval("document.querySelector('#continue-btn')?.click()")
        time.sleep(0.6)
        fb = c.eval("JSON.stringify({btn: document.querySelector('#continue-btn')?.textContent, dis: document.querySelector('#continue-btn')?.disabled, thinking: !!document.querySelector('#thinking-msg')})")
        finding("flow", "info", f"继续即时反馈: {fb}")
        for _ in range(60):
            time.sleep(3)
            ok = c.eval("!!document.querySelector('#answer-input') && !document.querySelector('#thinking-msg')")
            if ok:
                break
        order = c.eval("""[...document.querySelector('.chat-inner').children].map(el =>
          el.className.includes('result') ? 'PANEL' : el.className.includes('msg') ? 'msg' : el.className.slice(0,10)).join(',')""")
        finding("flow", "info", f"继续后顺序: {order}")
        c.shot("09-continued.png")
        # 退出重进
        c.goto(BASE + "/session/" + sid)
        time.sleep(2)
        order2 = c.eval("""[...document.querySelector('.chat-inner').children].map(el =>
          el.className.includes('result') ? 'PANEL' : el.className.includes('msg') ? 'msg' : el.className.slice(0,10)).join(',')""")
        if order != order2:
            finding("continuation", "high", f"重进后顺序变化: {order} -> {order2}")
        c.shot("10-reentry.png")

        # ---- 4. 训练端 ----
        c.eval("location.href = '/'")
        time.sleep(2)
        c.eval("document.querySelector('.seg-tab[data-ltab=\"training\"]').click()")
        time.sleep(1)
        tid = c.eval("""(async () => {
          const r = await fetch('/api/sessions', {method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({kind:'training', name:'审查训练', context_type:'text',
              context_text:'我面试中被指出不会判断渠道优先级，也不擅长长期跟踪 founder。',
              context_label:'粘贴文本'})});
          return (await r.json()).session.id;
        })()""")
        c.goto(BASE + "/session/" + tid)
        time.sleep(1.5)
        c.eval("document.querySelector('.big-btn')?.click()")
        for _ in range(60):
            time.sleep(3)
            ok = c.eval("!!document.querySelector('#answer-input') && !document.querySelector('#thinking-msg')")
            if ok:
                break
        t1 = c.eval("document.querySelector('.msg.ai .bubble')?.textContent?.slice(0,90)")
        finding("training", "info", f"训练官开场: {t1}")
        c.eval("""(async () => {
          const ta = document.querySelector('#answer-input');
          ta.value = '我会先列出候选渠道，再按转化率排序。';
          ta.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
        })()""")
        for _ in range(40):
            time.sleep(3)
            done = c.eval("!document.querySelector('#thinking-msg') && !!document.querySelector('#answer-input')")
            if done:
                break
        c.shot("11-training.png")
        t2 = c.eval("[...document.querySelectorAll('.msg.ai .bubble')].pop()?.textContent?.slice(0,90)")
        finding("training", "info", f"训练官点评: {t2}")
        c.eval(f"fetch('/api/sessions/{tid}/finish', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:'{{}}'}})")
        for _ in range(30):
            time.sleep(3)
            st = c.eval(f"(async()=>((await (await fetch('/api/sessions/{tid}')).json()).session.status))()")
            if st == "scored":
                break
        c.goto(BASE + "/session/" + tid)
        time.sleep(2)
        c.eval("document.querySelector('.result')?.scrollIntoView()")
        time.sleep(0.4)
        c.shot("12-training-summary.png")

        # ---- 5. 边界行为抽查 ----
        # 空回答发送
        c.eval(f"""fetch('/api/sessions/{tid}/continue', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:'{{}}'}}).then(r=>r.json()).then(d=>{{window.__c=d;}})""")
        time.sleep(20)
        c.eval("""(async () => {
          const ta = document.querySelector('#answer-input');
          if (ta) { ta.value = ''; ta.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true})); }
        })()""")
        time.sleep(1)
        # 双击发送（busy 中再发）
        c.eval("""(async () => {
          const ta = document.querySelector('#answer-input');
          if (ta) {
            ta.value = '双击测试';
            ta.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
            ta.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
          }
        })()""")
        time.sleep(1.5)
        dup = c.eval("document.querySelectorAll('.msg.me').length")
        finding("edge", "info", f"busy 中重复发送后我的消息数: {dup}")
        # 会话超限（面试已有1个+训练1个，建到11个面试会话太多——跳过，逻辑已测）
        # 重命名（内联）
        c.eval("location.href = '/'")
        time.sleep(2)
        c.eval("document.querySelector('[data-rename]')?.click()")
        time.sleep(0.5)
        has_input = c.eval("!!document.querySelector('.rename-input')")
        if not has_input:
            finding("ui", "medium", "点击重命名未出现内联输入框")
        else:
            c.eval("""(async () => {
              const inp = document.querySelector('.rename-input');
              inp.value = '改名测试会话';
              inp.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}));
            })()""")
            time.sleep(1.5)
        c.shot("13-home-after-rename.png")

        print("\n===== 截图目录:", SHOT_DIR)
    finally:
        c.close()

    with open(os.path.join(SHOT_DIR, "findings.json"), "w", encoding="utf-8") as f:
        json.dump(FINDINGS, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
