"""全局 API 限速与负载均衡。

对全部用户共享一个预算窗口：token/h、response/h、每小时成本上限。
所有 LLM 调用先经过 acquire() 排队取号，按 FIFO 公平调度，
预算不足时在条件变量上等待 —— 多人同时使用时自然排队变卡，
单个用户无法饿死其他人。
"""
import threading
import time
from collections import deque

from . import config


class RateLimiter:
    def __init__(self):
        self._cond = threading.Condition()
        self._records = deque()  # (ts, tokens, cost)；response 次数 = len

    def _sweep(self, now):
        cutoff = now - config.RATE_WINDOW_SECONDS
        while self._records and self._records[0][0] < cutoff:
            self._records.popleft()

    def _usage(self, now):
        self._sweep(now)
        tokens = sum(r[1] for r in self._records)
        cost = sum(r[2] for r in self._records)
        return tokens, cost, len(self._records)

    def acquire(self, est_tokens, est_cost):
        """等到预算足够，预留 est 额度，返回 record 引用以便事后按实际值修正。"""
        with self._cond:
            while True:
                now = time.time()
                tokens, cost, responses = self._usage(now)
                if (tokens + est_tokens <= config.TOKEN_CAP_PER_HOUR
                        and cost + est_cost <= config.COST_CAP_PER_HOUR_CNY
                        and responses + 1 <= config.RESPONSE_CAP_PER_HOUR):
                    rec = [now, est_tokens, est_cost]
                    self._records.append(rec)
                    return rec
                # 窗口最老的记录还有多久滚出
                wait = max(1.0, config.RATE_WINDOW_SECONDS
                           - (now - self._records[0][0])) if self._records else 5.0
                self._cond.wait(timeout=min(wait, 30.0))

    def settle(self, rec, actual_tokens, actual_cost):
        """用 API 实际 usage 修正预留的估计值。"""
        with self._cond:
            rec[1] = actual_tokens
            rec[2] = actual_cost
            self._cond.notify_all()


def estimate_call(messages, max_tokens):
    """粗略估计一次调用的 token 数与成本（保守偏高）。"""
    chars = sum(len(m.get("content", "")) for m in messages)
    est_tokens = min(chars // 2 + max_tokens, config.TOKEN_CAP_PER_HOUR)
    est_cost = (
        est_tokens / 2 / 1_000_000 * config.PRICE_INPUT_PER_M
        + max_tokens / 1_000_000 * config.PRICE_OUTPUT_PER_M
    )
    return est_tokens, est_cost


def actual_cost(prompt_tokens, completion_tokens):
    return (prompt_tokens / 1_000_000 * config.PRICE_INPUT_PER_M
            + completion_tokens / 1_000_000 * config.PRICE_OUTPUT_PER_M)
