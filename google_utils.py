# import gspread
import os
import json
from datetime import datetime

# Tên file JSON key bạn tải về
CREDENTIALS_FILE = 'credentials.json'

# URL file Sheet của bạn
SHEET_URL = "https://docs.google.com/spreadsheets/d/1OVh-z8rZbb7z-zPbKKbkYSFg1tLDcRMjMGtCoJAb7SQ/edit"


# Kết nối Google Sheet
def get_gspread_client():
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"❌ Không tìm thấy file {CREDENTIALS_FILE}")
        return None

    gc = gspread.service_account(filename=CREDENTIALS_FILE)
    return gc


def get_sheet():
    client = get_gspread_client()
    if not client: return None

    try:
        # Mở sheet bằng URL
        sh = client.open_by_url(SHEET_URL)
        # Chọn WorkSheet đầu tiên (hoặc tên cụ thể)
        worksheet = sh.sheet1
        return worksheet
    except Exception as e:
        print(f"❌ Lỗi kết nối Sheet: {e}")
        return None


# --- HÀM LẤY TASK THEO USER ---
def get_assigned_task_from_sheet(role_name_in_sheet):
    """
    Tìm task chưa hoàn thành dựa trên 'Chủ sở hữu' (Cột D)
    """
    ws = get_sheet()
    if not ws: return None, None

    # Lấy toàn bộ dữ liệu. Vì Header ở dòng 4, ta lấy từ dòng 4 trở đi.
    # Cấu trúc cột dựa trên file bạn gửi:
    # Col A (0): Mã công việc
    # Col B (1): Việc cần làm
    # Col C (2): Mức độ ưu tiên
    # Col D (3): Chủ sở hữu
    # Col G (6): Trạng thái

    # Lấy tất cả giá trị (list of lists)
    all_values = ws.get_all_values()

    # Bỏ qua 3 dòng đầu rỗng/ngày tháng, bắt đầu check từ dòng 5 (index 4)
    # Header là index 3 (Dòng 4)

    for i, row in enumerate(all_values):
        if i < 4: continue  # Bỏ qua header và các dòng trên

        # Kiểm tra độ dài row để tránh lỗi index
        if len(row) < 7: continue

        task_code = row[0]  # Mã
        task_name = row[1]  # Tên việc
        owner = row[3]  # Chủ sở hữu (VD: 2. Lead Programmer)
        status = row[6]  # Trạng thái (VD: Đang thực hiện, Đã hoàn thành)

        # Logic lọc task:
        # 1. Chủ sở hữu khớp với Role của User
        # 2. Trạng thái KHÔNG PHẢI "Đã hoàn thành"
        if role_name_in_sheet in owner and "Đã hoàn thành" not in status:
            return {
                "task_code": task_code,
                "task_name": task_name,
                "row_index": i + 1  # Lưu lại số dòng để sau này update (1-based index)
            }

    return None


# --- HÀM UPDATE TRẠNG THÁI ---
def update_task_status_in_sheet(row_index, new_status="Đang chờ duyệt", percent="100%"):
    """
    Cập nhật cột Trạng thái (Col G - 7) và Phần trăm (Col F - 6)
    """
    ws = get_sheet()
    if not ws: return False

    try:
        # Cập nhật cột F (Phần trăm) - Cột thứ 6
        ws.update_cell(row_index, 6, percent)

        # Cập nhật cột G (Trạng thái) - Cột thứ 7
        ws.update_cell(row_index, 7, new_status)
        return True
    except Exception as e:
        print(f"❌ Lỗi update sheet: {e}")
        return False