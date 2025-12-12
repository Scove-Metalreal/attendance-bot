# 🤖 Discord Attendance Bot - Smart Task Assignment

Bot Discord tự động chấm công và giao việc thông minh, tích hợp với Google Sheet.

## ✨ Tính năng chính

### 1. Giao việc thông minh (Smart Task Assignment)

- Bot **tự động giao task phù hợp nhất** khi user vào Voice Channel dựa trên:
  - ✅ Role/Owner (Project Lead, Tech Lead, Level Builder/QA, Gameplay Prog)
  - ✅ Độ ưu tiên (Cao > Trung bình > Thấp)
  - ✅ Ngày bắt đầu (ưu tiên task đã quá hạn hoặc sắp bắt đầu)
  - ✅ Tiến trình (ưu tiên task chưa hoàn thành)

### 2. Tự động đồng bộ Google Sheet

- Đồng bộ tất cả tasks từ Sheet vào database
- Tự động cập nhật: Progress, Status, Deliverables
- Auto-sync mỗi 30 phút

### 3. Tích hợp Git

- Bắt buộc có link Git khi nộp bài (commit/branch/PR)
- Tự động lưu link vào cột Deliverables trên Sheet

### 4. Chấm công tự động

- Tính giờ làm việc trong Voice Channel
- Tự động verify khi đủ điều kiện
- Hỗ trợ làm việc 7 ngày/tuần

## 📋 Yêu cầu

- Python 3.8+
- MySQL 8.0+
- Discord Bot Token
- Google Service Account (credentials.json)
- Google Sheet với cấu trúc như mô tả

## 🚀 Cài đặt

### 1. Clone project và cài đặt dependencies

```bash
pip install discord.py python-dotenv mysql-connector-python gspread
```

### 2. Cấu hình Database

```bash
mysql -u root -p < discord_attendance_bot.sql
```

### 3. Cấu hình .env

Copy file `.env.example` thành `.env` và điền thông tin:

```bash
cp .env.example .env
nano .env
```

### 4. Cấu hình Google Sheet

#### Cấu trúc Sheet (bắt đầu từ dòng 6):

| A                | B                | C                  | D                | E              | F     | G              | H                | I                 | J              | K             | L              | M            |
| ---------------- | ---------------- | ------------------ | ---------------- | -------------- | ----- | -------------- | ---------------- | ----------------- | -------------- | ------------- | -------------- | ------------ |
| **Mã công việc** | **Việc cần làm** | **Mức độ Ưu tiên** | **Chủ sở hữu**   | **Tiến trình** | **%** | **Trạng thái** | **Ngày bắt đầu** | **Ngày kết thúc** | **Thời lượng** | **Giai đoạn** | **Thành phẩm** | **Ghi chú**  |
| F-01             | Design level 1   | Cao                | Level Builder/QA | 5              | 50%   | Đang thực hiện | 10/12/2024       | 15/12/2024        | 5              | Phase 1       |                | Fix lighting |

**Chú ý:**

- Dòng 5: Tiêu đề cột
- Dòng 6+: Nội dung tasks
- Cột E (Tiến trình): Số nguyên 0-100 hoặc phân số (3/10)
- Cột F (%): Tự động tính từ cột E
- Cột L (Thành phẩm): Bot tự động thêm Git links

#### Tạo Service Account:

1. Vào [Google Cloud Console](https://console.cloud.google.com/)
2. Tạo project mới
3. Enable Google Sheets API
4. Tạo Service Account → Download JSON key
5. Đổi tên file thành `credentials.json`
6. Share Google Sheet với email service account

### 5. Cấu hình User Roles trong bot.py

Sửa dict `USER_ROLE_MAPPING` trong `bot.py`:

```python
USER_ROLE_MAPPING = {
    123456789012345678: "Project Lead",      # Discord ID của leader
    987654321098765432: "Tech Lead",         # Discord ID của tech lead
    111111111111111111: "Level Builder/QA",  # ...
    222222222222222222: "Gameplay Prog",
}
```

**Lấy Discord ID:**

- Bật Developer Mode trong Discord (Settings → Advanced)
- Click phải vào user → Copy ID

### 6. Cấu hình Leader IDs

Sửa list `LEADERS` trong `bot.py`:

```python
LEADERS = [
    123456789012345678,  # Discord ID của leader 1
    987654321098765432,  # Discord ID của leader 2
]
```

### 7. Thêm ảnh Reward (Optional)

Tạo folder `reward_images` và thêm ảnh:

```bash
mkdir reward_images
# Copy các file ảnh .jpg, .png, .gif vào folder này
```

### 8. Chạy Bot

```bash
python bot.py
```

## 📖 Hướng dẫn sử dụng

### Cho Team Member:

#### 1. Bắt đầu làm việc

- Vào Voice Channel được chỉ định
- Bot tự động:
  - Giao task phù hợp nhất
  - Bắt đầu tính giờ
  - Cập nhật status thành "Đang thực hiện"

#### 2. Chuyển task (nếu cần)

```
/working_on F-01
```

#### 3. Kiểm tra task của mình

```
/todo
```

#### 4. Xem trạng thái hiện tại

```
/status
```

#### 5. Nộp bài khi hoàn thành

```
/done F-01 https://github.com/user/repo/commit/abc123 100
```

- **Bắt buộc** phải có Git link
- Progress mặc định 100%, có thể điều chỉnh

#### 6. Xem thống kê

```
/my_stats
```

### Cho Leader:

#### 1. Verify task bằng code

```
/verify ABC123
```

#### 2. Approve task trực tiếp

```
/approve F-01
```

#### 3. Reject task

```
/reject F-01
```

#### 4. Cập nhật progress

```
/update_progress F-01 75
```

#### 5. Đồng bộ Sheet thủ công

```
/sync_sheet
```

#### 6. Force checkout user

```
/force_checkout @username
```

#### 7. Xem chi tiết task

```
/task_info F-01
```

## 🔄 Flow hoạt động

### 1. User vào Voice Channel

```
User joins VC
    ↓
Bot check user role
    ↓
Bot tìm task phù hợp nhất:
  • Đúng owner/role
  • Priority cao
  • Deadline gần
  • Progress thấp
    ↓
Start session & update status → "Đang thực hiện"
    ↓
Gửi notification vào Log Channel
```

### 2. User làm việc & nộp bài

```
User hoàn thành task
    ↓
/done F-01 [git_link] [progress%]
    ↓
Bot tạo verify code
    ↓
Update DB: progress, status
    ↓
Sync to Sheet: cột E, F, G
    ↓
Gửi reward + code vào Log Channel
```

### 3. Leader verify

```
Leader gõ /verify [code]
    ↓
Bot verify submission
    ↓
Update session: is_verified = TRUE
    ↓
Check tổng thời gian >= min_work_seconds
    ↓
Cập nhật is_counted = TRUE
    ↓
Add Git link vào Sheet (cột L)
    ↓
Update task status → "Đã hoàn thành"
    ↓
Sync all to Sheet
```

## 📊 Cấu trúc Database

### Table: users

- Lưu thông tin user, role

### Table: tasks

- Sync từ Google Sheet
- Theo dõi tiến trình realtime

### Table: work_sessions

- Lưu lịch sử làm việc
- Tính tổng giờ

### Table: task_submissions

- Lưu code verify
- Link Git commit/branch
- Progress báo cáo

## ⚙️ Settings

Thay đổi trong DB hoặc `.env`:

```sql
-- Thời gian tối thiểu để tính công (giây)
UPDATE settings SET setting_value = '3600' WHERE setting_key = 'min_work_seconds';

-- Giờ làm việc (0-24, hỗ trợ cả tuần)
UPDATE settings SET setting_value = '0' WHERE setting_key = 'work_day_start_hour';
UPDATE settings SET setting_value = '24' WHERE setting_key = 'work_day_end_hour';
```

## 🐛 Troubleshooting

### Bot không giao task phù hợp?

- Kiểm tra `USER_ROLE_MAPPING` có đúng Discord ID không
- Kiểm tra cột "Chủ sở hữu" trong Sheet có đúng với role mapping không
- Chạy `/sync_sheet` để đồng bộ lại

### Không cập nhật lên Sheet?

- Kiểm tra `credentials.json` có đúng không
- Kiểm tra service account đã được share Sheet chưa
- Kiểm tra console logs để xem error

### Session bị stuck?

- Bot tự động fix khi restart
- Hoặc dùng `/force_checkout @user`

### Git link không xuất hiện trên Sheet?

- Kiểm tra cột L (index 11) có đúng không
- Kiểm tra format link có hợp lệ không

## 📝 Lưu ý

1. **Role mapping phải khớp chính xác** giữa bot.py và Sheet
2. **Git link bắt buộc** khi dùng `/done`
3. **Dòng 5 là header**, nội dung từ dòng 6
4. **Cột A là task_code**, phải unique
5. Bot tự động sync Sheet mỗi 30 phút
6. Làm việc 7 ngày/tuần (không nghỉ cuối tuần)

## 🆘 Support

Nếu gặp vấn đề:

1. Check logs trong console
2. Kiểm tra `.env` configuration
3. Verify database schema
4. Test Google Sheet connection

## 📜 License

MIT License - Free to use and modify
