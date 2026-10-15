---
name: news-followup
description: Thêm, huỷ hoặc liệt kê follow-up topic cho bản tin Daily News — khi người dùng reply kiểu "ngày mai báo cáo về phản ứng của cộng đồng về X", "theo dõi X cho bản tin thứ 2", "huỷ theo dõi X", "đang theo dõi gì". Ghi followups/<DUE>-<slug>.json và push lên main qua scripts/followup.sh.
---

# Follow-up topic cho Daily News

Người dùng muốn bản tin của một ngày sau có thêm một tin riêng về một topic. Routine của ngày đó sẽ research topic bằng last30days (topic mode) rồi đặt thành tin đầu tiên của bản tin. Việc của bạn chỉ là ghi chỉ thị lại bằng `scripts/followup.sh`. **Không** research, **không** sửa `news/`, **không** tự chạy git.

## 1. Xác định ngày
- Chạy `TZ=Asia/Ho_Chi_Minh date '+%F %A'` → TODAY. Luôn dùng ngày này, **không** dùng DATE của bản tin trong session (session có thể là của hôm trước).
- Quy đổi: "ngày mai"/không nói gì → TODAY+1; "ngày kia" → TODAY+2; "thứ N" → lần gần nhất sau TODAY; ngày cụ thể → giữ nguyên.
- Luật (script kiểm tra): TODAY < due ≤ TODAY+14; tối đa 3 follow-up cho cùng một ngày. Không cho tạo follow-up cho hôm nay vì bản tin hôm nay đã chạy.

## 2. Soạn các trường
| Tham số | Cách viết |
|---|---|
| `--slug` | ascii kebab-case ≤ 40 ký tự, theo tên topic, vd `gemini-4-argon` (không thêm tiền tố `fu-`) |
| `--title` | tiếng Việt, ngắn: điều người dùng muốn biết, vd `Phản ứng của cộng đồng về Gemini 4 Argon` |
| `--query` | tiếng Anh, 2–6 từ, chỉ tên riêng + từ khoá phân biệt, vd `Gemini 4 Argon`. KHÔNG thêm "reaction/news/latest", năm, tháng. Tên dễ nhầm thì gắn tên hãng (`Argon Gemini`) |
| `--angle` | tiếng Anh hoặc Việt, góc cần tập trung, vd `community reaction: reviews, benchmarks, complaints, comparisons with GPT/Claude` |
| `--days` | cửa sổ research 1–7 ngày (mặc định 2). Sự kiện xảy ra hôm qua/hôm nay → 2; sự kiện cũ hơn → tính từ ngày sự kiện, tối đa 7 |
| `--request` | nguyên văn câu người dùng |

Nếu không rõ topic là gì (vd "theo dõi cái đó") thì hỏi lại người dùng bằng text, không đoán.

## 3. Chạy
```bash
bash scripts/followup.sh add --due <DUE> --slug <slug> --title "<title>" --query "<query>" \
  --angle "<angle>" --days <N> --request "<nguyên văn>"
```
(Bash timeout 120000.) Dùng nháy kép; nếu chuỗi có nháy kép thì đổi thành nháy đơn trong nội dung.

- Exit 0 → script đã commit `followup: add <DUE> <slug>` và push lên main.
- Lỗi luật (ngày, trùng slug, quá 3 follow-up/ngày) → giải thích cho người dùng, đề xuất cách sửa (ngày khác, huỷ cái cũ…).
- Lỗi git/guard/push → báo nguyên văn lỗi, KHÔNG push tay, KHÔNG force, KHÔNG sửa script.

## 4. Báo lại người dùng
Ngắn gọn, tiếng Việt: ngày hiệu lực (thứ + ngày), title, query, vị trí sẽ là tin đầu tiên của bản tin ngày đó (có nhiều follow-up thì xếp theo thứ tự tạo). Nếu research không ra dữ liệu, bản tin vẫn có một tin ngắn ghi "chưa thấy phản ứng đáng kể". Nhắc cách huỷ: "huỷ theo dõi <topic>".

## Huỷ / liệt kê
- "đang theo dõi gì", "list follow-up" → `bash scripts/followup.sh list`, tóm tắt lại.
- "huỷ theo dõi X" → `bash scripts/followup.sh list` để tìm slug khớp X, rồi `bash scripts/followup.sh cancel <slug>`. Không chắc là slug nào thì hỏi lại.
- Muốn sửa follow-up (đổi ngày, đổi góc): `cancel` rồi `add` lại.
