#!/usr/bin/env bash
# Đẩy bản tin ngày DATE lên main + Pages + Google Chat. Cách DUY NHẤT routine được commit/push.
#
#   publish.sh <DATE> [--no-push]
#
# sync (fast-forward main lên origin/main) → validate → prune (xoá bản tin quá RETENTION_DAYS ngày) → build site → guard worktree
# → commit "news: DATE" (gồm cả file vừa xoá) → guard outgoing → push main
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
LOG="$(mktemp)"
# Mỗi bước ghi dòng bắt đầu trong LOG để thông báo lỗi chỉ chứa output của đúng bước đó.
step() { STEP="$1"; STEP_LINE=$(( $(wc -l < "$LOG") + 1 )); }
step init

on_error() {
  local code=$?
  trap - ERR
  echo "publish.sh: THẤT BẠI ở bước '$STEP' (exit $code)" >&2
  local notify_date="$DATE"
  [[ "$notify_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || notify_date="$(TZ="$NEWS_TZ" date +%F)"
  bash scripts/notify.sh failure "$notify_date" "$STEP" "$(tail -n "+$STEP_LINE" "$LOG" | tail -n 8)" || true
  rm -f "$LOG"
  exit "$code"
}
trap on_error ERR

run() { "$@" 2>&1 | tee -a "$LOG"; }

[[ "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "cần DATE dạng YYYY-MM-DD, nhận '$DATE'" >>"$LOG"; false; }

step branch
branch="$(git rev-parse --abbrev-ref HEAD)"
[[ "$branch" == main ]] || { echo "đang ở branch '$branch', phải là main" | tee -a "$LOG"; false; }

step sync
# Sandbox cloud có thể dùng lại bản clone cũ (main local tụt sau origin) → chỉ fast-forward lên origin/main.
# HEAD đổi nghĩa là script vừa chạy là bản cũ: exec lại bản mới đúng 1 lần.
run git fetch --quiet origin '+refs/heads/main:refs/remotes/origin/main'
before="$(git rev-parse HEAD)"
run git merge --ff-only --quiet origin/main
if [[ "$(git rev-parse HEAD)" != "$before" && -z "${PUBLISH_SYNCED:-}" ]]; then
  echo "main được cập nhật ${before:0:7} → $(git rev-parse --short HEAD), chạy lại publish.sh bản mới" | tee -a "$LOG"
  trap - ERR; rm -f "$LOG"
  PUBLISH_SYNCED=1 exec bash scripts/publish.sh "$@"
fi

step validate
run python3 scripts/news.py validate "$DATE"

step prune
run python3 scripts/news.py prune "$DATE"

step build
run python3 scripts/news.py site "$DATE"

step guard
run bash scripts/guard.sh worktree "$DATE"

step commit
git add -A -- news/
if git diff --cached --quiet; then
  echo "Không có thay đổi so với HEAD — bỏ qua commit" | tee -a "$LOG"
else
  run git commit --quiet -m "news: $DATE"
fi

step guard
run bash scripts/guard.sh outgoing

if [[ $NO_PUSH == 1 ]]; then
  echo "--no-push: bỏ qua push và kiểm tra Pages" | tee -a "$LOG"
  step notify
  DRY_RUN=1 bash scripts/notify.sh success "$DATE" | tee -a "$LOG"
  rm -f "$LOG"
  exit 0
fi

step push
if ! run git push origin main; then
  # main trên remote đã đi trước: rebase commit news chưa publish lên trên rồi thử lại đúng 1 lần.
  run git fetch --quiet origin '+refs/heads/main:refs/remotes/origin/main'
  run git rebase origin/main || { git rebase --abort || true; false; }
  step guard; run bash scripts/guard.sh outgoing
  step push;  run git push origin main
fi

step deploy
run python3 scripts/news.py verify-live "$DATE" --base "$PAGES_BASE_URL" --timeout 420

step notify
run bash scripts/notify.sh success "$DATE"
rm -f "$LOG"
echo "✅ Xong: news: $DATE"
