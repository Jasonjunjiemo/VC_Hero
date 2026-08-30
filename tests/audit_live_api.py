"""线上审查 part1：API 驱动全部数据流（可靠），输出会话 id 供 part2 截图检查。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests.smoke_test as st
st.BASE = "http://152.136.60.146"
from tests.smoke_test import Client, make_pdf_bytes  # noqa: E402
import urllib.request  # noqa: E402

BASE = "http://152.136.60.146"
OUT = {}


def main():
    c = Client()
    USER = "audit" + str(int(time.time()))[-6:]
    r = c.req("POST", "/api/register", {"username": USER, "password": "audit12345"})
    assert r.get("ok"), r
    OUT["user"] = USER
    print("注册:", USER, flush=True)
    me = c.req("GET", "/api/me")
    assert me.get("user"), f"cookie无效: {me}"
    print("cookie OK", flush=True)

    # 伪 PDF 应被拒绝
    boundary = "----audit"
    payload = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
               f"filename=\"fake.pdf\"\r\nContent-Type: application/pdf\r\n\r\n"
               .encode() + b"not a pdf" + f"\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(BASE + "/api/resumes", data=payload, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Cookie", c.cookie)
    try:
        urllib.request.urlopen(req, timeout=30)
        OUT["fake_pdf_rejected"] = False
        print("[瑕疵候选] 伪PDF未被拒绝", flush=True)
    except urllib.error.HTTPError:
        OUT["fake_pdf_rejected"] = True
        print("伪PDF已拒绝 OK", flush=True)

    # 真简历
    payload = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
               f"filename=\"cv_audit.pdf\"\r\nContent-Type: application/pdf\r\n\r\n"
               .encode() + make_pdf_bytes() + f"\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(BASE + "/api/resumes", data=payload, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Cookie", c.cookie)
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    assert d.get("ok"), d
    rid = d["resume"]["id"]
    print("简历上传 OK", flush=True)

    # 面试：开始 → 3 答 → 结束 → 继续 → 1 答
    sid = c.req("POST", "/api/sessions", {"kind": "interview", "name": "审查面试",
                "resume_id": rid, "level": "low", "task_count": 1,
                "time_limit_min": None})["session"]["id"]
    OUT["interview_sid"] = sid
    d = c.req("POST", f"/api/sessions/{sid}/start", {})
    print("Q1:", d["session"]["messages"][-1]["content"][:70], flush=True)
    for i, a in enumerate([
        "最开始逐个邀请熟人，前100人来自同学和室友。",
        "后来靠每周分享会增长，我联系了68位嘉宾，稳定合作15位。",
        "踩过的坑是早期活动来的人少，后来先小范围验证主题再放大。",
    ]):
        t0 = time.time()
        d = c.req("POST", f"/api/sessions/{sid}/answer", {"content": a})
        print(f"Q{i+2} ({time.time()-t0:.0f}s):", d["session"]["messages"][-1]["content"][:70], flush=True)
    t0 = time.time()
    d = c.req("POST", f"/api/sessions/{sid}/finish", {})
    OUT["grade1"] = d["session"]["result"]["grade"]
    OUT["total1"] = d["session"]["result"]["total"]
    print(f"评分1 ({time.time()-t0:.0f}s):", OUT["grade1"], OUT["total1"], flush=True)

    d = c.req("POST", f"/api/sessions/{sid}/continue", {})
    print("继续后考官:", d["session"]["messages"][-1]["content"][:80], flush=True)
    OUT["continued_msg"] = d["session"]["messages"][-1]["content"][:40]
    d = c.req("POST", f"/api/sessions/{sid}/answer", {"content": "嘉宾主要靠往期讲者推荐和 LinkedIn 冷触达。"})
    print("续聊追问:", d["session"]["messages"][-1]["content"][:70], flush=True)

    # 训练：粘贴上下文 → 开场 → 1 答 → 总结
    tid = c.req("POST", "/api/sessions", {"kind": "training", "name": "审查训练",
                "context_type": "text",
                "context_text": "我面试中被指出不会判断渠道优先级，也不擅长长期跟踪 founder。",
                "context_label": "粘贴文本"})["session"]["id"]
    OUT["training_tid"] = tid
    d = c.req("POST", f"/api/sessions/{tid}/start", {})
    print("训练开场:", d["session"]["messages"][-1]["content"][:80], flush=True)
    d = c.req("POST", f"/api/sessions/{tid}/answer", {"content": "我会先列出候选渠道，再按转化率排序。"})
    print("训练点评:", d["session"]["messages"][-1]["content"][:80], flush=True)
    d = c.req("POST", f"/api/sessions/{tid}/finish", {})
    OUT["summary_head"] = d["session"]["result"]["summary"][:60]
    print("总结:", OUT["summary_head"], flush=True)

    # 训练导入面试记录（含多次结果的场景：再让面试出第二份结果太贵，用当前单结果导入验证）
    d = c.req("POST", "/api/sessions", {"kind": "training", "name": "审查导入",
                "context_type": "session", "context_session_id": sid})
    if d.get("ok"):
        print("导入面试记录 OK label:", d["session"]["context_label"], flush=True)
        OUT["import_tid"] = d["session"]["id"]
    else:
        print("[瑕疵候选] 导入失败:", d, flush=True)

    # token 保存供 part2 使用
    token = c.cookie.split("=", 1)[1]
    OUT["token"] = token
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_audit_state.json"), "w", encoding="utf-8") as f:
        json.dump(OUT, f, ensure_ascii=False)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
