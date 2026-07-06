#!/bin/bash
# SessionStart hook — 强制把本仓库的工作铁律注入每个会话的上下文。
# SessionStart hook 的 stdout 会被 harness 直接加进 Claude 的上下文，Claude 无法跳过。
set -euo pipefail

cat <<'RULES'
============================================================
【本仓库工作铁律 · 每次开工强制生效 · 优先级高于任何惯性记忆】
1) Skill/ROUTINE 优先：动手前先读 ROUTINE.md 全文并按当前版本执行；
   有相关 Skill 必须先调用再动手。禁止凭记忆里的旧规则行事。
2) 出错必先读日志原文：任何 CI/部署/命令失败，第一步必须取该错误的 log 原文
   （如 get_job_logs 读 ##[error] 原句），在读到真实报错前禁止任何"大概是…"的经验推测。
3) Pages 部署：失败禁止 rerun_failed_jobs（会叠加同名 artifact 秒失败）；
   遇 "Deployment failed, try again later" 用 workflow_dispatch 起全新 run；
   判定上线前须确认 run conclusion==success 并提醒用户强刷缓存。
   详见仓库根目录 CLAUDE.md。
============================================================
RULES
