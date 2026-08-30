"""VC_Hero 全局配置。"""
import os

# 项目根目录（vc_hero 的上一级）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
STATIC_DIR = os.path.join(BASE_DIR, "static")
KEY_FILE = os.path.join(BASE_DIR, "kimi_api_key.txt")

# ---- 账号 / 简历 / 会话限制 ----
MAX_RESUMES_PER_USER = 5
RESUME_MAX_MB = 10
MAX_SESSIONS_PER_USER = 10
TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 登录态有效期
SESSION_COOKIE = "vc_session"

# 问题数量档位 -> (目标下限, 目标上限, 安全上限)；区间内具体题数由模型自行决定
LEVEL_RANGES = {"low": (10, 14, 18), "medium": (18, 22, 28), "high": (35, 45, 55)}
TASK_COUNT_MIN = 1
TASK_COUNT_MAX = 5
TIME_LIMIT_MAX_MIN = 180
TASK_TURNS_PER_TASK = 3  # 每个 task：场景引入 + 2 轮追问

# ---- Kimi ----
KIMI_BASE_URL = "https://api.moonshot.cn/v1"
KIMI_MODEL = "kimi-k3"
KIMI_TIMEOUT = 180
# kimi-k3 推理耗时过长，关闭推理（此时 API 要求 temperature=0.6）
KIMI_THINKING = {"type": "disabled"}
KIMI_TEMPERATURE = 0.6
MAX_REPLY_TOKENS = 2000
MAX_SCORING_TOKENS = 8000

# ---- 全局限速（对全部用户生效，负载共享）----
RATE_WINDOW_SECONDS = 3600
TOKEN_CAP_PER_HOUR = 150_000     # token/h
RESPONSE_CAP_PER_HOUR = 90       # response/h（一次 LLM 调用计 1 次 response）
COST_CAP_PER_HOUR_CNY = 2.0      # 每小时最多消耗 2 元人民币

# 计费估计（元 / 百万 token）。取保守偏高估计，保证成本上限可靠触发。
PRICE_INPUT_PER_M = 4.0
PRICE_OUTPUT_PER_M = 20.0

# AI 回复正式发出前的自我迭代轮数（恰好 N 轮）
SELF_REVIEW_ROUNDS = 2
