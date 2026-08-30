"""真实 LLM 端到端测试：走完整面试流程（花费真实 API 额度）。

运行：python tests/real_flow_test.py
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.smoke_test import Client, make_pdf_bytes  # noqa: E402

BASE = "http://127.0.0.1:5000"


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def main():
    c = Client()
    d = c.req("POST", "/api/register", {"username": "realtest", "password": "pw123"})
    assert d.get("ok"), d
    log("注册成功")

    boundary = "----realtest"
    pdf = make_pdf_bytes()
    payload = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
               f"filename=\"cv_zhangsan.pdf\"\r\nContent-Type: application/pdf\r\n\r\n"
               .encode() + pdf + f"\r\n--{boundary}--\r\n".encode())
    r = urllib.request.Request(BASE + "/api/resumes", data=payload, method="POST")
    r.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    r.add_header("Cookie", c.cookie)
    d = json.loads(urllib.request.urlopen(r, timeout=30).read().decode())
    assert d.get("ok"), d
    rid = d["resume"]["id"]
    log(f"简历上传成功，抽出 {d['resume']['chars']} 字符")

    d = c.req("POST", "/api/sessions", {"name": "真实流程测试", "resume_id": rid,
                                        "level": "low", "task_count": 1,
                                        "time_limit_min": None})
    assert d.get("ok"), d
    sid = d["session"]["id"]
    log("会话创建成功")

    t0 = time.time()
    d = c.req("POST", f"/api/sessions/{sid}/start", {})
    assert d.get("ok"), d
    s = d["session"]
    log(f"面试开始，首个问题耗时 {time.time()-t0:.1f}s：")
    print("  考官:", s["messages"][-1]["content"][:200], flush=True)

    answers = [
        "这个社群是我大二时自己发起的。最开始只有 30 个人，是我从学院里一个个拉进来的，一年后发展到 500 人。",
        "增长主要靠每周一次的线下分享。我负责邀请嘉宾，前后联系了 60 多位行业人士，最后稳定合作的有 8 位。",
        "踩过的坑很多，比如早期办了一场 200 人的活动只来了 40 人。后来我改成先小范围验证主题再放大。",
    ]
    for i, a in enumerate(answers):
        t0 = time.time()
        d = c.req("POST", f"/api/sessions/{sid}/answer", {"content": a})
        assert d.get("ok"), d
        s = d["session"]
        log(f"第 {i+1} 次回答 -> phase={s['phase']} status={s['status']}，耗时 {time.time()-t0:.1f}s")
        print("  考官:", s["messages"][-1]["content"][:200], flush=True)

    t0 = time.time()
    d = c.req("POST", f"/api/sessions/{sid}/finish", {})
    assert d.get("ok"), d
    s = d["session"]
    log(f"结束并评分完成，耗时 {time.time()-t0:.1f}s")
    print(json.dumps(s["result"], ensure_ascii=False, indent=1), flush=True)
    log("全部完成 ✔")


if __name__ == "__main__":
    main()
