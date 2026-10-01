#!/usr/bin/env bash
# Chạy lại phần sau bước viết bài ở LOCAL để test. KHÔNG commit, KHÔNG push → guard chỉ cảnh báo, không chặn
# (code chưa commit vẫn chạy được). Publish thật vẫn đi qua publish.sh sau khi đã commit + push code.
#
#   dev.sh build  <DATE> [--send]   # validate → prune → build site → guard (cảnh báo) → notify success
#   dev.sh notify <DATE> [--send]   # chỉ notify success (link lấy từ news/feed.xml hiện có)
#
# Mặc định notify chạy DRY_RUN (chỉ in payload). --send: gửi Google Chat thật, tiền tố NOTIFY_PREFIX="[TEST] ".
# Bước viết bài (news/DATE.md + news/raw/DATE-summary.txt) do Claude làm trong phiên chat — xem CLAUDE.local.md.
# Bỏ kết quả test: git checkout -- news/ && git clean -fd news/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

cmd="${1:-}"; DATE="${2:-}"; SEND=0
[[ "${3:-}" == "--send" ]] && SEND=1
[[ "$cmd" == build || "$cmd" == notify ]] || { sed -n '2,10p' "$0" >&2; exit 2; }
[[ "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "dev.sh: cần DATE dạng YYYY-MM-DD" >&2; exit 2; }

if [[ "$cmd" == build ]]; then
  echo "== validate"; python3 scripts/news.py validate "$DATE"
  echo "== prune";    python3 scripts/news.py prune "$DATE"
  echo "== build";    python3 scripts/news.py site "$DATE"
  # Chỉ để biết trước publish thật có bị chặn không (code chưa commit, commit bảo trì chưa push…).
  echo "== guard (chỉ cảnh báo)"
  for mode in worktree outgoing; do
    bash scripts/guard.sh "$mode" "$DATE" || echo "⚠️  publish.sh thật sẽ bị guard $mode chặn (xem danh sách trên)"
  done
fi

echo "== notify"
if [[ $SEND == 1 ]]; then
  NOTIFY_PREFIX="${NOTIFY_PREFIX:-[TEST] }" bash scripts/notify.sh success "$DATE"
else
  DRY_RUN=1 bash scripts/notify.sh success "$DATE"
fi
echo "✅ dev.sh $cmd $DATE xong — không commit/push. Xem thử: open news/index.html"
