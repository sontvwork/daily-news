#!/usr/bin/env python3
"""Follow-up topic theo chỉ thị: file followups/<DUE>-<slug>.json (chỉ dùng stdlib).

  followup.py add --due D --slug S --query Q --title T --angle A --request R [--days N]
                              ghi followups/D-S.json (kiểm tra luật), in đường dẫn
  followup.py cancel SLUG     xoá file follow-up của SLUG, in đường dẫn
  followup.py list            in mọi follow-up đang chờ (kể cả đã tới hạn mà chưa publish)
  followup.py due DATE        in follow-up cần xử lý ở bản tin DATE (due ≤ DATE), theo thứ tự tin 1…N
  followup.py path FU-SLUG DATE   in đường dẫn file của research slug fu-<slug> (due ≤ DATE)

Commit/push do followup.sh lo; prune (news.py) xoá file có due ≤ DATE khi publish bản tin DATE.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date as Date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
FOLLOWUPS = ROOT / "followups"
CONFIG = ROOT / "config/news.env"
FOLLOWUP_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)\.json$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PREFIX = "fu-"  # slug research của follow-up: fu-<slug> → news/raw/<DATE>/fu-<slug>.{md,json}
MAX_AHEAD_DAYS = 14
MAX_PER_DAY = 3
DEFAULT_DAYS = 2
LIMITS = {"query": 80, "title": 120, "angle": 300, "request": 1000}


def fail(message: str) -> None:
    print(f"followup.py: {message}", file=sys.stderr)
    sys.exit(1)


def news_tz() -> ZoneInfo:
    match = re.search(r'^NEWS_TZ="([^"]+)"', CONFIG.read_text(encoding="utf-8"), re.MULTILINE)
    return ZoneInfo(match.group(1) if match else "Asia/Ho_Chi_Minh")


def today() -> Date:
    return datetime.now(news_tz()).date()


def parse_date(value: str) -> Date:
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return Date.fromisoformat(value)
    except ValueError:
        pass
    fail(f"ngày phải dạng YYYY-MM-DD, nhận {value!r}")


def all_followups() -> list[tuple[Path, dict]]:
    """[(path, data)] của mọi file follow-up hợp lệ, xếp theo (due, created) — đúng thứ tự tin 1…N."""
    found = []
    for path in FOLLOWUPS.glob("*.json") if FOLLOWUPS.is_dir() else []:
        match = FOLLOWUP_FILE.match(path.name)
        if not match:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            fail(f"{path.relative_to(ROOT)} không đọc được: {exc}")
        if data.get("due") != match.group(1) or data.get("slug") != match.group(2):
            fail(f"{path.relative_to(ROOT)}: due/slug trong file không khớp tên file")
        found.append((path, data))
    return sorted(found, key=lambda item: (item[1]["due"], item[1].get("created", ""), item[1]["slug"]))


def due_followups(date: str) -> list[tuple[Path, dict]]:
    """Follow-up cần xử lý (và được dọn) ở bản tin DATE: due ≤ DATE (follow-up trễ vẫn làm bù)."""
    return [(path, data) for path, data in all_followups() if data["due"] <= date]


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def clean_text(name: str, value: str) -> str:
    value = " ".join(value.split())  # một dòng, không ký tự điều khiển
    if not value:
        fail(f"--{name} không được rỗng")
    if len(value) > LIMITS[name]:
        fail(f"--{name} dài {len(value)} > {LIMITS[name]} ký tự")
    return value


def cmd_add(args: argparse.Namespace) -> None:
    due, now = parse_date(args.due), today()
    if not now < due <= now + timedelta(days=MAX_AHEAD_DAYS):
        fail(f"due phải trong khoảng {now + timedelta(days=1)} … {now + timedelta(days=MAX_AHEAD_DAYS)} "
             f"(hôm nay {now}: bản tin hôm nay đã/đang chạy, không nhận thêm follow-up)")
    if not SLUG.fullmatch(args.slug) or len(args.slug) > 40 or args.slug.startswith(PREFIX):
        fail(f"slug phải là ascii kebab-case ≤ 40 ký tự, không bắt đầu bằng '{PREFIX}': {args.slug!r}")
    if not 1 <= args.days <= 7:
        fail(f"--days phải trong 1…7, nhận {args.days}")
    path = FOLLOWUPS / f"{due.isoformat()}-{args.slug}.json"
    existing = all_followups()
    same_slug = [p for p, d in existing if d["slug"] == args.slug and p != path]
    if same_slug:
        fail(f"slug {args.slug!r} đã có ở {rel(same_slug[0])} — huỷ trước (followup.sh cancel {args.slug}) hoặc đổi slug")
    same_day = [p for p, d in existing if d["due"] == due.isoformat() and p != path]
    if len(same_day) >= MAX_PER_DAY:
        fail(f"ngày {due} đã có {len(same_day)} follow-up (tối đa {MAX_PER_DAY}): "
             + ", ".join(rel(p) for p in same_day))
    data = {
        "slug": args.slug,
        "due": due.isoformat(),
        "title": clean_text("title", args.title),
        "query": clean_text("query", args.query),
        "angle": clean_text("angle", args.angle),
        "days": args.days,
        "request": clean_text("request", args.request),
        "created": datetime.now(news_tz()).isoformat(timespec="seconds"),
    }
    FOLLOWUPS.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(rel(path))


def cmd_cancel(slug: str) -> None:
    paths = [p for p, d in all_followups() if d["slug"] == slug]
    if not paths:
        fail(f"không có follow-up nào với slug {slug!r} (xem: followup.sh list)")
    for path in paths:
        path.unlink()
        print(rel(path))


def describe(path: Path, data: dict) -> str:
    return (
        f"{PREFIX}{data['slug']} | due {data['due']} | days {data['days']} | query \"{data['query']}\" | {rel(path)}\n"
        f"  title:   {data['title']}\n"
        f"  angle:   {data['angle']}\n"
        f"  request: {data['request']}"
    )


def cmd_list() -> None:
    items = all_followups()
    if not items:
        print("(không có follow-up nào)")
    for path, data in items:
        print(describe(path, data))


def cmd_due(date: str) -> None:
    items = due_followups(parse_date(date).isoformat())
    if not items:
        print(f"(không có follow-up nào cho bản tin {date})")
    for number, (path, data) in enumerate(items, 1):
        print(f"[tin {number}] {describe(path, data)}")


def cmd_path(research_slug: str, date: str) -> None:
    slug = research_slug.removeprefix(PREFIX)
    paths = [p for p, d in due_followups(parse_date(date).isoformat()) if d["slug"] == slug]
    if not research_slug.startswith(PREFIX) or len(paths) != 1:
        fail(f"không có follow-up {research_slug!r} tới hạn ở bản tin {date} (xem: followup.py due {date})")
    print(rel(paths[0]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    for name in ("due", "slug", "query", "title", "angle", "request"):
        add.add_argument(f"--{name}", required=True)
    add.add_argument("--days", type=int, default=DEFAULT_DAYS)
    sub.add_parser("cancel").add_argument("slug")
    sub.add_parser("list")
    sub.add_parser("due").add_argument("date")
    path = sub.add_parser("path")
    path.add_argument("research_slug")
    path.add_argument("date")
    args = parser.parse_args()
    if args.command == "add":
        cmd_add(args)
    elif args.command == "cancel":
        cmd_cancel(args.slug)
    elif args.command == "list":
        cmd_list()
    elif args.command == "due":
        cmd_due(args.date)
    else:
        cmd_path(args.research_slug, args.date)


if __name__ == "__main__":
    main()
