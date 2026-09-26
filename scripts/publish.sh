#!/usr/bin/env bash
# Đẩy bản tin ngày DATE lên main + Pages + Google Chat. Cách DUY NHẤT routine được commit/push.
#
#   publish.sh <DATE> [--no-push]
#
# validate → build site → guard worktree → commit "news: DATE" → guard outgoing → push main
# → chờ Pages live → notify success.  Bất kỳ bước nào lỗi: notify failure <bước> rồi exit ≠ 0.
# --no-push: dừng sau guard outgoing, gửi tin tóm tắt ở chế độ DRY_RUN (dùng để test local).
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=../config/news.env
source config/news.env
if [[ -f .env.local ]]; then set -a; source .env.local; set +a; fi

DATE="${1:-}"
NO_PUSH=0; [[ "${2:-}" == "--no-push" ]] && NO_PUSH=1
STEP="init"
LOG="$(mktemp)"

on_error() {
  local code=$?
  trap - ERR
  echo "publish.sh: THẤT BẠI ở bước '$STEP' (exit $code)" >&2
  local notify_date="$DATE"
  [[ "$notify_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || notify_date="$(TZ="$NEWS_TZ" date +%F)"
  bash scripts/notify.sh failure "$notify_date" "$STEP" "$(tail -n 6 "$LOG")" || true
  rm -f "$LOG"
  exit "$code"
}
trap on_error ERR

run() { "$@" 2>&1 | tee -a "$LOG"; }

[[ "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "cần DATE dạng YYYY-MM-DD, nhận '$DATE'" >>"$LOG"; false; }

STEP="branch"
branch="$(git rev-parse --abbrev-ref HEAD)"
[[ "$branch" == main ]] || { echo "đang ở branch '$branch', phải là main" | tee -a "$LOG"; false; }

STEP="validate"
run python3 scripts/news.py validate "$DATE"

STEP="build"
run python3 scripts/news.py site "$DATE"

STEP="guard"
run bash scripts/guard.sh worktree

STEP="commit"
git add -A -- news/
if git diff --cached --quiet; then
  echo "Không có thay đổi so với HEAD — bỏ qua commit" | tee -a "$LOG"
else
  run git commit --quiet -m "news: $DATE"
fi

STEP="guard"
run bash scripts/guard.sh outgoing

if [[ $NO_PUSH == 1 ]]; then
  echo "--no-push: bỏ qua push và kiểm tra Pages" | tee -a "$LOG"
  STEP="notify"
  DRY_RUN=1 bash scripts/notify.sh success "$DATE" | tee -a "$LOG"
  rm -f "$LOG"
  exit 0
fi

STEP="push"
if ! run git push origin main; then
  # main trên remote đã đi trước: rebase commit news chưa publish lên trên rồi thử lại đúng 1 lần.
  run git fetch origin main
  run git rebase origin/main || { git rebase --abort || true; false; }
  STEP="guard"; run bash scripts/guard.sh outgoing
  STEP="push";  run git push origin main
fi

STEP="deploy"
run python3 scripts/news.py verify-live "$DATE" --base "$PAGES_BASE_URL" --timeout 420

STEP="notify"
run bash scripts/notify.sh success "$DATE"
rm -f "$LOG"
echo "✅ Xong: news: $DATE"
