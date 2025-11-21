import os
import mysql.connector
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Database Connection Configuration ---
DB_CONFIG = {
    'host' : os.getenv("MYSQL_HOST"),
    'user' : os.getenv("MYSQL_USER"),
    'password' : os.getenv("MYSQL_PASS"),
    'database' : os.getenv("MYSQL_DATABASE"),
}

# Get MIN_WORK_SECONDS from .env (as a fallback)
MIN_WORK_SECONDS_FALLBACK = int(os.getenv("MIN_WORK_SECONDS", 3600))

# --- Database Connection Manager ---

def get_db_connection():
    """"Establishes and returns a new MySQL connection object"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        print("MySQL connected!")
        return conn
    except mysql.connector.Error as err:
        print(f"Error connecting to MySQL: {err}")
        # Terminate if DB connection fails
        exit(1)

# --- Generic Query Executors ---
def fetch_one(sql, params=None):
    """Executes a SELECT query and returns the first row as a dictionary"""
    conn = get_db_connection()
    # dictionary=True returns results as a dictionary (column_name: value)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        result = cursor.fetchone()
        return result
    except mysql.connector.Error as err:
        print (f"Error executing fetch_one query: {err}")
        return None
    finally:
        cursor.close()
        conn.close()

def execute_query(sql, params=None):
    """Executes an INSERT/UPDATE/DELETE query and returns the last row ID or True/False"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        conn.commit()
        if sql.strip().upper().startswith("INSERT"):
            return cursor.lastrowid
        return True
    except mysql.connector.Error as err:
        print (f"Error executing query: {err}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

# --- Configuration Functions (Setting Table) ---
def get_setting(key):
    """Retrieves a value of a setting from the settings tables"""
    sql = "SELECT setting_value FROM settings WHERE setting_key=%s"
    results = fetch_one(sql, [key])
    if results:
        # Convert to appropriate type if needed (e.g., int for min_work_seconds)
        if key == "min_work_seconds":
            return int(results['setting_value'])
        return results['setting_value']

    # Fallback to .env value if not found in DB
    if key == "min_work_seconds":
        return MIN_WORK_SECONDS_FALLBACK
    return None

# --- User $ Task Management Functions ---
def get_or_create_user(user_id: int, username: str, avatar_url: str):
    """Checks for, creates, or updates user information in the 'users' table."""
    sql_check = "SELECT user_id FROM users WHERE user_id = %s"
    user = fetch_one(sql_check, (user_id,))

    if user:
        # User exists, update info (username, avatar)
        sql_update = "UPDATE users SET username = %s, avatar_url = %s WHERE user_id = %s"
        return execute_query(sql_update, (username, avatar_url, user_id))
    else:
        # User does not exist, insert new user
        sql_insert = "INSERT INTO users (user_id, username, avatar_url) VALUES (%s, %s, %s)"
        return execute_query(sql_insert, (user_id, username, avatar_url))


def get_random_active_task():
    """Retrieves one random active task."""
    # ORDER BY RAND() is simple but inefficient on large tables. Optimize if tasks table grows large.
    sql = "SELECT task_id, task_name, task_description FROM tasks WHERE is_active = TRUE ORDER BY RAND() LIMIT 1"
    return fetch_one(sql)


# --- Work Session Management Functions ---

def start_session(user_id, task_id, guild_id, voice_channel_id, sheet_row_id=None):
    """
    Tạo session mới (Cập nhật thêm tham số sheet_row_id)
    """
    sql = """
    INSERT INTO work_sessions (user_id, task_id, guild_id, voice_channel_id, join_time, sheet_row_id)
    VALUES (%s, %s, %s, %s, NOW(), %s)
    """
    # execute_query nên trả về ID của dòng vừa insert (lastrowid)
    return execute_query(sql, (user_id, task_id, guild_id, voice_channel_id, sheet_row_id))


def get_active_session(user_id: int):
    """Finds the currently active work session (where leave_time IS NULL) for a user."""
    sql = """
          SELECT ws.*, t.task_name
          FROM work_sessions ws
                   LEFT JOIN tasks t ON ws.task_id = t.task_id
          WHERE ws.user_id = %s \
            AND ws.leave_time IS NULL \
          """
    return fetch_one(sql, (user_id,))


# TƯƠNG ĐƯƠNG VỚI HÀM get_active_or_recent_session(user_id)
def get_active_or_recent_session(user_id: int):
    sql = """
          SELECT ws.*, t.task_name \
          FROM work_sessions ws \
                   LEFT JOIN tasks t ON ws.task_id = t.task_id
          WHERE ws.user_id = %s
            AND (
              ws.leave_time IS NULL
                  OR ws.leave_time > NOW() - INTERVAL 15 MINUTE
              )
          ORDER BY ws.session_id DESC LIMIT 1 \
          """
    return fetch_one(sql, (user_id,))


def check_submission_exists(session_id: int):
    """
    Kiểm tra xem session này đã từng có submission nào chưa (Bất kể đã duyệt hay chưa).
    Tránh lỗi Duplicate Entry.
    """
    # Bỏ điều kiện 'AND verified = 0' đi
    sql = "SELECT 1 FROM task_submissions WHERE session_id = %s LIMIT 1"
    return fetch_one(sql, (session_id,)) is not None


def get_submission_code(session_id: int):
    # Lấy code cuối cùng của session
    sql = "SELECT verify_code FROM task_submissions WHERE session_id = %s ORDER BY submission_id DESC LIMIT 1"
    res = fetch_one(sql, (session_id,))
    return res['verify_code'] if res else "N/A"


def get_task_by_id(task_id: int):
    # Lấy thông tin task
    return fetch_one("SELECT task_name FROM tasks WHERE task_id = %s", (task_id,))


def get_or_create_task(task_name, description):
    """
    Tìm task trong DB, nếu chưa có thì tạo mới. Trả về task_id.
    """
    # 1. Tìm kiếm
    sql_check = "SELECT task_id FROM tasks WHERE task_name = %s"
    res = fetch_one(sql_check, (task_name,))
    if res:
        return res['task_id']

    # 2. Nếu chưa có -> Tạo mới
    sql_insert = "INSERT INTO tasks (task_name, task_description, is_active) VALUES (%s, %s, 1)"
    task_id = execute_query(sql_insert, (task_name, description))
    return task_id

def end_session(session_id: int):
    """
    Updates a work session with the leave_time and calculates work_duration.
    If the duration is too short (< 60s), it deletes the session and its submissions.
    Returns the updated session data or None if deleted/failure.
    """
    # 1. Update leave_time and calculate work_duration
    sql_update = """
                 UPDATE work_sessions
                 SET leave_time    = NOW(),
                     work_duration = TIMESTAMPDIFF(SECOND, join_time, NOW())
                 WHERE session_id = %s
                 """
    if not execute_query(sql_update, (session_id,)):
        return None

    # 2. Fetch the complete updated session data to get the calculated duration
    updated_session = fetch_one("SELECT * FROM work_sessions WHERE session_id = %s", (session_id,))

    if not updated_session:
        return None

    # 3. [NEW LOGIC] KIỂM TRA DURATION VÀ XÓA SESSION RÁC (Garbage Collection)

    # Đặt ngưỡng tối thiểu để tránh spam/chập chờn. Ví dụ: 60 giây.
    # Nên dùng một setting để dễ dàng thay đổi mà không cần sửa code.
    min_duration_to_keep = 5  # Hoặc database.get_setting("min_session_duration")

    duration = updated_session['work_duration']

    if duration < min_duration_to_keep:
        print(f"🗑️ Deleting short session {session_id}. Duration: {duration}s")

        # Xóa các submission liên quan (Nếu có)
        execute_query("DELETE FROM task_submissions WHERE session_id = %s", (session_id,))

        # Xóa session chính
        execute_query("DELETE FROM work_sessions WHERE session_id = %s", (session_id,))

        # Trả về None để Bot Event biết và KHÔNG gửi thông báo kết thúc session
        return None

        # 4. Trả về session hợp lệ nếu nó đủ dài
    return updated_session


def update_session_verification(session_id: int, is_verified: bool):
    """Updates the is_verified status of a work session."""
    sql = "UPDATE work_sessions SET is_verified = %s WHERE session_id = %s"
    return execute_query(sql, (is_verified, session_id))


def update_session_counted_status(session_id: int, is_counted: bool):
    """Updates the is_counted status of a work session."""
    sql = "UPDATE work_sessions SET is_counted = %s WHERE session_id = %s"
    return execute_query(sql, (is_counted, session_id))


# --- Task Submission Management Functions ---

def create_submission(session_id: int, user_id: int, task_id: int, verify_code: str):
    """Creates a new task submission for an active session. Returns submission_id."""
    # Note: verify_code is case-sensitive due to COLLATION utf8mb4_bin in schema
    sql = """
          INSERT INTO task_submissions
              (session_id, user_id, task_id, submitted_at, verify_code)
          VALUES (%s, %s, %s, NOW(), %s) \
          """
    return execute_query(sql, (session_id, user_id, task_id, verify_code))


def get_submission_by_code(verify_code: str):
    """Finds an unverified submission by its verification code."""
    sql = """
          SELECT * \
          FROM task_submissions
          WHERE verify_code = %s \
            AND verified = FALSE \
          """
    return fetch_one(sql, (verify_code,))


def verify_submission(submission_id: int, boss_id: int):
    """Marks a submission as verified and records the verifier ID and time."""
    sql = """
          UPDATE task_submissions
          SET verified    = TRUE, \
              verified_by = %s, \
              verified_at = NOW()
          WHERE submission_id = %s \
            AND verified = FALSE \
          """
    return execute_query(sql, (boss_id, submission_id))

# --- THÊM VÀO CUỐI FILE database.py ---

def get_recent_task_id(user_id: int, minutes_threshold=15):
    """
    Lấy task_id của phiên làm việc gần nhất (trong vòng X phút).
    Giúp user tiếp tục task cũ nếu lỡ bị disconnect hoặc deafen.
    """
    sql = """
    SELECT task_id FROM work_sessions 
    WHERE user_id = %s 
    AND leave_time > NOW() - INTERVAL %s MINUTE
    ORDER BY session_id DESC LIMIT 1
    """
    res = fetch_one(sql, (user_id, minutes_threshold))
    return res['task_id'] if res else None

def get_accumulated_duration(user_id: int, task_id: int):
    """
    Tính TỔNG thời gian user đã làm cho một Task cụ thể trong 24h qua
    (Bao gồm cả các session bị ngắt quãng do deafen/mute).
    Chỉ tính các session chưa được trả công (is_counted = 0).
    """
    sql = """
    SELECT SUM(work_duration) as total_seconds
    FROM work_sessions
    WHERE user_id = %s 
    AND task_id = %s
    AND join_time > NOW() - INTERVAL 24 HOUR
    AND is_counted = 0
    """
    res = fetch_one(sql, (user_id, task_id))
    # Nếu res['total_seconds'] là None (chưa làm gì) thì trả về 0
    return int(res['total_seconds']) if res and res['total_seconds'] else 0


# --- Example Usage (Optional - for testing the module) ---
if __name__ == '__main__':
    print(f"Min work seconds (from DB/Fallback): {get_setting('min_work_seconds')}")
    # Example: Check and create a user
    success = get_or_create_user(1234567890, "TestUser", "https://avatar.url")
    print(f"User created/updated: {success}")
    # Example: Get a random task
    task = get_random_active_task()
    print(f"Random Task: {task}")

# Remember to create bot.py next!