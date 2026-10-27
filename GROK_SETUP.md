# Grok Automation setup — Daily News

Grok (tính năng "Tự động hoá") thu thập tin trên X mỗi ngày rồi commit vào repo [sontvwork/daily-news-inbox](https://github.com/sontvwork/daily-news-inbox), ở file `grok/<DATE>.json`. Routine Daily News sẽ đọc file này và gộp vào nhóm tin ứng viên. Tính năng đang thử nghiệm, routine chưa đọc file.

| Mục | Giá trị |
|---|---|
| Lịch | Hằng ngày 05:30 giờ VN, trước routine (07:00) |
| Quyền GitHub | Chỉ được vào `sontvwork/daily-news-inbox`, KHÔNG được vào `sontvwork/daily-news` |
| Output | `grok/<DATE>.json` (schema `grok-inbox/1`), commit message `grok: <DATE>` |
| Prompt | Nội dung file [GROK_PROMPT.md](GROK_PROMPT.md), dán nguyên văn |

**Tiêu chí:** mục 2 của prompt dựa trên khối "Tiêu chí biên tập" của [ROUTINE_PROMPT.md](ROUTINE_PROMPT.md), nhưng từ v6.1 đã **cố ý khác** (thêm "bài viết hot trên X liên quan AI", bỏ "khảo sát mức độ tiếp nhận" và "chủ đề AI chung chung" khỏi danh sách loại bỏ) và viết bằng tiếng Anh. Không cần chép nguyên văn nữa; khi đổi định hướng biên tập ở ROUTINE_PROMPT thì xem lại mục 2 cho khớp ý. Sửa prompt xong thì dán lại vào Grok.

## Lịch sử chỉnh sửa

### v6.1 (27/10/2026)
- Người dùng tự sửa: mục 2 mở rộng sang bài viết hot trên X liên quan AI; mục 1 bỏ ngoại lệ "bài cũ đang hot"; `x_posts` chỉ còn bài gốc (bỏ bài phản hồi); bỏ một số luật trung thực.
- Bỏ trường `reaction`: Grok bịa ở mọi phiên bản (ngày 25/10 còn tóm tắt một tweet bịa ID), và routine không dùng được (bình luận chỉ lấy từ `deep.json`).
- Dịch toàn bộ prompt sang tiếng Anh, nội dung giữ nguyên.

### v6 (27/10/2026), sau 3 ngày chạy theo lịch 05:30 với v4.1 — ĐANG THỬ, không hơn v4.1 thì rollback
Kết quả v4.1 (25–27/10): **đúng 3 tin mỗi ngày**, dù prompt cho tối đa 15 (các lần chạy tay ngày 24/10 ra 4–6 tin; automation cũ dạng markdown ra 6 tin). Chỉ 1/9 tin trùng bản tin routine; mỗi ngày Grok thêm được 1–2 tin X đáng giá mà last30days không có. 18/19 tweet thật, 1 tweet bịa ID (`…858000000000000`).

| Thay đổi | Lý do |
|---|---|
| Thêm mục "Cách làm" 2 bước: lập danh sách mọi tin (mục tiêu 8–15, dưới 8 thì tìm thêm) → điền trường; không bỏ tin vì thiếu `primary_url`/phản hồi | Mỗi tin quá nhiều việc nên Grok dừng ở 3 tin |
| Schema gọn (giữ `grok-inbox/1`, dữ liệu cũ chưa dùng): bỏ `x_posts[].text`, `x_posts[].posted_at`, `why_hot`, `confidence`; `x_posts` = bài gốc + tối đa 1 phản hồi; `facts` 1–3 dữ kiện | Bớt việc; nguyên văn, giờ đăng, tương tác thật sẽ lấy qua fxtwitter trong `grok.py` |
| Không gợi ý truy vấn cụ thể | Người dùng chốt: chỉ đưa chủ đề, để Grok tự tìm theo cách của nó |
| Cửa sổ: bài cũ hơn 24 giờ vẫn lấy nếu đang được thảo luận sôi nổi; không lọc tin cũ | Tránh trùng do routine lo (đọc 2 bản tin trước) |
| Ví dụ `primary_url` cho release Claude Code; URL bài X phải chép từ kết quả tìm kiếm | Link changelog chung lặp 3 lần; 1 tweet bịa ID |
| "Đặc biệt chú ý thảo luận hot" → "gồm cả tin công bố trên X và thảo luận hot" | Thế mạnh đo được của Grok là tin công bố trước trên X |

Rollback: `.cache/grok/GROK_PROMPT.v4.1.md` (chỉ có ở máy local) → chép đè lên `GROK_PROMPT.md`, rồi dán lại vào Grok.

### v4.1 (24/10/2026): rollback v5.1 về v4 + 1 dòng "làm từ đầu"
Lần chạy v5.1 (23:15) so với v4: số tin trong cửa sổ 24 giờ bằng nhau (4 so với 4), nhưng v5.1 kém về độ chính xác: 3 tin có `reaction` dù không có bài phản hồi nào (v4: 0), 2 tin ngoài cửa sổ 24 giờ (Artificial Analysis ~40 giờ, Functionize ~32 giờ; v4: 0), 2/6 tin không có bài X (v4: 0/4). Theo thỏa thuận "tệ hơn thì rollback" → quay về v4. Bản v5.1 lưu ở `.cache/grok/GROK_PROMPT.v5.1.md`.

Phát hiện: output v5.1 chỉ là bản **vá** của file v5 (diff 35 dòng; 3 câu `reaction` giống hệt từng chữ). Tức là khi chạy lại trong cùng ngày, Grok đọc file cũ rồi sửa chứ không làm lại từ đầu, nên các lần so sánh cùng ngày không độc lập. → Thêm vào mục Commit: "tìm và viết nội dung từ đầu; không đọc các file grok/*.json đã có".

**Lần chạy v4.1 (23:24):** viết lại gần hết file (diff 48+/62−, lời văn khác hẳn), có vẻ dòng "làm từ đầu" có tác dụng. 5 tin, cả 5 trong cửa sổ 24 giờ; 4/4 tweet thật, 5/5 URL trả 200; 1 tin mới (Cloudflare security-audit-skill). Vẫn còn 2 tin có `reaction` dù chỉ có bài chính thức → lỗi này có ở cả v4 lẫn v5, prompt không trị dứt được; `grok.py` sẽ tự bỏ `reaction`/`why_hot` khi `x_posts` không có bài `official: false`. **Chốt v4.1**, chờ dữ liệu chạy theo lịch nhiều ngày.

### v5 (24/10/2026), dựng lại từ prompt automation Grok đang chạy tốt — ĐANG THỬ, tệ hơn v4 thì rollback
So sánh ngày 24/10: automation cũ (prompt ngắn, tự nhiên, output markdown không có link) bắt được 6 tin; v4 bắt được 4 tin. Gộp mọi lần chạy được 10 tin khác nhau. last30days **không bắt được tin nào** trong các tin của Grok, kể cả tin ra mắt chính thức có tương tác lớn trên X (Cursor Computer Use, Claude MCP Tasks, Codex CLI 0.164.0); ngược lại, last30days bắt tốt tin thảo luận từ Hacker News/Reddit. Vì vậy thế mạnh của Grok là **tin công bố trước trên X**, không phải tin thảo luận như định hướng của v4.

| Thay đổi | Lý do |
|---|---|
| Cấu trúc thẻ `<persona>/<task>/<steps>/<constraint>/<output_format>/<commit>` theo prompt automation cũ | Grok đã chạy tốt với cách diễn đạt này |
| Tách bước: tìm tin → gắn nguồn → ghi JSON | Để phần định dạng không làm Grok tìm ít tin đi |
| Bỏ đoạn "đặc biệt chú ý thảo luận hot"; thêm "ưu tiên tin công bố/bàn tán trên X (tài khoản chính thức, changelog, người trong cuộc)" | Đó là chỗ last30days đang hụt |
| Luật trung thực rút còn 4 dòng | Giảm gánh nặng của prompt |
| Schema: bỏ `why_hot`, `confidence` | Bớt trường cần điền |

**Lần chạy v5 lúc 23:06:** 6 tin (v4: 4), 4/4 tweet thật, thêm 1 tin mới (Artificial Analysis Coding Agent Index v2.0, nhưng đăng ~40 giờ trước, ngoài cửa sổ 24 giờ). Thiếu MCP Tasks và tin nhân sự mà v3/v4 có. Lỗi tái xuất hiện vì v5 bỏ bớt luật: 3 tin có `reaction` dù `x_posts` không có bài phản hồi nào (giống lỗi v1); `primary_url` của tin Cursor là link x.com. → v5.1 thêm lại 2 dòng: `primary_url` phải là trang ngoài X, `reaction` chỉ tóm tắt bài phản hồi có trong `x_posts`.

Cách rollback: bản v4 lưu ở `.cache/grok/GROK_PROMPT.v4.md` (chỉ có ở máy local) → chép đè lên `GROK_PROMPT.md`, rồi dán lại vào Grok.

### v4 (24/10/2026), sau lần chạy v3 lúc 22:32
Kết quả lần thử: 3 tin, 5/5 tweet khớp khi đối chiếu qua fxtwitter, dữ kiện đều có trong nguồn. Vấn đề chính: độ phủ thấp, mỗi lần chạy ra một nhóm tin khác (gộp 3 lần chạy được 7 tin, mỗi lần chỉ bắt được khoảng một nửa). Định hướng: last30days đã làm tốt mảng tin ra mắt chính thức; Grok bù vào mảng **thảo luận hot trên X**, liệt kê rộng, để routine lọc lại.

| Thay đổi | Lý do |
|---|---|
| Thêm đoạn "đặc biệt chú ý thảo luận hot" + quét rộng (từ khoá, tài khoản chính thức, bài nhiều tương tác), "liệt kê mọi tin đạt tiêu chí", tối đa 15 item | Tăng độ phủ; routine lọc lại |
| Bỏ "ít tin mà chính xác tốt hơn", "hoặc bỏ item", giới hạn 2 tin chỉ có trên web, luật lọc chặt bài phản hồi | Siết quá mức làm Grok dừng sớm |
| Bỏ mọi giới hạn tính bằng ký tự (title, text) | LLM không đếm được ký tự; v3 trích 421–801 ký tự dù prompt ghi 280 |
| Khối tiêu chí chép nguyên văn ROUTINE_PROMPT, bỏ "tin đồn, meme, quảng cáo/affiliate" | Dễ đồng bộ; routine lọc lại |
| Schema: thêm `category: "discussion"` và trường `why_hot` | Tin thảo luận cần nói rõ đang bàn gì, vì sao |

Hệ quả: tin thảo luận phần lớn có `primary_url: null`, nên routine bắt buộc phải đọc tweet qua `api.fxtwitter.com` để có dữ kiện kiểm chứng.

### v3 (24/10/2026), sau lần chạy v2 lúc 22:24
Kết quả lần thử: 3 tin, JSON hợp lệ, 3/3 tweet mới khớp khi đối chiếu qua fxtwitter, dữ kiện Kimi chép đúng nguyên văn blog. `reaction: null` đúng chỗ. `primary_url: null` của tin Cursor là đúng, vì changelog Cursor không có bài nào về Computer Use. Không còn tin chỉ có trên web (giới hạn cho phép 2). Các lỗi đã sửa trong prompt:

| Lỗi | Sửa |
|---|---|
| Tin Claude Code: `primary_url` là trang changelog chung của mọi phiên bản (lần trước là trang release của đúng phiên bản) | Chọn URL cụ thể nhất cho đúng tin, không dùng trang tổng hợp |
| Tin Kimi: bài phản hồi chỉ là "dude this benchmark result is INSANE" | Bỏ bài chỉ cảm thán |
| Tin Claude Code: bài 0 like chỉ tóm tắt lại release notes | Bỏ bài tóm tắt lại nội dung tin/release notes; bài ít tương tác chỉ lấy khi có thử nghiệm cụ thể |

### v2 (24/10/2026), sau lần chạy thử `grok/2026-10-24.json`
Kết quả lần thử: JSON hợp lệ, 5/5 URL trả 200, 5/5 tweet khớp khi đối chiếu qua fxtwitter, dữ kiện Claude Code khớp nguyên văn CHANGELOG. Các lỗi đã sửa trong prompt:

| Lỗi | Sửa |
|---|---|
| Có `reaction` dù `x_posts` rỗng (tin Copilot) hoặc chỉ có 1 bài đăng lại bằng tiếng Thái (tin Claude Code) | `reaction` chỉ viết khi có bài phản hồi thực chất của dev, không có thì `null`; cấm khái quát kiểu "users noted…" |
| Một số dữ kiện không tìm thấy trong nguồn (Kimi: "2.8T/104B", "$2/$10"; Teams: "reproduce bugs, paid plan, sandbox") | Mỗi dữ kiện phải đọc được trong `primary_url` hoặc `x_posts` |
| `primary_url` = `cursor.com/download` | Cấm trang download/trang chủ/pricing/landing page |
| `x_posts` chứa bài dịch lại tin, 0 like | Bỏ bài đăng lại/dịch lại; ưu tiên 1 bài chính thức + phản hồi của dev |
| 2/5 tin chỉ lấy từ web, không có bài X nào | Tin chỉ có trên web tối đa 2 item |

### v1 (24/10/2026)
Bản đầu tiên.
