#!/usr/bin/env bash
# Cập nhật bản vendored của last30days skill vào .claude/skills/last30days/.
# CHỈ người chạy tay rồi review + commit. Routine KHÔNG được chạy script này.
#
#   scripts/vendor_skill.sh [ref]            # clone upstream, mặc định HEAD của main
#   LAST30DAYS_SRC=/path/to/checkout scripts/vendor_skill.sh 52f5331
#
# Dùng `git archive` nên tôn trọng export-ignore của upstream (bỏ assets/, tests/, docs/...).
set -euo pipefail

UPSTREAM="https://github.com/mvanhorn/last30days-skill.git"
REF="${1:-HEAD}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/.claude/skills/last30days"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if [[ -n "${LAST30DAYS_SRC:-}" ]]; then
  SRC="$LAST30DAYS_SRC"
else
  git clone --quiet "$UPSTREAM" "$TMP/src"
  SRC="$TMP/src"
fi

SHA="$(git -C "$SRC" rev-parse "${REF}^{commit}")"
mkdir -p "$TMP/out"
git -C "$SRC" archive "$SHA" skills/last30days | tar -x -C "$TMP/out"

rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
mv "$TMP/out/skills/last30days" "$DEST"
cat > "$DEST/.vendored-from" <<EOF
repo=$UPSTREAM
commit=$SHA
vendored_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

echo "Vendored last30days @ $SHA -> ${DEST#"$ROOT"/}"
