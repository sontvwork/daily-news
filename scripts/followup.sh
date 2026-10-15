#!/usr/bin/env bash
# Follow-up topic theo chỉ thị (skill news-followup gọi script này khi người dùng reply vào session routine).
# Cách DUY NHẤT để thêm/huỷ follow-up trên main: ghi/xoá đúng 1 file followups/<DUE>-<slug>.json,
# commit "followup: add|cancel <DUE> <slug>", guard outgoing, push.
#
#   followup.sh add --due D --slug S --query Q --title T --angle A --request R [--days N] [--no-push]
#   followup.sh cancel <slug> [--no-push]
#   followup.sh list
#
# Luật nội dung (ngày, slug, độ dài, tối đa 3 follow-up/ngày) nằm ở followup.py.
# Follow-up được xử lý ở bản tin có DATE ≥ due, rồi publish.sh (news.py prune) xoá file trong commit news: DATE.
# --no-push: commit local, không push (để test).
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=../config/news.env
source config/news.env
if [[ -f .env.local ]]; then set -a; source .env.local; set +a; fi

die() { echo "followup.sh: $*" >&2; exit 2; }

sync_main() {
  # Session reply có thể ở branch khác hoặc main local tụt sau origin (sandbox dùng lại clone cũ).
  local branch
  branch="$(git rev-parse --abbrev-ref HEAD)"
  if [[ "$branch" != main ]]; then
    git checkout --quiet main || die "đang ở branch '$branch', không checkout được main"
  fi
  git fetch --quiet origin '+refs/heads/main:refs/remotes/origin/main'
  git merge --ff-only --quiet origin/main || die "main local đã rẽ nhánh khỏi origin/main — cần xử lý tay"
}

commit_push() {  # <message> <path> <no_push>
  local message="$1" path="$2" no_push="$3"
  # Chỉ commit đúng file follow-up (pathspec), thay đổi khác trong worktree không bị cuốn theo.
  git commit --quiet -m "$message" -- "$path"
  bash scripts/guard.sh outgoing
  if [[ "$no_push" == 1 ]]; then
    echo "--no-push: đã commit '$message', chưa push"
    return
  fi
  if ! git push --quiet origin main; then
    # main trên remote vừa đi trước (vd routine vừa publish): rebase rồi thử lại đúng 1 lần.
    git fetch --quiet origin '+refs/heads/main:refs/remotes/origin/main'
    git rebase --quiet origin/main || { git rebase --abort || true; die "rebase thất bại"; }
    bash scripts/guard.sh outgoing
    git push --quiet origin main
  fi
  echo "✅ Đã push: $message"
}

cmd="${1:-}"; shift || true
no_push=0
args=()
for arg in "$@"; do
  if [[ "$arg" == --no-push ]]; then no_push=1; else args+=("$arg"); fi
done

case "$cmd" in
  add)
    [[ ${#args[@]} -gt 0 ]] || die "thiếu tham số (xem: followup.sh)"
    sync_main
    path="$(python3 scripts/followup.py add "${args[@]}")"
    [[ "$path" =~ ^followups/([0-9]{4}-[0-9]{2}-[0-9]{2})-([a-z0-9-]+)\.json$ ]] || die "đường dẫn lạ: $path"
    git add -- "$path"
    commit_push "followup: add ${BASH_REMATCH[1]} ${BASH_REMATCH[2]}" "$path" "$no_push"
    cat -- "$path"
    ;;
  cancel)
    [[ ${#args[@]} -eq 1 ]] || die "cách dùng: followup.sh cancel <slug>"
    sync_main
    path="$(python3 scripts/followup.py cancel "${args[0]}")"
    [[ "$path" =~ ^followups/([0-9]{4}-[0-9]{2}-[0-9]{2})-([a-z0-9-]+)\.json$ ]] || die "đường dẫn lạ: $path"
    git rm --quiet --cached -- "$path"
    commit_push "followup: cancel ${BASH_REMATCH[1]} ${BASH_REMATCH[2]}" "$path" "$no_push"
    ;;
  list)
    git fetch --quiet origin '+refs/heads/main:refs/remotes/origin/main' 2>/dev/null \
      && git merge --ff-only --quiet origin/main 2>/dev/null || true
    python3 scripts/followup.py list
    ;;
  *)
    sed -n '2,12p' "$0" >&2; exit 2
    ;;
esac
