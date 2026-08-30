"""端到端冒烟测试：用 stub 替换 Kimi 客户端，验证账号/简历/会话/面试状态机全流程。

运行：python tests/smoke_test.py
"""
import io
import json
import os
import sys
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vc_hero import create_app  # noqa: E402

BASE = "http://127.0.0.1:5000"


class StubClient:
    """模拟 Kimi：固定回复，验证状态机不需真实 API。"""

    n = 0

    def interviewer_reply(self, system_prompt, history):
        StubClient.n += 1
        return f"【问题{StubClient.n}】请具体讲讲你在某项目里做了什么？"

    def score_interview(self, system_prompt, transcript):
        return {
            "scores": {"task_understanding": 80, "signal_identification": 75,
                       "prioritization": 70, "judgment_update": 72,
                       "decision_expression": 74},
            "total": 74.2, "grade": "C",
            "feedback": "总体判断：基础尚可但稳定性不足。\n优势：回答具体。\n问题：取舍能力欠缺。\n建议：加强取舍训练。",
        }


def make_pdf_bytes():
    """手工构造一个含文本流的最小 PDF。"""
    text = "Zhang San. Tsinghua University. Built an AI community with 500 members. Led BD outreach to 30 companies."
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n{body}\nendobj\n".encode())
    xref = out.tell()
    out.write(f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return out.getvalue()


class Client:
    def __init__(self):
        self.cookie = ""

    def req(self, method, path, body=None, raw=False):
        data = None if body is None else (body if raw else json.dumps(body).encode())
        r = urllib.request.Request(BASE + path, data=data, method=method)
        r.add_header("Content-Type", "application/json")
        if self.cookie:
            r.add_header("Cookie", self.cookie)
        try:
            resp = urllib.request.urlopen(r, timeout=600)
            sc = resp.headers.get("Set-Cookie")
            if sc:
                self.cookie = sc.split(";")[0]
            return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return json.loads(e.read().decode())


def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok - {msg}")


def main():
    app = create_app()
    app.extensions["kimi_client"] = StubClient()
    import threading
    threading.Thread(target=lambda: app.run(port=5001, threaded=True, use_reloader=False),
                     daemon=True).start()
    import time
    time.sleep(1.5)
    global BASE
    BASE = "http://127.0.0.1:5001"
    c = Client()

    print("[1] 注册与登录")
    d = c.req("POST", "/api/register", {"username": "tester", "password": "pw123"})
    expect(d.get("ok"), "注册成功并自动登录")
    me = c.req("GET", "/api/me")
    expect(me["user"]["username"] == "tester", "登录态有效")
    d = c.req("POST", "/api/register", {"username": "tester", "password": "x"})
    expect("error" in d, "重复用户名被拒绝")

    print("[2] 个人信息")
    d = c.req("PUT", "/api/profile", {"name": "张三", "org": "某大学"})
    expect(d["user"]["profile"]["name"] == "张三", "资料保存")

    print("[3] 简历上传")
    pdf = make_pdf_bytes()
    boundary = "----testboundary"
    payload = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
               f"filename=\"cv.pdf\"\r\nContent-Type: application/pdf\r\n\r\n"
               .encode() + pdf + f"\r\n--{boundary}--\r\n".encode())
    r = urllib.request.Request(BASE + "/api/resumes", data=payload, method="POST")
    r.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    r.add_header("Cookie", c.cookie)
    d = json.loads(urllib.request.urlopen(r, timeout=30).read().decode())
    expect(d.get("ok") and d["resume"]["chars"] > 20, "PDF 上传并抽出文本")
    rid = d["resume"]["id"]
    # 非 PDF 拒绝
    r = urllib.request.Request(BASE + "/api/resumes",
                               data=f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"x.txt\"\r\n\r\nhello\r\n--{boundary}--\r\n".encode(),
                               method="POST")
    r.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    r.add_header("Cookie", c.cookie)
    try:
        urllib.request.urlopen(r, timeout=30)
        expect(False, "非 PDF 应被拒绝")
    except urllib.error.HTTPError:
        expect(True, "非 PDF 被拒绝")

    print("[4] 会话管理")
    d = c.req("POST", "/api/sessions", {"name": "测试会话", "resume_id": rid,
                                        "level": "low", "task_count": 1,
                                        "time_limit_min": None})
    expect(d.get("ok"), "创建会话")
    sid = d["session"]["id"]
    expect(d["session"]["cv_total"] == 3, "low 档位 = 3 题")
    d = c.req("POST", "/api/sessions", {"name": "x", "resume_id": "bad",
                                        "level": "low", "task_count": 1})
    expect("error" in d, "无效简历被拒绝")
    d = c.req("POST", "/api/sessions", {"name": "x", "resume_id": rid,
                                        "level": "low", "task_count": 9})
    expect("error" in d, "task_count 越界被拒绝")
    d = c.req("PUT", f"/api/sessions/{sid}", {"name": "改名后"})
    expect(d["session"]["name"] == "改名后", "重命名会话")

    print("[5] 面试流程（low=3 题 + 1 任务×3 回合 = 6 轮）")
    d = c.req("POST", f"/api/sessions/{sid}/start", {})
    expect(d["session"]["status"] == "active", "面试开始")
    expect(len(d["session"]["messages"]) == 1, "考官提出第 1 个问题")

    # 答满 3 个 CV 问题
    for i in range(3):
        d = c.req("POST", f"/api/sessions/{sid}/answer", {"content": f"我的回答{i+1}"})
    msgs = d["session"]["messages"]
    expect(d["session"]["phase"] == "task", "3 题后进入 task 阶段")
    expect(len([m for m in msgs if m["role"] == "interviewer"]) == 4, "task 场景已布置")

    # 连答导致越界：再次 answer 前不能重复答
    d2 = c.req("POST", f"/api/sessions/{sid}/answer", {"content": "任务回答1"})
    expect(len(d2["session"]["messages"]) == len(msgs) + 2, "任务回合推进")

    # 一次性答完剩余回合并触发评分
    d = c.req("POST", f"/api/sessions/{sid}/answer", {"content": "任务回答2"})
    d = c.req("POST", f"/api/sessions/{sid}/answer", {"content": "任务回答3"})
    expect(d["session"]["status"] == "scored", "回合耗尽自动评分")
    res = d["session"]["result"]
    expect(res["grade"] == "C" and res["total"] == 74.2, "评级与分数正确")
    expect(len(res["feedback"]) > 10, "反馈非空")

    # 结束后不能再答
    d = c.req("POST", f"/api/sessions/{sid}/answer", {"content": "还能答吗"})
    expect("error" in d, "结束后禁止回答")

    print("[6] 删除")
    d = c.req("DELETE", f"/api/sessions/{sid}")
    expect(d.get("ok"), "删除会话")
    d = c.req("DELETE", f"/api/resumes/{rid}")
    expect(d.get("ok"), "删除简历")

    print("\n全部通过 ✔")


if __name__ == "__main__":
    main()
