"""面试引擎：会话状态机与两阶段流转。

流程：
  阶段一（cv）：基于简历提问 cv_total 个问题，一问一答。
  阶段二（task）：逐个进入所选场景任务，每个任务 TASK_TURNS_PER_TASK 个回合。
  问题耗尽 / 到时 / 用户手动结束 -> 按 Interview_Scoring_Rules.md 评分，给出 A-E 评级与反馈。

每个会话一个互斥锁，保证"考生只能回答一次、考官问完才答"的严格轮转。
"""
import random
import threading
import time

from . import config, prompts, storage
from .kimi import KimiError

_locks = {}
_locks_guard = threading.Lock()


def _session_lock(session_id):
    with _locks_guard:
        return _locks.setdefault(session_id, threading.Lock())


class InterviewError(Exception):
    pass


# 模型决定结束简历阶段时输出在回复末尾的标记（对考生不可见）
CV_DONE_MARKER = "[[CV_DONE]]"


def _strip_marker(reply):
    """剥离阶段结束标记，返回 (清理后的回复, 是否含标记)。"""
    if CV_DONE_MARKER in reply:
        cleaned = reply.replace(CV_DONE_MARKER, "").rstrip()
        return (cleaned or reply), True
    return reply, False


def _time_expired(s):
    if not s.get("time_limit_min") or not s.get("started_at"):
        return False
    return time.time() > s["started_at"] + s["time_limit_min"] * 60


def pick_tasks(task_count):
    """从 Task_Scenarios.md 中随机选取不重复的 N 个场景。"""
    pool = prompts.list_task_scenarios()
    if len(pool) < task_count:
        raise InterviewError("可用任务场景数量不足")
    return random.sample(pool, task_count)


def _build_system_prompt(s, resume_text):
    orch = prompts.load_prompt("Interview_Orchestrator")

    if s["phase"] == "cv":
        phase_rules = prompts.load_prompt("CV_Evaluation_and_Questioning_Rules")
        phase_desc = (
            f"当前处于阶段一【简历问答】，本阶段计划提问约 {s['cv_target_min']}-{s['cv_target_max']} 个，"
            "具体数量由你根据面试进程自行决定，不必机械地问满。"
            "请针对候选人简历继续提出下一个问题，深入挖掘最值得追问的经历，不要泛泛而谈。"
            "当你决定结束本阶段时：本条回复先对阶段一做一两句简短总结、不要再提问，"
            f"然后在回复末尾单独一行输出标记 {CV_DONE_MARKER}。"
            f"除末尾标记外，不要在回复任何其他位置输出 {CV_DONE_MARKER}。"
        )
        scenario = ""
    else:
        phase_rules = prompts.load_prompt("Deal_Sourcing_Knowhow_Task_and_Questioning")
        task_name, task_text = s["tasks"][s["task_index"]]
        if s["task_turns"] == 0:
            phase_desc = (
                f"当前进入阶段二【行业 Know-how 场景任务】的第 {s['task_index'] + 1}/{len(s['tasks'])} 个任务"
                f"（{task_name}）。请自然地向候选人布置以下任务场景并提出第一个问题：\n{task_text}"
            )
        else:
            phase_desc = (
                f"当前处于阶段二【行业 Know-how 场景任务】，任务（{task_name}）进行中。"
                "请根据候选人上一轮回答继续深入追问同一个场景，"
                "接近本任务尾声时在合适的问题后自然收束，不要生硬地宣布结束。"
            )
        scenario = task_text

    return (
        orch
        + "\n\n===== 当前阶段指令 =====\n" + phase_desc
        + ("\n\n===== 当前任务场景原文 =====\n" + scenario if scenario else "")
        + "\n\n===== 候选人简历 =====\n" + resume_text
        + "\n\n===== 本阶段提问规则 =====\n" + phase_rules
    )


def _history(s):
    # Kimi API 只接受 system/user/assistant 角色
    return [{"role": "assistant" if m["role"] == "interviewer" else "user",
             "content": m["content"]} for m in s["messages"]]


def start_session(client, user_id, session_id):
    """开始面试：同步生成第一个问题（HTTP 响应直接携带，前端无需轮询）。"""
    with _session_lock(session_id):
        s = _get_active(user_id, session_id)
        if s["status"] == "scored":
            raise InterviewError("面试已结束")
        if s["status"] == "active":
            raise InterviewError("面试已在进行中")
        if not s["tasks"]:
            s["tasks"] = pick_tasks(s["task_count"])
        s["status"] = "active"
        s["started_at"] = time.time()
        storage.save_session(s)
        return _ask_next(client, s)


def answer(client, user_id, session_id, content):
    """考生提交一次回答，推进面试。"""
    content = (content or "").strip()
    if not content:
        raise InterviewError("回答不能为空")
    if len(content) > 20000:
        raise InterviewError("回答过长")

    with _session_lock(session_id):
        s = _get_active(user_id, session_id)
        if s["status"] == "scored":
            raise InterviewError("面试已结束")
        # 严格一问一答：必须轮到考生回答
        if s["messages"] and s["messages"][-1]["role"] == "candidate":
            raise InterviewError("请等待考官的下一个问题")
        if _time_expired(s):
            return finish(client, user_id, session_id)

        s["messages"].append({"role": "candidate", "content": content,
                              "ts": time.time()})
        if s["phase"] == "cv":
            s["cv_asked"] += 1

        if _time_expired(s):
            return finish(client, user_id, session_id)
        return _ask_next(client, s)


def finish(client, user_id, session_id):
    """结束面试并评分。"""
    with _session_lock(session_id):
        s = _get_active(user_id, session_id)
        if s["status"] == "scored":
            return s
        if s["status"] == "created":
            raise InterviewError("面试尚未开始")
        return _score(client, s)


def _get_active(user_id, session_id):
    s = storage.get_session(user_id, session_id)
    if not s:
        raise InterviewError("会话不存在")
    return s


def _ask_next(client, s):
    """决定下一步：继续提问还是进入评分，并生成面试官回复（经 2 轮自我迭代）。

    简历阶段结束有两种触发：模型在回复末尾输出 [[CV_DONE]] 标记（模型自行决定题数），
    或答题数达到安全上限（防止模型忘记收尾）。
    """
    while True:
        if s["phase"] == "cv" and s["cv_asked"] >= s["cv_cap"]:
            if s["task_index"] >= len(s["tasks"]):
                return _score(client, s)
            s["phase"] = "task"
            s["task_turns"] = 0
            continue
        if s["phase"] == "task" and s["task_turns"] >= config.TASK_TURNS_PER_TASK:
            s["task_index"] += 1
            s["task_turns"] = 0
            if s["task_index"] >= len(s["tasks"]):
                return _score(client, s)
            continue
        break

    resume_text = storage.get_resume_text(s["user_id"], s["resume_id"]) or ""
    system_prompt = _build_system_prompt(s, resume_text)
    try:
        reply = client.interviewer_reply(system_prompt, _history(s))
    except KimiError as e:
        raise InterviewError(f"AI 服务暂时不可用，请稍后重试（{e}）")
    reply, cv_done = _strip_marker(reply)

    s["messages"].append({"role": "interviewer", "content": reply,
                          "ts": time.time()})
    if s["phase"] == "cv":
        s["cv_asked"] += 1
        storage.save_session(s)
        if cv_done:
            # 模型主动收尾：若无剩余任务则直接评分，否则立即布置任务开场
            if s["task_index"] >= len(s["tasks"]):
                return _score(client, s)
            s["phase"] = "task"
            s["task_turns"] = 0
            return _ask_next(client, s)
        return s
    s["task_turns"] += 1
    storage.save_session(s)
    return s


def _score(client, s):
    s["status"] = "scored"
    s["ended_at"] = time.time()
    transcript = "\n\n".join(
        ("【面试官】" if m["role"] == "interviewer" else "【候选人】") + m["content"]
        for m in s["messages"]
    )
    system_prompt = (prompts.load_prompt("Interview_Scoring_Rules")
                     + "\n\n===== 输出格式要求 =====\n"
                     + prompts.load_prompt("Scoring_Output_Format"))
    try:
        result = client.score_interview(system_prompt, transcript)
    except Exception as e:
        s["status"] = "active"  # 评分失败，允许重试
        storage.save_session(s)
        raise InterviewError(f"评分失败：{e}")

    s["result"] = {
        "scores": result.get("scores", {}),
        "total": result.get("total"),
        "grade": result.get("grade", ""),
        "feedback": result.get("feedback", ""),
    }
    storage.save_session(s)
    return s
