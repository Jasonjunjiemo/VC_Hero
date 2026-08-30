"""Kimi 开放平台 API 客户端。

- 每次调用经过全局 RateLimiter（token/h、response/h、¥2/h 上限，FIFO 公平排队）
- 面试官的每条回复在正式发出前，先按 Reply_Self_Review.md 自我迭代恰好 2 轮
"""
import json
import time
import urllib.error
import urllib.request

from . import config, prompts, ratelimit


class KimiError(Exception):
    pass


class KimiClient:
    def __init__(self, api_key, limiter):
        self.api_key = api_key
        self.limiter = limiter

    def chat(self, messages, max_tokens, response_format=None, retries=4):
        payload = {
            "model": config.KIMI_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.6,
        }
        if response_format:
            payload["response_format"] = response_format

        est_tokens, est_cost = ratelimit.estimate_call(messages, max_tokens)
        rec = self.limiter.acquire(est_tokens, est_cost)
        done = False
        try:
            for attempt in range(retries + 1):
                try:
                    text, prompt_tokens, completion_tokens = self._call(payload)
                    self.limiter.settle(
                        rec, prompt_tokens + completion_tokens,
                        ratelimit.actual_cost(prompt_tokens, completion_tokens))
                    done = True
                    return text
                except KimiError as e:
                    if attempt >= retries or "429" not in str(e):
                        raise
                    time.sleep(min(2 ** attempt * 3, 30))
        finally:
            if not done:
                # 调用失败：移除预留记录，避免额度泄漏
                with self.limiter._cond:
                    try:
                        self.limiter._records.remove(rec)
                    except ValueError:
                        pass
                    self.limiter._cond.notify_all()

    def _call(self, payload):
        req = urllib.request.Request(
            config.KIMI_BASE_URL + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer " + self.api_key,
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=config.KIMI_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise KimiError(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")
        except (urllib.error.URLError, TimeoutError) as e:
            raise KimiError(f"网络错误: {e}")

        usage = data.get("usage", {})
        text = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        if not text:
            raise KimiError("API 返回空内容")
        return (text,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0))

    # ---------------- 面试官回复：生成 + 恰好 2 轮自我迭代 ----------------

    def interviewer_reply(self, system_prompt, history):
        """生成面试官回复。草稿先生成，再迭代恰好 SELF_REVIEW_ROUNDS 轮，最后一版才发出。"""
        review_prompt = prompts.load_prompt("Reply_Self_Review")

        draft = self.chat(
            [{"role": "system", "content": system_prompt}] + history,
            config.MAX_REPLY_TOKENS,
        )
        reply = draft
        for _ in range(config.SELF_REVIEW_ROUNDS):
            reply = self._review_once(review_prompt, system_prompt, history, reply)
        return reply

    def _review_once(self, review_prompt, system_prompt, history, draft):
        ctx = (
            review_prompt
            + "\n\n===== 面试官系统提示词（仅供你理解语境）=====\n" + system_prompt
            + "\n\n===== 面试对话历史 =====\n"
            + "\n".join(f"{m['role']}: {m['content']}" for m in history)
            + "\n\n===== 待改进的面试官回复草稿 =====\n" + draft
            + "\n\n请输出改进后的回复全文。"
        )
        return self.chat([{"role": "user", "content": ctx}], config.MAX_REPLY_TOKENS)

    # ---------------- 终场评分 ----------------

    def score_interview(self, system_prompt, transcript):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "以下是本次面试完整记录：\n\n" + transcript},
        ]
        raw = self.chat(messages, config.MAX_SCORING_TOKENS,
                        response_format={"type": "json_object"})
        return _parse_json(raw)


def _parse_json(raw):
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise KimiError(f"评分结果不是合法 JSON: {raw[:200]}")
    return json.loads(text[start:end + 1])
