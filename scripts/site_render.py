"""Renderer riêng của Daily News: news/YYYY-MM-DD.md → trang card dashboard (chỉ stdlib).

Template + CSS nằm trong theme/ (người sửa, routine không động vào). Tên trang bài
(briefs/<slug>-<hash>-<date>.html) lấy từ feed.xml của `library feed` nên link trong feed
và link đã gửi Google Chat luôn khớp.
"""

from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from string import Template

WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
ITEM_HEADING = re.compile(r"^###\s+(\d+)\.\s+(.+?)\s*$")
BULLET = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
BOLD = re.compile(r"\*\*(.+?)\*\*")
CODE = re.compile(r"`([^`]+)`")
SUMMARY_PREFIX = re.compile(r"^(?:[-*•]|\d+[.)])\s*")


@dataclass
class Item:
    number: int
    title: str
    bullets: list[str] = field(default_factory=list)
    source: tuple[str, str] | None = None  # (label, url)


@dataclass
class Issue:
    day: date
    href: str  # đường dẫn trang bài, tương đối với news/
    title: str
    items: list[Item]
    paragraphs: list[str]  # nội dung ngoài danh sách tin (ngày không có tin)
    summary: list[str] | None  # 3 dòng tóm tắt từ news/raw/<DATE>-summary.txt (nếu có)


def inline(text: str) -> str:
    """Markdown inline tối thiểu → HTML đã escape (chỉ nhận link http/https)."""
    out = html.escape(text, quote=False)
    out = LINK.sub(lambda m: f'<a href="{html.escape(html.unescape(m.group(2)))}" '
                             f'target="_blank" rel="noopener">{m.group(1)}</a>', out)
    out = BOLD.sub(r"<strong>\1</strong>", out)
    return CODE.sub(r"<code>\1</code>", out)


def summary_path(news_dir: Path, day: date) -> Path:
    return news_dir / "raw" / f"{day.isoformat()}-summary.txt"


def read_summary(news_dir: Path, day: date) -> list[str] | None:
    """Đúng 3 dòng tóm tắt (đã bỏ gạch đầu dòng/số thứ tự), hoặc None nếu thiếu/sai format."""
    path = summary_path(news_dir, day)
    if not path.is_file():
        return None
    lines = [SUMMARY_PREFIX.sub("", line.strip()) for line in path.read_text(encoding="utf-8").splitlines()]
    lines = [line for line in lines if line]
    return lines if len(lines) == 3 else None


def parse_issue(path: Path, day: date, href: str) -> Issue:
    title, items, paragraphs = "", [], []
    current: Item | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif match := ITEM_HEADING.match(line):
            current = Item(int(match.group(1)), match.group(2))
            items.append(current)
        elif (match := BULLET.match(line)) and current is not None:
            text = match.group(1)
            link = LINK.search(text)
            if text.startswith("🔗") and link:
                current.source = (link.group(1), link.group(2))
            else:
                current.bullets.append(text)
        elif line.strip() and current is None and not line.startswith("#"):
            paragraphs.append(line.strip())
    return Issue(day, href, title or f"Daily News {day:%d/%m/%Y}", items, paragraphs,
                 read_summary(path.parent, day))


def item_card(item: Item) -> str:
    bullets = "".join(f"<li>{inline(b)}</li>" for b in item.bullets)
    foot = ""
    if item.source:
        label, url = item.source
        foot = (f'<div class="card-foot"><a href="{html.escape(url)}" target="_blank" '
                f'rel="noopener">🔗 {html.escape(label)} ↗</a></div>')
    return (f'<article class="card" id="tin-{item.number}"><div class="card-head">'
            f'<span class="num">{item.number}</span><h3>{inline(item.title)}</h3></div>'
            f"<ul>{bullets}</ul>{foot}</article>")


def empty_card(issue: Issue) -> str:
    text = " ".join(inline(p) for p in issue.paragraphs).removeprefix("😴").strip() or "Không có tin mới nổi bật."
    return f'<article class="card empty"><div class="big">😴</div><p>{text}</p></article>'


def issue_cards(issue: Issue) -> str:
    return "".join(item_card(i) for i in issue.items) if issue.items else empty_card(issue)


def count_label(issue: Issue) -> str:
    return f"{len(issue.items)} tin" if issue.items else "không có tin mới"


def card_lines(issue: Issue) -> list[str]:
    """1–3 dòng cho card trên trang chủ: tóm tắt đã lưu → tiêu đề các tin → câu 'không có tin'."""
    if issue.summary:
        return issue.summary
    if issue.items:
        return [item.title for item in issue.items[:3]]
    text = " ".join(issue.paragraphs).removeprefix("😴").strip()
    return [text or "Không có tin mới nổi bật."]


def day_card(issue: Issue, *, latest: bool = False) -> str:
    lines = "".join(f"<li>{inline(line)}</li>" for line in card_lines(issue))
    badge = '<span class="badge">Mới nhất</span>' if latest else ""
    return (f'<a class="card day-card" href="{html.escape(issue.href)}">'
            f'<div class="day-head"><h3>{html.escape(issue.title)}</h3>{badge}</div>'
            f'<ul class="summary">{lines}</ul>'
            f'<span class="more">Đọc bản tin →</span></a>')


def render_site(news_dir: Path, theme_dir: Path, pages: dict[date, str]) -> list[Path]:
    """Ghi index.html, briefs/*.html, assets/style.css. `pages`: ngày → href từ feed.xml."""
    issues = sorted(
        (parse_issue(news_dir / f"{day.isoformat()}.md", day, href) for day, href in pages.items()),
        key=lambda issue: issue.day, reverse=True,
    )
    brief_tpl = Template((theme_dir / "brief.html").read_text(encoding="utf-8"))
    index_tpl = Template((theme_dir / "index.html").read_text(encoding="utf-8"))
    written: list[Path] = []

    def write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)

    def nav(other: Issue | None, label: str) -> str:
        return f'<a href="../{html.escape(other.href)}">{label}</a>' if other else "<span></span>"

    for pos, issue in enumerate(issues):
        newer = issues[pos - 1] if pos > 0 else None
        older = issues[pos + 1] if pos + 1 < len(issues) else None
        first = issue.items[0].title if issue.items else "Không có tin mới nổi bật"
        write(news_dir / issue.href, brief_tpl.safe_substitute(
            title=html.escape(issue.title),
            description=html.escape(first),
            weekday=WEEKDAYS[issue.day.weekday()],
            count_label=count_label(issue),
            cards=issue_cards(issue),
            prev_link=nav(older, f"← {older.day:%d/%m/%Y}" if older else ""),
            next_link=nav(newer, f"{newer.day:%d/%m/%Y} →" if newer else ""),
        ))

    latest = issues[0] if issues else None
    total = sum(len(issue.items) for issue in issues)
    stats = "".join(f'<div class="stat"><b>{value}</b><span>{label}</span></div>' for value, label in [
        (len(issues), "số bản tin"),
        (total, "tin đã tổng hợp"),
        (f"{latest.day:%d/%m}" if latest else "—", "số mới nhất"),
    ])
    write(news_dir / "index.html", index_tpl.safe_substitute(
        stats=stats,
        issue_cards="".join(day_card(issue, latest=pos == 0) for pos, issue in enumerate(issues))
        or '<article class="card empty"><p>Chưa có bản tin nào.</p></article>',
        updated=f"{latest.day:%d/%m/%Y}" if latest else "—",
    ))

    css_target = news_dir / "assets" / "style.css"
    css_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(theme_dir / "style.css", css_target)
    written.append(css_target)
    return written
