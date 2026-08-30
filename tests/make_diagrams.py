"""绘制原型图（页面线框）与架构图，输出 PNG 到 docs/diagrams/。"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "docs", "diagrams")
os.makedirs(OUT, exist_ok=True)

BG = "#f6f7fa"
CARD = "#ffffff"
LINE = "#c9cede"
INK = "#1a2233"
BRAND = "#4656e0"
GREEN = "#159a6c"
BLUE2 = "#4a7fd4"
GRAY = "#8a94a6"


def box(ax, x, y, w, h, fc=CARD, ec=LINE, lw=1.2, r=0.008):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=fc, ec=ec, lw=lw, mutation_aspect=1))


def txt(ax, x, y, s, size=9, color=INK, ha="left", weight="normal"):
    ax.text(x, y, s, fontsize=size, color=color, ha=ha, va="center", weight=weight)


def wire_page(title):
    fig, ax = plt.subplots(figsize=(10, 6.4), dpi=150)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor(BG)
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, fc=BG, ec="none"))
    txt(ax, 0.02, 0.965, title, size=13, weight="bold")
    return fig, ax


# ---------- 原型 1：主页 ----------
fig, ax = wire_page("原型图 1 · 主页（AI 面试官 / AI 训练官 双 Tab）")
# 浮动控件
box(ax, 0.02, 0.885, 0.10, 0.045)
txt(ax, 0.07, 0.907, "[VC] Hero", size=8, ha="center", weight="bold")
box(ax, 0.80, 0.885, 0.09, 0.045); txt(ax, 0.845, 0.907, "用户名", size=7.5, ha="center")
box(ax, 0.90, 0.885, 0.07, 0.045); txt(ax, 0.935, 0.907, "退出", size=7.5, ha="center")
# tab 切换
box(ax, 0.36, 0.83, 0.13, 0.04, fc="#e9ecf5"); txt(ax, 0.425, 0.85, "AI 面试官", size=8, ha="center", weight="bold", color=BRAND)
box(ax, 0.50, 0.83, 0.13, 0.04, fc="#e9ecf5"); txt(ax, 0.565, 0.85, "AI 训练官", size=8, ha="center", color=GRAY)
# hero
box(ax, 0.03, 0.52, 0.94, 0.27, fc="#2c3a8c", ec="none")
txt(ax, 0.06, 0.745, "AI 面试陪练 · 早期 VC Deal Sourcing", size=8, color="#c3cbff")
txt(ax, 0.06, 0.69, "在真正的面试之前，先在这里输一次", size=13, color="white", weight="bold")
txt(ax, 0.06, 0.63, "VC Hero 是一位 AI 虚拟面试官……结束后给出 A-E 评级和具体反馈。", size=8, color="#cdd4f5")
box(ax, 0.06, 0.545, 0.14, 0.045, fc=BRAND, ec="none"); txt(ax, 0.13, 0.567, "立即开始模拟面试", size=8, color="white", ha="center", weight="bold")
box(ax, 0.72, 0.545, 0.22, 0.225, fc="white", ec="none"); txt(ax, 0.83, 0.655, "插图\n(人物+气泡+评分卡)", size=8, color=GRAY, ha="center")
# 会话面板
box(ax, 0.03, 0.20, 0.94, 0.29)
txt(ax, 0.05, 0.455, "面试会话 (2/10)", size=9, weight="bold")
box(ax, 0.85, 0.435, 0.10, 0.04, fc=BRAND, ec="none"); txt(ax, 0.90, 0.455, "新建会话", size=7.5, color="white", ha="center")
for i, (name, badge) in enumerate([("第一次模拟面试  [已完成] [评级 B]", "#e6f6ef"),
                                   ("sourcing 训练  [进行中]", "#eef0fd")]):
    y = 0.385 - i * 0.085
    box(ax, 0.05, y, 0.90, 0.07)
    txt(ax, 0.07, y + 0.035, name, size=8)
    box(ax, 0.79, y + 0.015, 0.05, 0.04, fc=badge, ec="none"); txt(ax, 0.815, y + 0.035, "重命名", size=6.5, ha="center")
    box(ax, 0.85, y + 0.015, 0.05, 0.04, fc="#fdeeed", ec="none"); txt(ax, 0.875, y + 0.035, "删除", size=6.5, ha="center")
    box(ax, 0.91, y + 0.015, 0.04, 0.04, fc=BRAND, ec="none"); txt(ax, 0.93, y + 0.035, "进入", size=6.5, color="white", ha="center")
txt(ax, 0.05, 0.20, "功能卡片区（简历深挖 / 场景任务 / 评级反馈）…", size=7.5, color=GRAY)
fig.savefig(os.path.join(OUT, "proto1_home.png"), bbox_inches="tight", facecolor=BG)
plt.close(fig)

# ---------- 原型 2：面试对话页 ----------
fig, ax = wire_page("原型图 2 · 面试对话页（含结果速览侧边栏）")
# 浮动控件
box(ax, 0.02, 0.885, 0.07, 0.045); txt(ax, 0.055, 0.907, "‹ 返回", size=7.5, ha="center")
box(ax, 0.60, 0.885, 0.37, 0.045); txt(ax, 0.785, 0.907, "会话名   不限时   [结束面试]", size=7.5, ha="center")
# 侧边栏
box(ax, 0.955, 0.44, 0.030, 0.13); txt(ax, 0.97, 0.505, "结\n果\n2", size=7, ha="center", weight="bold")
box(ax, 0.74, 0.36, 0.20, 0.33)
txt(ax, 0.76, 0.66, "面试结果 · 2 份", size=8, weight="bold")
for i, t in enumerate(["(C) C 级 · 64.2 分", "(B) B 级 · 78.5 分（最新）"]):
    box(ax, 0.755, 0.575 - i * 0.075, 0.17, 0.06)
    txt(ax, 0.765, 0.605 - i * 0.075, t, size=7.5)
# 消息区
box(ax, 0.06, 0.36, 0.04, 0.04, fc=BRAND, ec="none"); txt(ax, 0.08, 0.38, "VC", size=6.5, color="white", ha="center", weight="bold")
box(ax, 0.11, 0.345, 0.42, 0.075)
txt(ax, 0.125, 0.383, "你在复旦搭建了一个800人社群。最开始是怎么冷启动的？", size=7.5)
box(ax, 0.55, 0.26, 0.30, 0.075, fc=BRAND, ec="none")
txt(ax, 0.70, 0.298, "最开始逐个邀请熟人……", size=7.5, color="white", ha="center")
box(ax, 0.87, 0.27, 0.035, 0.035, ec="none", fc=GRAY); txt(ax, 0.887, 0.287, "我", size=6, color="white", ha="center")
# 输入区
box(ax, 0.06, 0.10, 0.86, 0.11)
txt(ax, 0.09, 0.175, "输入你的回答…", size=8, color=GRAY)
txt(ax, 0.09, 0.125, "Enter 发送 · Ctrl+Enter 换行", size=6.5, color=GRAY)
box(ax, 0.865, 0.115, 0.04, 0.075, fc=BRAND, ec="none"); txt(ax, 0.885, 0.152, "↑", size=10, color="white", ha="center", weight="bold")
fig.savefig(os.path.join(OUT, "proto2_chat.png"), bbox_inches="tight", facecolor=BG)
plt.close(fig)

# ---------- 原型 3：结果面板（可展开/收起） ----------
fig, ax = wire_page("原型图 3 · 面试结果面板（可展开/收起，Codex 风格）")
# 展开态
box(ax, 0.03, 0.50, 0.60, 0.38)
box(ax, 0.06, 0.745, 0.09, 0.10, fc=GREEN, ec="none"); txt(ax, 0.105, 0.795, "B", size=16, color="white", ha="center", weight="bold")
txt(ax, 0.18, 0.81, "面试结果 · 总分 78.5", size=10, weight="bold")
txt(ax, 0.18, 0.76, "评级 A-E，A 为最高 · 点击收起/展开", size=7, color=GRAY)
ax.plot(0.60, 0.79, marker="v", color=GRAY, markersize=9, mec=GRAY)
txt(ax, 0.06, 0.70, "任务理解 [██████      ] 80    关键信号 [███████     ] 82", size=7.5)
txt(ax, 0.06, 0.66, "优先级   [██████      ] 76    判断调整 [███████     ] 79", size=7.5)
txt(ax, 0.06, 0.62, "决策表达 [███████     ] 81", size=7.5)
txt(ax, 0.06, 0.56, "│ 反馈正文（总体判断 / 优势 / 问题 / 建议……）", size=7.5)
# 收起态
box(ax, 0.68, 0.74, 0.29, 0.14)
box(ax, 0.70, 0.765, 0.045, 0.09, fc=GRAY, ec="none"); txt(ax, 0.722, 0.81, "C", size=11, color="white", ha="center", weight="bold")
txt(ax, 0.76, 0.835, "面试结果 · 总分 64.2", size=8, weight="bold")
txt(ax, 0.76, 0.79, "点击展开", size=6.5, color=GRAY)
ax.plot(0.935, 0.81, marker=">", color=GRAY, markersize=9, mec=GRAY)
txt(ax, 0.68, 0.70, "收起态：只留头部一行，点击头部展开", size=7, color=GRAY)
# 继续按钮
box(ax, 0.03, 0.36, 0.25, 0.075, fc=BRAND, ec="none"); txt(ax, 0.155, 0.398, "继续面试", size=9, color="white", ha="center", weight="bold")
txt(ax, 0.30, 0.398, "从上一次结尾继续，聊几轮后自动生成新结果", size=7, color=GRAY)
fig.savefig(os.path.join(OUT, "proto3_result.png"), bbox_inches="tight", facecolor=BG)
plt.close(fig)

# ---------- 架构图 ----------
fig, ax = plt.subplots(figsize=(11, 7.6), dpi=150)
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")
fig.patch.set_facecolor("white")
txt(ax, 0.02, 0.96, "VC Hero 系统架构图", size=15, weight="bold")
txt(ax, 0.02, 0.925, "Flask + 原生 HTML/CSS/JS · 本地文件系统存储 · Kimi(kimi-k3) · 全局限速与负载均衡", size=9, color=GRAY)


def node(x, y, w, h, title, lines, fc=CARD, ec=LINE, title_color=INK):
    box(ax, x, y, w, h, fc=fc, ec=ec, lw=1.4)
    txt(ax, x + w / 2, y + h - 0.028, title, size=9.5, ha="center", weight="bold", color=title_color)
    for i, ln in enumerate(lines):
        txt(ax, x + 0.02, y + h - 0.065 - i * 0.033, ln, size=7.5, color="#4c5670")


def arrow(x1, y1, x2, y2, label="", color=GRAY):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                 mutation_scale=13, lw=1.4, color=color))
    if label:
        txt(ax, (x1 + x2) / 2 + 0.012, (y1 + y2) / 2 + 0.012, label, size=7, color=color)


# 浏览器层
node(0.03, 0.66, 0.30, 0.20, "浏览器（单页应用 + SSR 首屏）", [
    "static/：index(SPA) · app.js · style.css",
    "templates/：session.html(活动会话首屏)",
    "乐观回显 / 思考气泡 / 结果面板可收起",
    "右侧结果速览抽屉 · 双 Tab 主页",
])
# Flask 层
node(0.40, 0.66, 0.30, 0.20, "Flask 后端（vc_hero/）", [
    "routes.py：REST API（按 kind 分发）",
    "interview.py：面试状态机/[[CV_DONE]]",
    "training.py：训练引擎/训练总结",
    "pdfutil.py：PDF/TXT/MD/DOCX 抽取",
    "__init__.py：SSR 路由 / 缓存头 / 版本号",
])
# 存储
node(0.77, 0.66, 0.20, 0.20, "本地文件存储 data/", [
    "users/：账号+简历(pdf/txt)",
    "tokens/：登录令牌",
    "sessions/：会话 JSON",
    "（无数据库，原子写入）",
], fc="#f4f6fb")
# Kimi
node(0.40, 0.30, 0.30, 0.20, "Kimi API（moonshot，kimi-k3）", [
    "kimi.py：生成 → 恰好2轮自检 → 发出",
    "thinking 关闭 · temperature 0.6",
    "429/空内容退避重试",
    "评分 JSON 输出 / 训练总结",
], fc="#eef0fd", ec=BRAND, title_color=BRAND)
# 限速器
node(0.03, 0.30, 0.30, 0.20, "全局限速 ratelimit.py", [
    "滑动窗口 1h：token/h · response/h · ¥5/h",
    "预占→实结成本核算（保守偏高计价）",
    "FIFO 公平队列（多用户负载均衡）",
], fc="#f4f6fb")
# prompts
node(0.77, 0.30, 0.20, 0.20, "prompts/（全部 md）", [
    "3 份原始规则 + 总控/自检×2",
    "评分格式 / 任务场景库",
    "后端零硬编码提示词",
], fc="#f4f6fb")
# 部署
node(0.25, 0.05, 0.50, 0.13, "部署：Ubuntu 服务器 152.136.60.146 :80", [
    "/opt/vc_hero · venv 隔离 · nohup（tests/deploy.py 一键部署）",
], fc="#e8f6ef", ec=GREEN, title_color="#0d7a52")

arrow(0.33, 0.76, 0.40, 0.76, "HTTP/JSON")
arrow(0.55, 0.66, 0.55, 0.50, "全部 LLM 调用")
arrow(0.33, 0.42, 0.40, 0.76, "")
arrow(0.33, 0.40, 0.40, 0.42, "acquire()")
txt(ax, 0.335, 0.44, "放行/排队", size=6.5, color=GRAY)
arrow(0.70, 0.40, 0.77, 0.40, "load_prompt")
arrow(0.70, 0.76, 0.77, 0.76, "读写文件")
arrow(0.50, 0.30, 0.45, 0.18, "")
arrow(0.62, 0.30, 0.60, 0.18, "")
txt(ax, 0.30, 0.245, "API Key（kimi_api_key.txt，不进 git）", size=7, color=GRAY)

fig.savefig(os.path.join(OUT, "architecture.png"), bbox_inches="tight", facecolor="white")
plt.close(fig)

print("diagrams saved to", OUT)
