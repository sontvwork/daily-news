#!/usr/bin/env bash
# Wrapper quanh engine last30days (vendored) cho luồng discover 3 bước của routine.
# Mọi leg của một domain dùng chung --save-dir .cache/work/<slug> (handoff TTL 1 giờ).
#
#   research.sh list                      # in "<slug>|<domain>" từ config/news.env
#   research.sh preflight                 # kiểm tra python + permission preflight của engine
#   research.sh nominate  <slug>…         # leg 1 (song song mọi slug truyền vào): ghi discover-nominations.json,
#                                         #   in mỗi slug một dòng: bundle (N nomination) | nothing-solid | error
#   research.sh resume    <DATE> <slug>…  # leg 2 + 3 (song song): research rồi finalize, in mỗi slug: ok | nothing-solid | error
#   research.sh research  <slug>          # leg 2: đọc .cache/work/<slug>/judgments.json (judge.py split ghi), research sâu
#   research.sh finalize  <slug> <DATE>   # leg 3: news/raw/<DATE>/<slug>.md + .json (+ <slug>-nominations.json, <slug>-judgments.json)
#   research.sh oneshot   <slug> <DATE>   # fallback khi một leg fail 2 lần: news/raw/<DATE>/<slug>.json
#   research.sh topic  <fu-slug> <DATE>   # follow-up: topic mode với query/days trong followups/<due>-<slug>.json
#                                         #   plan: .cache/work/<fu-slug>/plan.json (thiếu thì engine tự plan)
#                                         #   → news/raw/<DATE>/<fu-slug>.json
#   research.sh status    <slug> <DATE>   # outcome + tình trạng từng nguồn (từ JSON)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=../config/news.env
source config/news.env
# Local: API key của nguồn (XAI_API_KEY, XQUIK_API_KEY, …) đặt trong .env.local. Cloud: env vars của environment.
if [[ -f .env.local ]]; then set -a; source .env.local; set +a; fi

# Engine cần Python ≥ 3.12. Image cloud có python3 = 3.11 nhưng cài sẵn python3.12/3.13 → tự chọn
# (cùng thứ tự với PYTHON_CANDIDATES trong news.py). Không có bản nào đủ mới thì preflight báo lỗi.
pick_python() {
  local py
  for py in python3 python3.12 python3.13 python3.14; do
    command -v "$py" >/dev/null 2>&1 \
      && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null \
      && { echo "$py"; return; }
  done
  echo python3
}
PY="${LAST30DAYS_PYTHON:-$(pick_python)}"
ENGINE=".claude/skills/last30days/scripts/last30days.py"
SELF="$ROOT/scripts/research.sh"
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
    echo "python: $PY ($("$PY" -c 'import sys; print(sys.version.split()[0])'))"
    command -v jq >/dev/null || die "thiếu jq"
    "$PY" "$ENGINE" --preflight
    ;;
  nominate)
    [[ $# -gt 0 ]] || die "cần ít nhất 1 slug"
    for slug in "$@"; do domain_for "$slug" >/dev/null; done
    pids=()
    for slug in "$@"; do
      dir=".cache/work/$slug"; mkdir -p "$dir"
      # Sandbox cloud dùng lại bản clone: xoá handoff của lượt trước để không chấm/research nhầm bundle cũ.
      rm -f "$dir/discover-nominations.json" "$dir/judgments.json"
      "$PY" "$ENGINE" --discover "$(domain_for "$slug")" --nominate-only --days "$LOOKBACK_DAYS" \
        --save-dir="$dir" >"$dir/leg1.out" 2>"$dir/leg1.err" &
      pids+=("$!")
    done
    rc=0; i=0
    for slug in "$@"; do
      dir=".cache/work/$slug"
      if ! wait "${pids[$i]}"; then
        echo "$slug: error (exit ≠ 0, xem $dir/leg1.err)"; rc=1
      elif [[ -f "$dir/discover-nominations.json" ]] && ! grep -q "Nothing solid this window" "$dir/leg1.out"; then
        echo "$slug: bundle ($(jq '.nominations | length' "$dir/discover-nominations.json") nomination)"
      else
        echo "$slug: nothing-solid"
      fi
      i=$((i + 1))
    done
    exit "$rc"
    ;;
  resume)
    need_date "${1:-}"; date="$1"; shift
    [[ $# -gt 0 ]] || die "cần ít nhất 1 slug"
    for slug in "$@"; do domain_for "$slug" >/dev/null; done
    pids=()
    for slug in "$@"; do
      dir=".cache/work/$slug"; mkdir -p "$dir"
      (
        bash "$SELF" research "$slug" >"$dir/resume.log" 2>&1 || { echo "error (leg 2, xem $dir/resume.log)"; exit 1; }
        if grep -q "Nothing solid this window" "$dir/leg2.out"; then echo "nothing-solid"; exit 0; fi
        bash "$SELF" finalize "$slug" "$date" >>"$dir/resume.log" 2>&1 || { echo "error (finalize, xem $dir/resume.log)"; exit 1; }
        echo "ok"
      ) >"$dir/resume.status" &
      pids+=("$!")
    done
    rc=0; i=0
    for slug in "$@"; do
      wait "${pids[$i]}" || rc=1
      echo "$slug: $(cat ".cache/work/$slug/resume.status")"
      i=$((i + 1))
    done
    exit "$rc"
    ;;
  research)
    slug="${1:?slug}"; domain_for "$slug" >/dev/null; dir=".cache/work/$slug"
    [[ -s "$dir/judgments.json" ]] || die "thiếu $dir/judgments.json"
    "$PY" "$ENGINE" --discover --judgments "$dir/judgments.json" \
      --save-dir="$dir" | tee "$dir/leg2.out"
    ;;
  finalize)
    slug="${1:?slug}"; need_date "${2:-}"; domain_for "$slug" >/dev/null; dir=".cache/work/$slug"
    raw="news/raw/$2"; mkdir -p "$raw"
    "$PY" "$ENGINE" --discover --finalize --emit=md --output "$raw/$slug.md" --save-dir="$dir"
    # Finalize lặp lại là idempotent trong TTL: lấy thêm bản JSON (evidence_urls, source_status).
    "$PY" "$ENGINE" --discover --finalize --emit=json --output "$raw/$slug.json" \
      --save-dir="$dir" >/dev/null
    # Lưu bundle leg 1 (URL gốc, engagement) để chạy lại bước viết bài ở local; prune theo mẫu news/raw/DATE/*.
    if [[ -f "$dir/discover-nominations.json" ]]; then
      cp "$dir/discover-nominations.json" "$raw/$slug-nominations.json"
    fi
    # Lưu điểm agent chính chấm (junk, worthiness): judge.py candidates map topic leg 2 về nomination; eval đo cổng lọc.
    if [[ -f "$dir/judgments.json" ]]; then
      cp "$dir/judgments.json" "$raw/$slug-judgments.json"
    fi
    ;;
  oneshot)
    slug="${1:?slug}"; need_date "${2:-}"; domain="$(domain_for "$slug")"; dir=".cache/work/$slug"
    mkdir -p "$dir" "news/raw/$2"
    "$PY" "$ENGINE" --discover "$domain" --days "$LOOKBACK_DAYS" --emit=json \
      --output "news/raw/$2/$slug.json" --save-dir="$dir" >/dev/null
    ;;
  topic)
    slug="${1:?fu-slug}"; need_date "${2:-}"; dir=".cache/work/$slug"
    file="$(python3 scripts/followup.py path "$slug" "$2")" || exit 2
    query="$(jq -r .query "$file")"; days="$(jq -r .days "$file")"
    mkdir -p "$dir" "news/raw/$2"
    # Chạy dưới agent thì engine bắt buộc có --plan (LAW 7): sub-agent follow-up là planner. Không có plan thì
    # --auto-resolve để engine tự plan (planner LLM nếu env có key, không thì heuristic).
    if [[ -s "$dir/plan.json" ]]; then plan=(--plan "$dir/plan.json"); else plan=(--auto-resolve); fi
    # stdout của engine là cả JSON (vài chục KB) → chỉ ghi file, không đổ vào context của agent.
    "$PY" "$ENGINE" "$query" --days "$days" "${plan[@]}" --emit=json \
      --output "news/raw/$2/$slug.json" --save-dir="$dir" >"$dir/topic.out"
    echo "RAW: news/raw/$2/$slug.json"
    ;;
  status)
    slug="${1:?slug}"; need_date "${2:-}"; json="news/raw/$2/$slug.json"
    [[ -f "$json" ]] || { echo "outcome=missing"; exit 0; }
    # Topic mode (fu-*) không có .outcome: suy ra từ số kết quả.
    jq -r '"outcome=\(.outcome // (if (.results | length) > 0 then "ok" else "nothing-solid" end)) topics=\(.results | length)",
           (.source_status // {} | to_entries[]
            | "source \(.key)=\(if (.value | type) == "object" then .value.state else .value end)")' "$json"
    ;;
  *)
    sed -n '2,16p' "$0" >&2; exit 2
    ;;
esac
