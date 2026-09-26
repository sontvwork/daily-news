#!/usr/bin/env bash
# Hàng rào an toàn trước commit/push của routine.
#
#   guard.sh worktree   # trước commit: mọi thay đổi (kể cả untracked) phải nằm trong news/
#   guard.sh outgoing   # trước push: các commit origin/main..HEAD chỉ chạm news/, message "news: YYYY-MM-DD"
#
# Chặn: file ngoài news/, xoá/đổi tên file, merge commit, secret lọt vào nội dung.
# Vi phạm → in danh sách, exit 3.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f .env.local ]]; then set -a; source .env.local; set +a; fi

SECRET_VARS=(GCHAT_WEBHOOK_URL SCRAPECREATORS_API_KEY XAI_API_KEY BRAVE_API_KEY XQUIK_API_KEY
             EXA_API_KEY SERPER_API_KEY PARALLEL_API_KEY PERPLEXITY_API_KEY OPENROUTER_API_KEY)
violations=()

check_path() {  # <status> <path>
  case "$1" in *D*) violations+=("xoá file: $2") ;; esac
  [[ "$2" == news/* ]] || violations+=("ngoài phạm vi news/: $2")
}

scan_secrets() {  # đọc nội dung từ stdin (gọi bằng redirect, không qua pipe, để giữ $violations)
  local content var value
  content="$(cat)"
  grep -Eq 'chat\.googleapis\.com/v1/spaces/[^[:space:]]*key=[A-Za-z0-9_-]{20,}' <<<"$content" \
    && violations+=("nội dung chứa URL webhook Google Chat")
  for var in "${SECRET_VARS[@]}"; do
    value="${!var:-}"
    [[ ${#value} -ge 8 ]] && grep -Fq -- "$value" <<<"$content" && violations+=("nội dung chứa giá trị \$$var")
  done
  return 0
}

mode="${1:-}"
case "$mode" in
  worktree)
    changed=()
    while IFS= read -r -d '' entry; do
      xy="${entry:0:2}"; path="${entry:3}"
      if [[ "$xy" == R* || "$xy" == C* ]]; then
        IFS= read -r -d '' orig || true
        violations+=("đổi tên/copy: $orig -> $path")
        continue
      fi
      check_path "$xy" "$path"
      [[ -f "$path" ]] && changed+=("$path")
    done < <(git status --porcelain=v1 -z --untracked-files=all)
    if [[ ${#changed[@]} -gt 0 ]]; then scan_secrets < <(cat -- "${changed[@]}"); fi
    count=${#changed[@]}
    ;;
  outgoing)
    git fetch --quiet origin main
    range="origin/main..HEAD"
    [[ -z "$(git rev-list --merges "$range")" ]] || violations+=("có merge commit trong $range")
    while IFS= read -r subject; do
      [[ "$subject" =~ ^news:\ [0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || violations+=("commit message sai format: '$subject'")
    done < <(git log --format=%s "$range")
    count=0
    while IFS= read -r -d '' status && IFS= read -r -d '' path; do
      check_path "$status" "$path"; count=$((count + 1))
    done < <(git diff --name-status -z --no-renames origin/main HEAD)
    scan_secrets < <(git diff origin/main HEAD)
    ;;
  *)
    sed -n '2,8p' "$0" >&2; exit 2
    ;;
esac

if [[ ${#violations[@]} -gt 0 ]]; then
  echo "GUARD CHẶN ($mode): ${#violations[@]} vi phạm"
  printf ' - %s\n' "${violations[@]}"
  exit 3
fi
echo "GUARD OK ($mode): $count file, tất cả trong news/"
