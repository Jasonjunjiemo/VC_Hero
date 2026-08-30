"""prompts 文件夹中的 md 提示词加载。所有 prompt 必须放在 prompts/，不写死在代码里。"""
import os

from . import config


def load_prompt(name):
    """按文件名（不含 .md）加载 prompts 目录下的提示词。"""
    path = os.path.join(config.PROMPTS_DIR, name + ".md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def list_task_scenarios():
    """从 Task_Scenarios.md 解析可选任务场景列表。

    格式：每个场景占一段，以 "名称｜场景描述" 的形式书写。
    返回 [(name, scenario_text), ...]
    """
    raw = load_prompt("Task_Scenarios")
    scenarios = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block or "｜" not in block:
            continue
        name, _, text = block.partition("｜")
        scenarios.append((name.strip(), text.strip().replace("\n", " ")))
    return scenarios
