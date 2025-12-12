# Updated google_utils.py - Correct Column Mapping
import gspread
import os
import re
from datetime import datetime

CREDENTIALS_FILE = 'credentials.json'
SHEET_URL = "https://docs.google.com/spreadsheets/d/195ncY5mzzWwvRRpq2c_5ZZ_BS6AMFFTfYgIDw2j5RCk/edit?gid=857493313#gid=857493313"  # Thay bằng URL Sheet mới của bạn

# Column mapping (0-indexed) - CORRECTED
COL_MAP = {
    'task_code': 0,        # A - Mã công việc
    'task_name': 1,        # B - Việc cần làm
    'priority': 2,         # C - Mức độ Ưu tiên
    'owner': 3,            # D - Chủ sở hữu
    'progress': 4,         # E - Tiến trình (số)
    'percent': 5,          # F - Phần trăm (%)
    'status': 6,           # G - Trạng thái
    'start_date': 7,       # H - Ngày bắt đầu
    'end_date': 8,         # I - Ngày kết thúc
    'duration': 9,         # J - Thời lượng
    'phase': 10,           # K - Giai đoạn
    'deliverables': 11,    # L - Thành phẩm (Git links)
    'notes': 12            # M - Ghi chú
}

def get_gspread_client():
    """Connect to Google Sheets API"""
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"❌ Không tìm thấy file {CREDENTIALS_FILE}")
        return None
    return gspread.service_account(filename=CREDENTIALS_FILE)

def get_sheet():
    """Get worksheet instance"""
    client = get_gspread_client()
    if not client: 
        return None
    try:
        sh = client.open_by_url(SHEET_URL)
        return sh.sheet1
    except Exception as e:
        print(f"❌ Lỗi kết nối Sheet: {e}")
        return None

def parse_date(date_str):
    """Parse date from DD/MM/YYYY format"""
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str.strip(), '%d/%m/%Y').date()
    except:
        # Try other formats
        try:
            return datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
        except:
            return None

def parse_progress(progress_str):
    """
    Extract numeric progress from various formats:
    - '50%' -> 50
    - '50' -> 50
    - '3/10' -> 30
    - '0.5' -> 50
    """
    if not progress_str or not progress_str.strip():
        return 0
    
    s = progress_str.strip()
    
    # Handle percentage
    if '%' in s:
        try:
            return int(float(s.replace('%', '')))
        except:
            return 0
    
    # Handle fraction like '3/10'
    if '/' in s:
        try:
            parts = s.split('/')
            current = float(parts[0])
            total = float(parts[1])
            if total == 0:
                return 0
            return int((current / total) * 100)
        except:
            return 0
    
    # Handle decimal like 0.5
    try:
        num = float(s)
        if num <= 1.0:  # Assume it's a decimal
            return int(num * 100)
        else:  # Assume it's already a percentage
            return int(min(num, 100))
    except:
        return 0

def get_all_tasks():
    """
    Fetch all tasks from sheet starting from row 6 (0-indexed row 5)
    Row 5 (index 4) = Headers
    Row 6+ (index 5+) = Data
    """
    ws = get_sheet()
    if not ws:
        print("❌ Không thể kết nối Google Sheet")
        return []

    try:
        all_values = ws.get_all_values()
    except Exception as e:
        print(f"❌ Lỗi đọc Sheet: {e}")
        return []
    
    # Debug: Show first few rows
    print(f"📊 Sheet có {len(all_values)} dòng")
    print("Debug: 5 dòng đầu:")
    for i, row in enumerate(all_values[:5], start=1):
        print(f"  Dòng {i}: {row[:4] if len(row) >= 4 else row}")
    
    if len(all_values) < 6:
        print("⚠️ Sheet chưa có dữ liệu (cần ít nhất 6 dòng)")
        return []
    
    # Row 5 (index 4) should be headers
    headers = all_values[4] if len(all_values) > 4 else []
    print(f"\n📋 Headers (Dòng 5): {headers[:8] if len(headers) >= 8 else headers}")
    
    tasks = []
    
    # Start from row 6 (index 5)
    for i, row in enumerate(all_values[5:], start=6):
        # Ensure row has enough columns
        if len(row) < 4:  # At least need task_code, name, priority, owner
            continue
        
        # Get task code from column A (index 0)
        task_code = row[COL_MAP['task_code']].strip() if len(row) > COL_MAP['task_code'] and row[COL_MAP['task_code']] else ""
        
        # Skip empty rows, headers, week numbers, or section dividers
        if not task_code:
            continue
        
        # Skip if looks like header or week number
        if task_code.lower() in ['mã công việc', 'việc cần làm', 'task', 'week']:
            continue
        
        # Skip pure numbers or "Tuần X" patterns
        if task_code.isdigit() or re.match(r'^(Tuần|Week)\s*\d+', task_code, re.IGNORECASE):
            continue
        
        # Skip rows that look like numbering (1., 2., etc)
        if re.match(r'^\d+\.$', task_code):
            continue
        
        # Get task name from column B
        task_name = row[COL_MAP['task_name']].strip() if len(row) > COL_MAP['task_name'] and row[COL_MAP['task_name']] else ""
        
        # Skip if no task name (likely invalid row)
        if not task_name:
            continue
        
        # Parse all columns
        priority = row[COL_MAP['priority']].strip() if len(row) > COL_MAP['priority'] else ""
        owner = row[COL_MAP['owner']].strip() if len(row) > COL_MAP['owner'] else ""
        
        # Progress from column E (number)
        progress_str = row[COL_MAP['progress']].strip() if len(row) > COL_MAP['progress'] else "0"
        progress_num = parse_progress(progress_str)
        
        # Percent from column F (should auto-calculate, but we read it anyway)
        percent_str = row[COL_MAP['percent']].strip() if len(row) > COL_MAP['percent'] else f"{progress_num}%"
        
        # Status from column G
        status = row[COL_MAP['status']].strip() if len(row) > COL_MAP['status'] else "Chưa bắt đầu"
        
        # Dates
        start_date = parse_date(row[COL_MAP['start_date']]) if len(row) > COL_MAP['start_date'] else None
        end_date = parse_date(row[COL_MAP['end_date']]) if len(row) > COL_MAP['end_date'] else None
        
        # Duration
        duration_str = row[COL_MAP['duration']].strip() if len(row) > COL_MAP['duration'] else ""
        duration = None
        if duration_str:
            try:
                # Extract number from string like "5 days" or "5"
                duration = int(re.search(r'\d+', duration_str).group())
            except:
                duration = None
        
        # Phase
        phase = row[COL_MAP['phase']].strip() if len(row) > COL_MAP['phase'] else ""
        
        # Deliverables (Git links)
        deliverables = row[COL_MAP['deliverables']].strip() if len(row) > COL_MAP['deliverables'] else ""
        
        # Notes
        notes = row[COL_MAP['notes']].strip() if len(row) > COL_MAP['notes'] else ""
        
        # Create task object
        task = {
            "task_code": task_code,
            "task_name": task_name,
            "priority": priority,
            "owner": owner,
            "progress": progress_num,
            "progress_percent": f"{progress_num}%",
            "status": status,
            "start_date": start_date.strftime('%Y-%m-%d') if start_date else None,
            "end_date": end_date.strftime('%Y-%m-%d') if end_date else None,
            "duration": duration,
            "phase": phase,
            "deliverables": deliverables,
            "notes": notes,
            "row_index": i  # Actual row number in sheet (1-indexed)
        }
        
        tasks.append(task)
        
        # Debug first few tasks
        if len(tasks) <= 3:
            print(f"✅ Task {len(tasks)}: [{task_code}] {task_name[:30]}... | Owner: {owner} | Row: {i}")
    
    print(f"\n✅ Tổng cộng: Parsed {len(tasks)} tasks hợp lệ từ Sheet.")
    return tasks

def update_task_in_sheet(row_index, progress=None, status=None, deliverables=None):
    """
    Update task in sheet
    - row_index: Row number in sheet (1-indexed, e.g., 6, 7, 8...)
    - progress: Number 0-100 for column E (Tiến Trình) - Column F (%) will auto-calculate from sheet formula
    - status: String for column G (Trạng thái)
    - deliverables: String for column L (Thành phẩm) - will REPLACE existing value
    """
    ws = get_sheet()
    if not ws:
        print("❌ Không thể kết nối Sheet")
        return False

    try:
        updates = []
        
        # Update progress (Column E - Tiến trình số)
        # Sheet sẽ TỰ ĐỘNG tính cột F (Phần Trăm) từ formula
        if progress is not None:
            col_e = COL_MAP['progress'] + 1  # Convert to 1-indexed
            updates.append({
                'range': f'{chr(64 + col_e)}{row_index}',  # E{row_index}
                'values': [[progress]]
            })
            print(f"  📝 Will update E{row_index}={progress} (Sheet tự tính F)")
        
        # Update status (Column G - Trạng thái)
        if status:
            col_g = COL_MAP['status'] + 1
            updates.append({
                'range': f'{chr(64 + col_g)}{row_index}',  # G{row_index}
                'values': [[status]]
            })
            print(f"  📝 Will update G{row_index}={status}")
        
        # Update deliverables (Column L - Thành phẩm)
        if deliverables:
            col_l = COL_MAP['deliverables'] + 1
            updates.append({
                'range': f'{chr(64 + col_l)}{row_index}',  # L{row_index}
                'values': [[deliverables]]
            })
            print(f"  📝 Will update L{row_index}={deliverables[:50]}...")
        
        if updates:
            ws.batch_update(updates)
            print(f"✅ Đã cập nhật Sheet tại dòng {row_index}")
            return True
        else:
            print("⚠️ Không có gì để cập nhật")
            return False
            
    except Exception as e:
        print(f"❌ Lỗi update sheet: {e}")
        return False

def append_deliverable_link(row_index, new_link):
    """
    Append a new git link to deliverables column WITHOUT overwriting
    - row_index: Row number (1-indexed)
    - new_link: Git URL to append
    """
    ws = get_sheet()
    if not ws:
        print("❌ Không thể kết nối Sheet")
        return False
    
    try:
        # Get current deliverables from column L
        col_l = COL_MAP['deliverables'] + 1  # 1-indexed
        cell_address = f'{chr(64 + col_l)}{row_index}'  # L{row_index}
        
        current = ws.acell(cell_address).value or ""
        
        # Append new link (separated by newline)
        if current:
            updated = f"{current}\n{new_link}"
        else:
            updated = new_link
        
        ws.update_acell(cell_address, updated)
        print(f"✅ Đã thêm link vào {cell_address}: {new_link}")
        return True
        
    except Exception as e:
        print(f"❌ Lỗi append link: {e}")
        return False

def update_task_status_on_start(row_index):
    """
    Update task status to 'Đang thực hiện' when user starts working
    Only if current status is 'Chưa bắt đầu'
    """
    ws = get_sheet()
    if not ws:
        return False
    
    try:
        # Check current status
        col_g = COL_MAP['status'] + 1
        cell_address = f'{chr(64 + col_g)}{row_index}'
        current_status = ws.acell(cell_address).value or ""
        
        if current_status.lower() in ['chưa bắt đầu', 'chưa bat đau', '']:
            ws.update_acell(cell_address, 'Đang thực hiện')
            print(f"✅ Updated {cell_address}: 'Chưa bắt đầu' → 'Đang thực hiện'")
            return True
        else:
            print(f"ℹ️ Status already '{current_status}', not changing")
            return False
            
    except Exception as e:
        print(f"❌ Lỗi update status: {e}")
        return False

# Test function
if __name__ == '__main__':
    print("🧪 Testing Google Sheets connection...\n")
    
    tasks = get_all_tasks()
    
    if tasks:
        print(f"\n✅ Successfully loaded {len(tasks)} tasks")
        print("\n📋 Sample tasks:")
        for i, task in enumerate(tasks[:3], 1):
            print(f"\n{i}. [{task['task_code']}] {task['task_name']}")
            print(f"   Owner: {task['owner']} | Priority: {task['priority']}")
            print(f"   Progress: {task['progress']}% | Status: {task['status']}")
            print(f"   Start: {task['start_date']} | Due: {task['end_date']}")
            if task['notes']:
                print(f"   Notes: {task['notes'][:50]}...")
    else:
        print("❌ No tasks found or connection failed")
    
    # Test update (commented out to prevent accidental changes)
    # print("\n🧪 Testing update function...")
    # update_task_in_sheet(6, progress=50, status='Đang thực hiện')
    # append_deliverable_link(6, 'https://github.com/test/commit/abc123')