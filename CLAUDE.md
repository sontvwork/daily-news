# Daily News — ghi chú cho Claude

## Cách trả lời
- Communication style: direct, concise, action-oriented over theoretical
- Use headings, emojis, bullet points to make the answer more lively.
- Always answer me in Vietnamese.

## ⚠️ Nếu đang chạy như routine "Daily News"
Chỉ làm theo prompt của routine (bản gốc nằm trong `ROUTINE_PROMPT.md`). Mọi mục "sửa/đổi" bên dưới dành cho session tương tác với người, **không** áp dụng cho routine. Routine chỉ được ghi `news/**` và `.cache/`, và chỉ commit/push qua `scripts/publish.sh`.

## Project là gì
Repo `sontvwork/daily-news` (public) chỉ làm một việc: xuất bản bản tin tiếng Việt hằng ngày về AI ứng dụng trong phát triển phần mềm, gồm AI coding assistants, AI agents cho testing/review/DevOps và tin gọi vốn về dev tool. Nguồn tổng hợp là skill last30days.
- Site: https://sontvwork.github.io/daily-news/. Chạy trên GitHub Pages với source = GitHub Actions ([pages.yml](.github/workflows/pages.yml)), deploy thư mục `news/`.
- Lịch: Claude Code Routine chạy trên cloud lúc 07:00 giờ VN (cron `0 0 * * *` UTC). Workflow [watchdog.yml](.github/workflows/watchdog.yml) chạy 08:30 VN, báo Google Chat nếu chưa có bản tin trong ngày.
- Hướng dẫn setup dành cho người: [README.md](README.md).

## Luồng chạy mỗi ngày
1. **Research** — [research.sh](scripts/research.sh): với mỗi domain, chạy last30days `--discover` theo 3 leg `nominate` → `research` → `finalize`.
   - Giữa leg 1 và leg 2, Claude đọc `discover-nominations.json` và ghi `judgments.json`.
   - Tham số: `--days 1`, `--save-dir .cache/work/<slug>`.
   - Kết quả: `news/raw/<DATE>-<slug>.{md,json}`.
2. **Viết bài** — Claude viết `news/<DATE>.md` bằng tiếng Việt, đúng format, và `news/raw/<DATE>-summary.txt` gồm 1–3 dòng (mỗi dòng 1 tin hot: 1 emoji + câu ngắn, plain text). File tóm tắt này dùng chung cho card trên trang chủ và tin Google Chat.
3. **Publish** — [publish.sh](scripts/publish.sh) `<DATE>` chạy lần lượt:
   1. `sync` — fetch rồi fast-forward `main` lên `origin/main`; nếu HEAD đổi thì exec lại `publish.sh` bản mới
   2. `news.py validate`
   3. `news.py prune` — xoá `news/<ngày>.md`, `news/raw/<ngày>-*`, `news/briefs/<ngày>.html` (và tên cũ `news/briefs/*-<ngày>.html`) có ngày < `DATE − (RETENTION_DAYS − 1)`
   4. `news.py site`
   5. `guard.sh worktree <DATE>`
   6. commit `news: <DATE>` (gồm cả file vừa xoá)
   7. `guard.sh outgoing`
   8. push `main`
   9. `news.py verify-live`
   10. `notify.sh success`

   Lỗi ở bất kỳ bước nào → `notify.sh failure <bước>` gửi Google Chat.

`news.py site` gồm 4 việc:
- Chuẩn hoá mtime của `news/YYYY-MM-DD.md`.
- Chạy `library feed` trong **thư mục tạm**, chỉ lấy `feed.xml` về, rồi đổi `<link href>` của từng entry thành `briefs/<DATE>.html` (`rewrite_feed_links`, sửa trên text nên `<id>` giữ nguyên).
- Render trang bằng [site_render.py](scripts/site_render.py) + `theme/`.
- Kiểm tra link local.

## Muốn đổi X → sửa ở đâu
| Muốn đổi | Sửa ở |
|---|---|
| Chủ đề/domain, cửa sổ ngày, nguồn bị loại | [config/news.env](config/news.env): `DOMAINS` (`"slug\|domain"`), `LOOKBACK_DAYS`, `EXCLUDE_SOURCES` |
| URL site | `PAGES_BASE_URL` trong `config/news.env`, cùng các link trong README và ROUTINE_PROMPT |
| Số ngày lưu trữ | `RETENTION_DAYS` trong `config/news.env` (hằng số, news.py tự parse). Mẫu file được xoá: `DATED_FILES` trong news.py **và** `DATED_RES` trong guard.sh — sửa cả hai |
| Tiêu chí biên tập, cách chấm, format bản tin | [ROUTINE_PROMPT.md](ROUTINE_PROMPT.md) (Bước 1–2). Sửa xong phải **dán lại vào routine**, vì routine giữ bản copy riêng |
| Luật kiểm tra format | `cmd_validate` trong [news.py](scripts/news.py). Giữ khớp với ROUTINE_PROMPT Bước 2 và `parse_issue` trong site_render.py |
| Màu, font, spacing, light/dark | [theme/style.css](theme/style.css) (biến trong `:root` và khối `prefers-color-scheme: dark`) |
| Bố cục trang chủ | [theme/index.html](theme/index.html), placeholder: `$stats $issue_cards $updated`. Mỗi bản tin (ngày) là một card |
| Bố cục trang bài | [theme/brief.html](theme/brief.html), placeholder: `$title $description $weekday $count_label $cards $prev_link $next_link` |
| Trang 404 (link bản tin đã quá hạn) | [theme/404.html](theme/404.html), placeholder: `$base $retention_days`. Có `<base href>` = path của `PAGES_BASE_URL`, vì Pages trả 404 ngay tại URL hỏng |
| HTML của card, ô thống kê, nhãn tiếng Việt | [site_render.py](scripts/site_render.py): `item_card` (tin trên trang bài), `day_card` (card ngày trên trang chủ), `render_site` |
| Dòng tóm tắt (card trang chủ + tin Google Chat, dùng chung) | `news/raw/<DATE>-summary.txt` (1–3 dòng; luật viết ở ROUTINE_PROMPT Bước 2, luật kiểm tra ở `check_summary` trong news.py). Cả hai nơi lấy qua `summary_lines` trong site_render.py; nếu thiếu file thì hàm này lấy tiêu đề 3 tin đầu |
| Khung tin Google Chat | [notify.sh](scripts/notify.sh) (`success`: tiêu đề + dòng tóm tắt + link; `failure`) |
| Tên trang bài (`briefs/<DATE>.html`) | `brief_href` trong news.py, cùng mẫu briefs trong `DATED_FILES` (news.py) **và** `DATED_RES` (guard.sh) |
| Phạm vi routine được phép sửa, luật chặn | [guard.sh](scripts/guard.sh) |
| Giờ chạy | Cấu hình routine trên claude.ai/code/routines (không nằm trong repo). Giờ của watchdog: `watchdog.yml` |
| Phiên bản last30days | `scripts/vendor_skill.sh [ref]`. Commit đang pin nằm trong `.claude/skills/last30days/.vendored-from` |

## Lệnh hay dùng
```bash
DATE=$(TZ=Asia/Ho_Chi_Minh date +%F)
python3 scripts/news.py site "$DATE"          # build lại feed + mọi trang (tất định: chạy lại không sinh diff)
open news/index.html                           # xem thử local
bash scripts/publish.sh "$DATE" --no-push      # validate + build + guard, tin nhắn ở chế độ dry-run
DRY_RUN=1 bash scripts/notify.sh failure "$DATE" test 'thử "ký tự"'
bash scripts/research.sh status <slug> "$DATE" # outcome + tình trạng từng nguồn
python3 scripts/news.py verify-live "$DATE" --base https://sontvwork.github.io/daily-news
# Chụp màn hình để kiểm tra giao diện (mobile: nhúng trang vào iframe rộng 390px, vì headless có giới hạn bề rộng cửa sổ):
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
  --window-size=1280,1500 --screenshot=<scratchpad>/index.png "file://$PWD/news/index.html"
```
Bản local có `.env.local` (đã gitignore) chứa `GCHAT_WEBHOOK_URL`, các script tự `source` file này. Nghĩa là chạy `notify.sh` hay `publish.sh` mà **không** đặt `DRY_RUN=1` thì tin sẽ gửi thật. Tuyệt đối không in hay commit nội dung file này.

## Bất biến — đừng phá
- **Không sửa tay output build:** `news/index.html`, `news/404.html`, `news/briefs/*.html`, `news/feed.xml`, `news/assets/style.css` đều bị ghi đè mỗi lần build. Muốn đổi thì sửa `theme/` hoặc `site_render.py`, rồi build lại.
- **Không sửa `.claude/skills/last30days/`** (bản vendored). Muốn cập nhật thì chạy `vendor_skill.sh`.
- **Link bài phải giữ ổn định:** tên trang bài là `briefs/<DATE>.html`. Engine đặt link dạng `<slug>-<hash8>-<date>.html`, `news.py site` đổi lại thành mẫu này trong `feed.xml`; mọi nơi khác (trang chủ, prev/next, `news.py link` → Google Chat, verify-live) đọc href từ feed. `<id>` của entry vẫn do engine sinh từ slug H1 + hash, nên H1 luôn phải là `# Daily News DD/MM/YYYY`; đổi H1 thì feed reader coi là bài mới. Link chỉ sống trong `RETENTION_DAYS` ngày; sau đó trang bị prune và Pages trả `404.html`.
- **Ngày của entry lấy từ mtime,** nên phải build qua `news.py site`, vì chỉ bước này chuẩn hoá mtime về 12:00Z. Build cần tất định.
- **Hàng rào của routine** (guard.sh):
  - chỉ được đổi `news/**`;
  - không xoá hay đổi tên file, **trừ** file có ngày của bản tin đã quá hạn (mốc tính từ DATE trong tham số `worktree` / message từng commit; DATE ở tương lai hoặc không có `news/DATE.md` thì cấm xoá);
  - commit message đúng `news: YYYY-MM-DD`;
  - không có merge commit;
  - không để lộ secret.
- **Git:** không force push, không rewrite history đã push. `main` phải **không** bị protect. Mọi commit trên `main` phải do `sontvwork` author; repo-local git config đang đặt `user.email=67277784+sontvwork@users.noreply.github.com`. Nếu không, routine sẽ bị từ chối push.
- **Secrets** chỉ nằm ở 3 nơi: env của cloud environment, GitHub secret `GCHAT_WEBHOOK_URL`, và `.env.local`. Không bao giờ nằm trong repo.
- **Tương thích bash 3.2 (macOS):** không dùng `mapfile`, không dùng cờ `I` của sed, không dùng `cut -c` với UTF-8 (cắt chuỗi bằng Python).

## Commit bảo trì (code / theme / config / docs)
- Commit riêng, message mô tả thật, kết thúc bằng trailer `Co-Authored-By`. Push **trước** khi chạy `publish.sh`. Lý do:
  - `guard.sh worktree` chặn mọi thay đổi chưa commit nằm ngoài `news/`;
  - `guard.sh outgoing` chặn mọi commit không phải `news:` trong khoảng `origin/main..HEAD`.
- Sửa `theme/` hoặc `site_render.py` xong: chạy `news.py site <ngày mới nhất>`, commit cả `news/` đã render lại vào cùng commit bảo trì, push, rồi chạy `verify-live`.
- Sửa `ROUTINE_PROMPT.md` xong: nhắc người dùng dán lại prompt vào routine.

## Gotchas đã biết
- Pha research sâu của last30days cho số tương tác bị nhiễu (lẫn video không liên quan), còn `evidence_urls` thường chỉ là post mạng xã hội. Khi viết bài, lấy dữ kiện và URL gốc từ `discover-nominations.json`.
- Ở máy local, Reddit hay trả `Connection refused`; X và HN vẫn chạy. Trên cloud, IP datacenter cũng dễ bị chặn. Environment cần Network = Full và `SETUP_COMPLETE=true`.
- Docs Routines (kiểm tra ngày 26/09/2026) không có toggle "Allow unrestricted branch pushes". Push thẳng `main` chạy được khi đáp ứng các điều kiện ở mục Git phía trên.
- **Sandbox cloud dùng lại bản clone cũ** (log ghi "Fetching repository" thay vì "Cloning"): session bắt đầu ở branch `claude/*`, còn `main` và `origin/main` local vẫn nằm ở commit của lần clone đầu. Vì vậy ROUTINE_PROMPT Bước 0 bắt buộc `git pull --ff-only origin main`, `publish.sh` có bước `sync` (fast-forward, rồi exec lại bản mới), và mọi lệnh fetch dùng refspec tường minh `+refs/heads/main:refs/remotes/origin/main`. Routine không tự `rebase` được, vì auto-mode classifier chặn; git trong script thì không bị chặn.
- **Image cloud có `python3` = 3.11**, nhưng cài sẵn `python3.12`/`python3.13`. `research.sh` (`pick_python`) và `news.py` (`engine_python`) tự chọn bản ≥ 3.12 để chạy engine. `LAST30DAYS_PYTHON` dùng để ép một bản cụ thể.
- `--days 1` khá hay cho kết quả "nothing solid". Khi đó vẫn publish trang "😴 Không có tin mới nổi bật", không coi là lỗi.

## Trạng thái hạ tầng (cập nhật 26/09/2026, cần kiểm tra lại trước khi giả định)
- ✅ Repo public, Pages (Actions), số đầu tiên `news: 2026-09-26`, giao diện card dashboard.
- ⏳ Người dùng còn phải tự làm (hướng dẫn trong README):
  - tạo cloud environment `daily-news`;
  - thêm GitHub secret `GCHAT_WEBHOOK_URL`;
  - tạo routine theo [ROUTINE_SETUP.md](ROUTINE_SETUP.md) (cấu hình) + [ROUTINE_PROMPT.md](ROUTINE_PROMPT.md) (nội dung prompt).
