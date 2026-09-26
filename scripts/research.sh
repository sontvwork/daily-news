#!/usr/bin/env bash
# Wrapper quanh engine last30days (vendored) cho luồng discover 3 bước của routine.
# Mọi leg của một domain dùng chung --save-dir .cache/work/<slug> (handoff TTL 1 giờ).
#
#   research.sh list                      # in "<slug>|<domain>" từ config/news.env
#   research.sh preflight                 # kiểm tra python + permission preflight của engine
#   research.sh nominate  <slug>          # leg 1: quét listing, ghi discover-nominations.json
#   research.sh research  <slug>          # leg 2: đọc .cache/work/<slug>/judgments.json, research sâu
#   research.sh finalize  <slug> <DATE>   # leg 3: news/raw/<DATE>-<slug>.md + .json
#   research.sh oneshot   <slug> <DATE>   # fallback khi một leg fail 2 lần: news/raw/<DATE>-<slug>.json
#   research.sh status    <slug> <DATE>   # outcome + tình trạng từng nguồn (từ JSON)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=../config/news.env
source config/news.env

PY="${LAST30DAYS_PYTHON:-python3}"
ENGINE=".claude/skills/last30days/scripts/last30days.py"
# Chạy không người trực: bỏ qua first-run wizard, không bao giờ đọc cookie trình duyệt.
export SETUP_COMPLETE="${SETUP_COMPLETE:-true}" FROM_BROWSER=off EXCLUDE_SOURCES

die() { echo "research.sh: $*" >&2; exit 2; }

domain_for() {
  local entry
  for entry in "${DOMAINS[@]}"; do
    [[ "${entry%%|*}" == "$1" ]] && { echo "${entry#*|}"; return; }
  done
  die "slug không có trong config/news.env: $1"
}

need_date() {
  [[ "${1:-}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || die "cần DATE dạng YYYY-MM-DD"
}

cmd="${1:-}"; shift || true
case "$cmd" in
  list)
    printf '%s\n' "${DOMAINS[@]}"
    ;;
  preflight)
    "$PY" -c 'import sys; assert sys.version_info >= (3, 12), "cần Python >= 3.12, đang có " + sys.version.split()[0]'
    command -v jq >/dev/null || die "thiếu jq"
    "$PY" "$ENGINE" --preflight
    ;;
  nominate)
    slug="${1:?slug}"; domain="$(domain_for "$slug")"; dir=".cache/work/$slug"
    mkdir -p "$dir"
    "$PY" "$ENGINE" --discover "$domain" --nominate-only --days "$LOOKBACK_DAYS" \
      --save-dir="$dir" | tee "$dir/leg1.out"
    [[ -f "$dir/discover-nominations.json" ]] && echo "BUNDLE: $dir/discover-nominations.json"
    ;;
  research)
    slug="${1:?slug}"; domain_for "$slug" >/dev/null; dir=".cache/work/$slug"
    [[ -s "$dir/judgments.json" ]] || die "thiếu $dir/judgments.json"
    "$PY" "$ENGINE" --discover --judgments "$dir/judgments.json" \
      --save-dir="$dir" | tee "$dir/leg2.out"
    ;;
  finalize)
    slug="${1:?slug}"; need_date "${2:-}"; domain_for "$slug" >/dev/null; dir=".cache/work/$slug"
    mkdir -p news/raw
    "$PY" "$ENGINE" --discover --finalize --emit=md --output "news/raw/$2-$slug.md" --save-dir="$dir"
    # Finalize lặp lại là idempotent trong TTL: lấy thêm bản JSON (evidence_urls, source_status).
    "$PY" "$ENGINE" --discover --finalize --emit=json --output "news/raw/$2-$slug.json" \
      --save-dir="$dir" >/dev/null
    ;;
  oneshot)
    slug="${1:?slug}"; need_date "${2:-}"; domain="$(domain_for "$slug")"; dir=".cache/work/$slug"
    mkdir -p "$dir" news/raw
    "$PY" "$ENGINE" --discover "$domain" --days "$LOOKBACK_DAYS" --emit=json \
      --output "news/raw/$2-$slug.json" --save-dir="$dir" >/dev/null
    ;;
  status)
    slug="${1:?slug}"; need_date "${2:-}"; json="news/raw/$2-$slug.json"
    [[ -f "$json" ]] || { echo "outcome=missing"; exit 0; }
    jq -r '"outcome=\(.outcome) topics=\(.results | length)",
           (.source_status // {} | to_entries[]
            | "source \(.key)=\(if (.value | type) == "object" then .value.state else .value end)")' "$json"
    ;;
  *)
    sed -n '2,13p' "$0" >&2; exit 2
    ;;
esac
