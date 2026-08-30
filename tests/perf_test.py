"""性能测试：对本地实例执行真实测量，结果写入 tests/_perf_result.json。

覆盖：
  A. 静态/轻量端点延迟（串行 100 次，p50/p95/max）
  B. 认证 API 延迟（会话列表等）
  C. 并发能力（30 线程混合读请求）
  D. 服务端渲染会话页延迟
  E. AI 一轮回复延迟（真实 Kimi，3 次调用链）
"""
import json
import statistics
import sys
import threading
import time
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests.smoke_test as st  # noqa: E402
st.BASE = "http://127.0.0.1:5000"
from tests.smoke_test import Client  # noqa: E402

RESULT = {}


def bench(name, fn, n=100):
    lat = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        lat.append((time.perf_counter() - t0) * 1000)
    r = {
        "n": n,
        "p50": round(statistics.median(lat), 1),
        "p95": round(sorted(lat)[int(n * 0.95) - 1], 1),
        "max": round(max(lat), 1),
        "mean": round(statistics.mean(lat), 1),
    }
    RESULT[name] = r
    print(name, r, flush=True)
    return r


def main():
    c = Client()
    r = c.req("POST", "/api/register", {"username": "perf" + str(int(time.time()))[-5:],
                                        "password": "pw123"})
    assert r.get("ok"), r
    print("测试账号就绪", flush=True)

    # A. 轻量端点
    import urllib.request
    def get(path):
        urllib.request.urlopen("http://127.0.0.1:5000" + path, timeout=30).read()
    bench("A1 GET / 首页(SSR模板)", lambda: get("/"))
    bench("A2 GET /static/app.js", lambda: get("/static/app.js"))
    bench("A3 GET /api/health", lambda: get("/api/health"))

    # B. 认证 API
    bench("B1 GET /api/me", lambda: c.req("GET", "/api/me"), n=100)
    bench("B2 GET /api/sessions?kind=interview",
          lambda: c.req("GET", "/api/sessions?kind=interview"), n=100)

    # D. 服务端渲染会话页（先造一个 active 会话）
    tsid = c.req("POST", "/api/sessions", {"kind": "training", "name": "perf渲染测量",
                                           "context_type": "none"})["session"]["id"]
    c.req("POST", f"/api/sessions/{tsid}/start", {})   # 真实LLM，顺便给E预热
    bench("D1 GET /session/<id> (SSR首屏)", lambda: get("/session/" + tsid), n=50)

    # C. 并发：30 线程 x 20 次混合读
    def worker(res, path):
        for _ in range(20):
            t0 = time.perf_counter()
            get(path)
            res.append((time.perf_counter() - t0) * 1000)
    for label, path in [("C1 并发 GET /api/health", "/api/health"),
                        ("C2 并发 GET / (SSR)", "/")]:
        res, threads = [], []
        t0 = time.perf_counter()
        for _ in range(30):
            th = threading.Thread(target=worker, args=(res, path))
            threads.append(th)
            th.start()
        for th in threads:
            th.join()
        wall = time.perf_counter() - t0
        RESULT[label] = {
            "threads": 30, "requests": len(res), "wall_s": round(wall, 2),
            "req_per_s": round(len(res) / wall, 1),
            "p50": round(statistics.median(res), 1),
            "p95": round(sorted(res)[int(len(res) * 0.95) - 1], 1),
        }
        print(label, RESULT[label], flush=True)

    # E. AI 一轮回复延迟（真实 Kimi，生成+2轮自检 = 3 次调用）
    lat = []
    for _ in range(2):
        t0 = time.perf_counter()
        c.req("POST", f"/api/sessions/{tsid}/answer", {"content": "我会先按转化率给渠道排序。"})
        lat.append(time.perf_counter() - t0)
    RESULT["E1 AI一轮回复(生成+2轮自检)"] = {
        "n": len(lat),
        "mean_s": round(statistics.mean(lat), 1),
        "min_s": round(min(lat), 1),
        "max_s": round(max(lat), 1),
    }
    print("E1", RESULT["E1 AI一轮回复(生成+2轮自检)"], flush=True)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_perf_result.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(RESULT, f, ensure_ascii=False, indent=1)
    print("DONE ->", out, flush=True)


if __name__ == "__main__":
    main()
