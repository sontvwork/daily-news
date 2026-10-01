#!/usr/bin/env bash
# Hàng rào an toàn trước commit/push của routine.
#
#   guard.sh worktree [DATE]  # trước commit: mọi thay đổi (kể cả untracked) phải nằm trong news/
#   guard.sh outgoing         # trước push: từng commit origin/main..HEAD chỉ chạm news/, message "news: YYYY-MM-DD"
#
# Chặn: file ngoài news/, xoá/đổi tên file, merge commit, secret lọt vào nội dung.
# Ngoại lệ duy nhất: xoá file có ngày của bản tin (news/DATE.md, news/raw/DATE/*, news/briefs/DATE.html
# và tên cũ news/raw/DATE-*, news/briefs/*-DATE.html)
# khi ngày đó < DATE − (RETENTION_DAYS − 1). DATE = tham số (worktree) hoặc message của từng commit (outgoing).
# Vi phạm → in danh sách, exit 3.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=../config/news.env
source config/news.env
if [[ -f .env.local ]]; then set -a; source .env.local; set +a; fi

SECRET_VARS=(GCHAT_WEBHOOK_URL SCRAPECREATORS_API_KEY XAI_API_KEY BRAVE_API_KEY XQUIK_API_KEY
             EXA_API_KEY SERPER_API_KEY PARALLEL_API_KEY PERPLEXITY_API_KEY OPENROUTER_API_KEY)
# Mẫu file có ngày được phép xoá khi quá hạn (khớp DATED_FILES trong news.py). Nhóm 1 = ngày.
DATE_RE='^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
DATED_RES=('^news/([0-9]{4}-[0-9]{2}-[0-9]{2})\.md$'
           '^news/raw/([0-9]{4}-[0-9]{2}-[0-9]{2})/[a-z0-9-]+\.(md|json|txt)$'
           '^news/raw/([0-9]{4}-[0-9]{2}-[0-9]{2})-[a-z0-9-]+\.(md|json|txt)$'  # tên cũ (chưa chia thư mục)
           '^news/briefs/([0-9]{4}-[0-9]{2}-[0-9]{2})\.html$'
           '^news/briefs/[a-z0-9-]+-[0-9a-f]{8}-([0-9]{4}-[0-9]{2}-[0-9]{2})\.html$')  # tên cũ, để dọn file sót
violations=()
pruned=0

# In mốc xoá cho bản tin DATE: file có ngày < mốc mới được xoá. In rỗng (= cấm xoá) nếu RETENTION_DAYS
# sai, DATE sai format / ở tương lai, hoặc không có news/DATE.md (trên đĩa, hoặc trong <commit> nếu có).
cutoff_for() {  # <DATE> [commit]
  local day="$1" commit="${2:-}" retention="${RETENTION_DAYS:-}"
  [[ "$retention" =~ ^[1-9][0-9]*$ && "$day" =~ $DATE_RE ]] || return 0
  [[ "$day" > "$(TZ="$NEWS_TZ" date +%F)" ]] && return 0
  if [[ -n "$commit" ]]; then
    git cat-file -e "$commit:news/$day.md" 2>/dev/null || return 0
  else
    [[ -f "news/$day.md" ]] || return 0
  fi
  python3 -c 'import sys, datetime as d
print(d.date.fromisoformat(sys.argv[1]) - d.timedelta(days=int(sys.argv[2]) - 1))' "$day" "$retention" 2>/dev/null || true
}

is_expired() {  # <path> <mốc>: 0 nếu path là file có ngày của bản tin và ngày < mốc
  local re
  [[ -n "$2" ]] || return 1
  for re in "${DATED_RES[@]}"; do
    if [[ "$1" =~ $re ]]; then [[ "${BASH_REMATCH[1]}" < "$2" ]]; return; fi
  done
  return 1
}

check_path() {  # <status> <path> <mốc xoá, rỗng = cấm xoá>
  case "$1" in
    *D*) if is_expired "$2" "$3"; then pruned=$((pruned + 1)); else violations+=("xoá file: $2"); fi ;;
  esac
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
cutoffs=""
case "$mode" in
  worktree)
    cutoff="$(cutoff_for "${2:-}")"; cutoffs="$cutoff"
    changed=()
    while IFS= read -r -d '' entry; do
      xy="${entry:0:2}"; path="${entry:3}"
      if [[ "$xy" == R* || "$xy" == C* ]]; then
        IFS= read -r -d '' orig || true
        violations+=("đổi tên/copy: $orig -> $path")
        continue
      fi
      check_path "$xy" "$path" "$cutoff"
      [[ -f "$path" ]] && changed+=("$path")
    done < <(git status --porcelain=v1 -z --untracked-files=all --no-renames)
    if [[ ${#changed[@]} -gt 0 ]]; then scan_secrets < <(cat -- "${changed[@]}"); fi
    count=$(( ${#changed[@]} + pruned ))
    ;;
  outgoing)
    # Refspec tường minh: luôn cập nhật origin/main (ref cũ sẽ kéo cả commit đã push vào range).
    git fetch --quiet origin '+refs/heads/main:refs/remotes/origin/main'
    range="origin/main..HEAD"
    [[ -z "$(git rev-list --merges "$range")" ]] || violations+=("có merge commit trong $range")
    count=0
    # Từng commit một (không dùng diff gộp): commit sau xoá file mà commit trước thêm vẫn bị bắt.
    while IFS= read -r commit; do
      subject="$(git log -1 --format=%s "$commit")"
      cutoff=""
      if [[ "$subject" =~ ^news:\ ([0-9]{4}-[0-9]{2}-[0-9]{2})$ ]]; then
        cutoff="$(cutoff_for "${BASH_REMATCH[1]}" "$commit")"
      else
        violations+=("commit message sai format: '$subject'")
      fi
      [[ -n "$cutoff" ]] && cutoffs="$cutoff"
      while IFS= read -r -d '' status && IFS= read -r -d '' path; do
        check_path "$status" "$path" "$cutoff"; count=$((count + 1))
      done < <(git diff-tree -r -z --no-commit-id --no-renames --name-status "$commit")
    done < <(git rev-list "$range")
    scan_secrets < <(git diff origin/main HEAD)
    ;;
  *)
    sed -n '2,11p' "$0" >&2; exit 2
    ;;
esac

if [[ ${#violations[@]} -gt 0 ]]; then
  echo "GUARD CHẶN ($mode): ${#violations[@]} vi phạm"
  printf ' - %s\n' "${violations[@]}"
  exit 3
fi
note=""
[[ $pruned -gt 0 ]] && note=" · xoá $pruned file quá hạn (ngày < $cutoffs)"
echo "GUARD OK ($mode): $count file, tất cả trong news/$note"
