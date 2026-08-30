"""AI 训练官引擎：场景式自由训练。

与面试引擎共用会话存储、锁与 LLM 客户端，但流程不同：
  开始 -> 训练官布置第一个场景 -> 学员作答 -> 训练官点评/教学/推进（自由回合）
  手动结束 -> 生成训练总结（无评级打分）。
"""
import time

from . import prompts, storage
from .interview import InterviewError, _history, _session_lock
from .kimi import KimiError

REVIEW_PROMPT = "Training_Reply_Self_Review"


def _get(user_id, session_id):
    s = storage.get_session(user_id, session_id)
    if not s:
        raise InterviewError("会话不存在")
    return s


def _check_kind(s):
    if s.get("kind", "interview") != "training":
        raise InterviewError("该会话不是训练会话")


def build_system_prompt(s):
    guide = prompts.load_prompt("Training_Guide_Rules")
    if s.get("context_type") == "text":
        guide += ("\n\n===== 学员提供的背景材料 =====\n" + s.get("context_text", "")
                  + "\n请结合这份材料定制训练重点。")
    elif s.get("context_type") == "session":
        guide += ("\n\n===== 学员的历史面试记录（含完整对话、评级与反馈）=====\n"
                  + s.get("context_text", "")
                  + "\n请针对该记录中暴露的薄弱环节设计训练重点。")
    return guide


def _next(client, s):
    try:
        reply = client.generate_reply(build_system_prompt(s), _history(s),
                                      review_prompt=REVIEW_PROMPT)
    except KimiError as e:
        raise InterviewError(f"AI 服务暂时不可用，请稍后重试（{e}）")
    s["messages"].append({"role": "interviewer", "content": reply,
                          "ts": time.time()})
    storage.save_session(s)
    return s


def start_session(client, user_id, session_id):
    with _session_lock(session_id):
        s = _get(user_id, session_id)
        _check_kind(s)
        if s["status"] == "scored":
            raise InterviewError("训练已结束")
        if s["status"] == "active":
            raise InterviewError("训练已在进行中")
        s["status"] = "active"
        s["started_at"] = time.time()
        storage.save_session(s)
        try:
            return _next(client, s)
        except Exception:
            s["status"] = "created"
            s["started_at"] = None
            storage.save_session(s)
            raise


def answer(client, user_id, session_id, content):
    content = (content or "").strip()
    if not content:
        raise InterviewError("内容不能为空")
    if len(content) > 20000:
        raise InterviewError("内容过长")
    with _session_lock(session_id):
        s = _get(user_id, session_id)
        _check_kind(s)
        if s["status"] == "scored":
            raise InterviewError("训练已结束")
        if s["messages"] and s["messages"][-1]["role"] == "candidate":
            raise InterviewError("请等待训练官的回复")
        s["messages"].append({"role": "candidate", "content": content,
                              "ts": time.time()})
        return _next(client, s)


def finish(client, user_id, session_id):
    with _session_lock(session_id):
        s = _get(user_id, session_id)
        _check_kind(s)
        if s["status"] == "scored":
            return s
        if s["status"] == "created":
            raise InterviewError("训练尚未开始")
        s["status"] = "scored"
        s["ended_at"] = time.time()
        transcript = "\n\n".join(
            ("【训练官】" if m["role"] == "interviewer" else "【学员】") + m["content"]
            for m in s["messages"]
        )
        system = (build_system_prompt(s)
                  + "\n\n===== 训练结束指令（最高优先级，覆盖以上所有设定）=====\n"
                  + "训练已经正式结束。你现在必须完全脱离训练官角色：不要再布置场景、"
                    "不要等待学员回答、不要用对话口吻回应、不要评论最后一条消息。"
                    "你的唯一任务是基于完整训练记录写一份训练总结，必须包含三部分："
                    "1) 学员的进步；2) 主要问题（引用学员的具体回答作为证据）；"
                    "3) 下一步最应该练的具体场景建议。"
                    "直接输出总结正文，不要加标题、前缀或称呼。")
        try:
            summary = client.chat(
                [{"role": "system", "content": system},
                 {"role": "user", "content": "以下是本次训练的完整记录：\n\n" + transcript}],
                3000)
        except Exception as e:
            s["status"] = "active"
            storage.save_session(s)
            raise InterviewError(f"生成训练总结失败：{e}")
        s["result"] = {"summary": summary}
        storage.save_session(s)
        return s
