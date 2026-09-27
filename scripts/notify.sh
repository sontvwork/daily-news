#!/usr/bin/env bash
# Gửi thông báo Google Chat (incoming webhook) — payload {"text": ...} dựng bằng jq.
#
#   notify.sh success <DATE>                    # tiêu đề + 1–3 dòng tóm tắt (y hệt trang chủ) + link bài trên Pages
#   notify.sh failure <DATE> <STEP> <DETAIL>    # báo lỗi ngắn kèm bước bị fail
#
# Env: GCHAT_WEBHOOK_URL (secret), DRY_RUN=1 (chỉ in payload), NOTIFY_PREFIX (vd "[TEST] ").
# Thiếu GCHAT_WEBHOOK_URL → tự dry-run và exit 3 để người gọi biết là chưa gửi được.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=../config/news.env
source config/news.env
if [[ -f .env.local ]]; then set -a; source .env.local; set +a; fi

SECRET_VARS=(GCHAT_WEBHOOK_URL SCRAPECREATORS_API_KEY XAI_API_KEY BRAVE_API_KEY XQUIK_API_KEY
             EXA_API_KEY SERPER_API_KEY PARALLEL_API_KEY PERPLEXITY_API_KEY OPENROUTER_API_KEY)

# Xoá mọi thứ trông như secret khỏi chuỗi chi tiết lỗi, gộp khoảng trắng, cắt 300 ký tự.
sanitize() {
  local text="$1" var value
  for var in "${SECRET_VARS[@]}"; do
    value="${!var:-}"
    [[ ${#value} -ge 8 ]] && text="${text//"$value"/***}"
  done
  printf '%s' "$text" \
    | sed -E 's#https://chat\.googleapis\.com/[^[:space:]"]*#[webhook]#g; s#(([Kk][Ee][Yy]|[Tt][Oo][Kk][Ee][Nn])=)[^&[:space:]"]+#\1***#g' \
    | tr '\n\t' '  ' | tr -s ' ' \
    | python3 -c 'import sys; print(sys.stdin.read().strip()[:300], end="")'  # cắt theo ký tự, không vỡ UTF-8
}

pretty_date() { local d="$1"; echo "${d:8:2}/${d:5:2}/${d:0:4}"; }

send() {
  local text="$1" payload
  payload="$(jq -n --arg text "$text" '{text: $text}')"
  if [[ "${DRY_RUN:-0}" == 1 || -z "${GCHAT_WEBHOOK_URL:-}" ]]; then
    echo "[DRY-RUN] Google Chat payload:"
    echo "$payload"
    [[ -z "${GCHAT_WEBHOOK_URL:-}" && "${DRY_RUN:-0}" != 1 ]] && { echo "notify.sh: thiếu GCHAT_WEBHOOK_URL — chưa gửi" >&2; return 3; }
    return 0
  fi
  local body rc=0; body="$(mktemp)"
  printf '%s' "$payload" > "$body"
  # URL webhook đi qua config trên stdin (-K -) để không lộ trong argv/process list.
  printf 'url = "%s"\n' "$GCHAT_WEBHOOK_URL" \
    | curl -K - -sS -o /dev/null -w 'Google Chat HTTP %{http_code}\n' --fail --retry 3 --retry-all-errors \
        --max-time 20 -H 'Content-Type: application/json; charset=UTF-8' --data-binary @"$body" || rc=$?
  rm -f "$body"
  [[ $rc -eq 0 ]] || { echo "notify.sh: gửi Google Chat thất bại (curl exit $rc)" >&2; return "$rc"; }
  echo "$text"
}

mode="${1:-}"; DATE="${2:-}"
[[ "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "notify.sh: cần DATE YYYY-MM-DD" >&2; exit 2; }
TITLE="Daily News $(pretty_date "$DATE")"

case "$mode" in
  success)
    link="$(python3 scripts/news.py link "$DATE")"
    lines=()
    while IFS= read -r line; do lines+=("$line"); done < <(python3 scripts/news.py summary "$DATE")
    [[ ${#lines[@]} -ge 1 && ${#lines[@]} -le 3 ]] || { echo "notify.sh: summary phải có 1–3 dòng" >&2; exit 2; }
    text="${NOTIFY_PREFIX:-}📰 *$TITLE*"
    for line in "${lines[@]}"; do text+=$'\n'"$line"; done
    send "$text"$'\n'"🔗 ${PAGES_BASE_URL%/}/$link"
    ;;
  failure)
    step="${3:-unknown}"; detail="$(sanitize "${4:-}")"
    case "$step" in
      push)     note="Push thất bại — main không thay đổi." ;;
      deploy)   note="Đã push lên main nhưng Pages chưa phục vụ bài mới." ;;
      notify)   note="Đã push, chỉ bước gửi tin tóm tắt bị lỗi." ;;
      watchdog) note="Không thấy bản tin hôm nay trên main." ;;
      *)        note="Chưa push gì lên main." ;;
    esac
    send "$(printf '%s🚨 *%s — LỖI*\nBước: %s\nChi tiết: %s\n%s' "${NOTIFY_PREFIX:-}" "$TITLE" \
      "$step" "${detail:-(không có)}" "$note")"
    ;;
  *)
    sed -n '2,8p' "$0" >&2; exit 2
    ;;
esac
