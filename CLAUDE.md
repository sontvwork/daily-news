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
2. **Viết bài** — Claude viết `news/<DATE>.md` bằng tiếng Việt, đúng format, và `news/raw/<DATE>-summary.txt` gồm đúng 3 dòng. File tóm tắt này được dùng cho card trên trang chủ và cho tin Google Chat.
3. **Publish** — [publish.sh](scripts/publish.sh) `<DATE>` chạy lần lượt:
   1. `news.py validate`
   2. `news.py site`
   3. `guard.sh worktree`
   4. commit `news: <DATE>`
   5. `guard.sh outgoing`
   6. push `main`
   7. `news.py verify-live`
   8. `notify.sh success`

   Lỗi ở bất kỳ bước nào → `notify.sh failure <bước>` gửi Google Chat.

`news.py site` gồm 4 việc:
- Chuẩn hoá mtime của `news/YYYY-MM-DD.md`.
- Chạy `library feed` trong **thư mục tạm** và chỉ lấy `feed.xml` về.
- Render trang bằng [site_render.py](scripts/site_render.py) + `theme/`.
- Kiểm tra link local.

## Muốn đổi X → sửa ở đâu
| Muốn đổi | Sửa ở |
|---|---|
| Chủ đề/domain, cửa sổ ngày, nguồn bị loại | [config/news.env](config/news.env): `DOMAINS` (`"slug\|domain"`), `LOOKBACK_DAYS`, `EXCLUDE_SOURCES` |
| URL site | `PAGES_BASE_URL` trong `config/news.env`, cùng các link trong README và ROUTINE_PROMPT |
| Tiêu chí biên tập, cách chấm, format bản tin | [ROUTINE_PROMPT.md](ROUTINE_PROMPT.md) (Bước 1–2). Sửa xong phải **dán lại vào routine**, vì routine giữ bản copy riêng |
| Luật kiểm tra format | `cmd_validate` trong [news.py](scripts/news.py). Giữ khớp với ROUTINE_PROMPT Bước 2 và `parse_issue` trong site_render.py |
| Màu, font, spacing, light/dark | [theme/style.css](theme/style.css) (biến trong `:root` và khối `prefers-color-scheme: dark`) |
| Bố cục trang chủ | [theme/index.html](theme/index.html), placeholder: `$stats $issue_cards $updated`. Mỗi bản tin (ngày) là một card |
| Bố cục trang bài | [theme/brief.html](theme/brief.html), placeholder: `$title $description $weekday $count_label $cards $prev_link $next_link` |
| HTML của card, ô thống kê, nhãn tiếng Việt | [site_render.py](scripts/site_render.py): `item_card` (tin trên trang bài), `day_card` (card ngày trên trang chủ), `render_site` |
| Dòng tóm tắt trên card trang chủ | `news/raw/<DATE>-summary.txt` (3 dòng). Nếu thiếu thì `card_lines` trong site_render.py lấy tiêu đề 3 tin đầu |
| Nội dung tin Google Chat | [notify.sh](scripts/notify.sh) (`success` / `failure`). Nguồn 3 dòng: `news/raw/<DATE>-summary.txt`; fallback nằm ở `cmd_summary` trong news.py |
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
- **Không sửa tay output build:** `news/index.html`, `news/briefs/*.html`, `news/feed.xml`, `news/assets/style.css` đều bị ghi đè mỗi lần build. Muốn đổi thì sửa `theme/` hoặc `site_render.py`, rồi build lại.
- **Không sửa `.claude/skills/last30days/`** (bản vendored). Muốn cập nhật thì chạy `vendor_skill.sh`.
- **Link bài phải giữ ổn định:** tên trang bài có dạng `briefs/<slug>-<hash8>-<date>.html`, lấy từ `feed.xml`. Slug sinh từ H1 của file ngày, hash tính từ topic + tên file. Vì vậy H1 luôn phải là `# Daily News DD/MM/YYYY`; đổi H1 thì link đã gửi vào Chat sẽ gãy.
- **Ngày của entry lấy từ mtime,** nên phải build qua `news.py site`, vì chỉ bước này chuẩn hoá mtime về 12:00Z. Build cần tất định.
- **Hàng rào của routine** (guard.sh):
  - chỉ được đổi `news/**`;
  - không xoá hay đổi tên file;
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
- `--days 1` khá hay cho kết quả "nothing solid". Khi đó vẫn publish trang "😴 Không có tin mới nổi bật", không coi là lỗi.

## Trạng thái hạ tầng (cập nhật 26/09/2026, cần kiểm tra lại trước khi giả định)
- ✅ Repo public, Pages (Actions), số đầu tiên `news: 2026-09-26`, giao diện card dashboard.
- ⏳ Người dùng còn phải tự làm (hướng dẫn trong README):
  - tạo cloud environment `daily-news`;
  - thêm GitHub secret `GCHAT_WEBHOOK_URL`;
  - tạo routine theo [ROUTINE_SETUP.md](ROUTINE_SETUP.md) (cấu hình) + [ROUTINE_PROMPT.md](ROUTINE_PROMPT.md) (nội dung prompt).
