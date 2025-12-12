# Updated database.py - Smart Task Assignment
import os
import mysql.connector
from dotenv import load_dotenv
from datetime import datetime, date

load_dotenv()

DB_CONFIG = {
    'host': os.getenv("MYSQL_HOST"),
    'user': os.getenv("MYSQL_USER"),
    'password': os.getenv("MYSQL_PASS"),
    'database': os.getenv("MYSQL_DATABASE"),
}

MIN_WORK_SECONDS_FALLBACK = int(os.getenv("MIN_WORK_SECONDS", 3600))

def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        print(f"❌ Error connecting to MySQL: {err}")
        exit(1)

def fetch_one(sql, params=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchone()
    except mysql.connector.Error as err:
        print(f"❌ Error executing fetch_one: {err}")
        return None
    finally:
        cursor.close()
        conn.close()

def fetch_all(sql, params=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchall()
    except mysql.connector.Error as err:
        print(f"❌ Error executing fetch_all: {err}")
        return []
    finally:
        cursor.close()
        conn.close()

def execute_query(sql, params=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        conn.commit()
        if sql.strip().upper().startswith("INSERT"):
            return cursor.lastrowid
        return True
    except mysql.connector.Error as err:
        print(f"❌ Error executing query: {err}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

# --- Settings ---
def get_setting(key):
    sql = "SELECT setting_value FROM settings WHERE setting_key=%s"
    result = fetch_one(sql, [key])
    if result:
        if key == "min_work_seconds":
            return int(result['setting_value'])
        return result['setting_value']
    if key == "min_work_seconds":
        return MIN_WORK_SECONDS_FALLBACK
    return None

# --- User Management (UPDATED: Add role) ---
def get_or_create_user(user_id: int, username: str, avatar_url: str, discord_name: str = None, role: str = None):
    sql_check = "SELECT user_id FROM users WHERE user_id = %s"
    user = fetch_one(sql_check, (user_id,))
    
    if user:
        sql_update = "UPDATE users SET username = %s, avatar_url = %s, discord_name = %s, role = %s WHERE user_id = %s"
        return execute_query(sql_update, (username, avatar_url, discord_name, role, user_id))
    else:
        sql_insert = "INSERT INTO users (user_id, username, avatar_url, discord_name, role) VALUES (%s, %s, %s, %s, %s)"
        return execute_query(sql_insert, (user_id, username, avatar_url, discord_name, role))

def get_user_role(user_id: int):
    """Get user's role from database"""
    sql = "SELECT role FROM users WHERE user_id = %s"
    result = fetch_one(sql, (user_id,))
    return result['role'] if result and result['role'] else None

# --- Task Sync & Management ---
def sync_tasks_from_sheet():
    """Sync all tasks from Google Sheet to DB"""
    import google_utils
    tasks = google_utils.get_all_tasks()
    if not tasks:
        print("⚠️ No tasks to sync.")
        return False

    success_count = 0
    for task in tasks:
        task_code = task['task_code']
        sql_check = "SELECT task_id FROM tasks WHERE task_code = %s"
        existing = fetch_one(sql_check, (task_code,))
        
        if existing:
            # Update existing task
            sql_update = """
                UPDATE tasks SET 
                task_name = %s, priority = %s, owner = %s, progress = %s, progress_percent = %s,
                status = %s, start_date = %s, end_date = %s, duration = %s, 
                phase = %s, deliverables = %s, notes = %s, sheet_row_index = %s
                WHERE task_code = %s
            """
            params = (
                task['task_name'], task['priority'], task['owner'], task['progress'], task['progress_percent'],
                task['status'], task['start_date'], task['end_date'], task['duration'],
                task['phase'], task['deliverables'], task['notes'], task['row_index'], task_code
            )
            if execute_query(sql_update, params):
                success_count += 1
        else:
            # Insert new task
            sql_insert = """
                INSERT INTO tasks (task_code, task_name, priority, owner, progress, progress_percent,
                status, start_date, end_date, duration, phase, deliverables, notes, sheet_row_index, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
            """
            params = (
                task_code, task['task_name'], task['priority'], task['owner'], task['progress'], task['progress_percent'],
                task['status'], task['start_date'], task['end_date'], task['duration'],
                task['phase'], task['deliverables'], task['notes'], task['row_index']
            )
            if execute_query(sql_insert, params):
                success_count += 1

    print(f"✅ Synced {success_count}/{len(tasks)} tasks.")
    return success_count > 0

def get_smart_task_for_user(user_role: str):
    """
    Smart task assignment based on:
    1. Owner match
    2. Not completed (status != 'Đã hoàn thành')
    3. Priority (Cao > Trung bình > Thấp)
    4. Start date (overdue or starting soon)
    5. Progress (less completed first)
    """
    if not user_role:
        return None
    
    today = date.today()
    
    sql = """
        SELECT *, 
            CASE priority
                WHEN 'Cao' THEN 3
                WHEN 'Trung bình' THEN 2
                WHEN 'Thấp' THEN 1
                ELSE 0
            END as priority_score,
            CASE
                WHEN start_date IS NULL THEN 0
                WHEN start_date <= %s THEN 100
                WHEN start_date <= DATE_ADD(%s, INTERVAL 3 DAY) THEN 50
                ELSE 10
            END as urgency_score
        FROM tasks
        WHERE owner = %s
        AND is_active = TRUE
        AND status NOT IN ('Đã hoàn thành', 'Đã duyệt')
        AND progress < 100
        ORDER BY 
            priority_score DESC,
            urgency_score DESC,
            progress ASC,
            start_date ASC
        LIMIT 1
    """
    
    return fetch_one(sql, (today, today, user_role))

def get_task_by_code(task_code: str):
    sql = "SELECT * FROM tasks WHERE task_code = %s AND is_active = TRUE"
    return fetch_one(sql, (task_code,))

def get_tasks_by_owner(owner: str):
    sql = """
        SELECT * FROM tasks 
        WHERE owner = %s 
        AND is_active = TRUE 
        AND status NOT IN ('Đã hoàn thành', 'Đã duyệt')
        ORDER BY 
            CASE priority
                WHEN 'Cao' THEN 3
                WHEN 'Trung bình' THEN 2
                WHEN 'Thấp' THEN 1
                ELSE 0
            END DESC,
            start_date ASC
    """
    return fetch_all(sql, (owner,))

def update_task_progress(task_id: int, progress: int, status: str = None):
    """Update task progress and optionally status, sync to sheet"""
    task = fetch_one("SELECT task_code, sheet_row_index FROM tasks WHERE task_id = %s", (task_id,))
    if not task:
        return False
    
    # Update DB
    sql = "UPDATE tasks SET progress = %s, progress_percent = %s"
    params = [progress, f"{progress}%"]
    
    if status:
        sql += ", status = %s"
        params.append(status)
    
    sql += ", updated_at = NOW() WHERE task_id = %s"
    params.append(task_id)
    
    if execute_query(sql, params):
        # Sync to sheet
        if task['sheet_row_index']:
            import google_utils
            google_utils.update_task_in_sheet(
                task['sheet_row_index'],
                progress=progress,
                status=status
            )
        return True
    return False

def update_task_deliverable(task_id: int, git_link: str):
    """Add git commit/branch link to task deliverables"""
    task = fetch_one("SELECT sheet_row_index, deliverables FROM tasks WHERE task_id = %s", (task_id,))
    if not task:
        return False
    
    # Update DB
    current = task['deliverables'] or ""
    updated = f"{current}\n{git_link}" if current else git_link
    
    sql = "UPDATE tasks SET deliverables = %s WHERE task_id = %s"
    if execute_query(sql, (updated, task_id)):
        # Sync to sheet
        if task['sheet_row_index']:
            import google_utils
            google_utils.append_deliverable_link(task['sheet_row_index'], git_link)
        return True
    return False

# --- Work Sessions ---
def start_session(user_id, task_id, guild_id, voice_channel_id):
    """Start work session and record initial progress"""
    progress_at_start = 0
    if task_id:
        task = fetch_one("SELECT progress FROM tasks WHERE task_id = %s", (task_id,))
        if task:
            progress_at_start = task['progress']
    
    sql = """
    INSERT INTO work_sessions (user_id, task_id, guild_id, voice_channel_id, join_time, progress_at_start)
    VALUES (%s, %s, %s, %s, NOW(), %s)
    """
    session_id = execute_query(sql, (user_id, task_id, guild_id, voice_channel_id, progress_at_start))
    
    # Update task status to 'Đang thực hiện' if not started
    if task_id:
        sql_status = """
        UPDATE tasks SET status = 'Đang thực hiện', last_assigned_at = NOW()
        WHERE task_id = %s AND status = 'Chưa bắt đầu'
        """
        execute_query(sql_status, (task_id,))
        
        # Sync to sheet
        task = fetch_one("SELECT sheet_row_index FROM tasks WHERE task_id = %s", (task_id,))
        if task and task['sheet_row_index']:
            import google_utils
            google_utils.update_task_in_sheet(task['sheet_row_index'], status='Đang thực hiện')
    
    return session_id

def get_active_session(user_id: int):
    sql = """
        SELECT ws.*, t.task_name, t.task_code, t.progress, t.sheet_row_index
        FROM work_sessions ws
        LEFT JOIN tasks t ON ws.task_id = t.task_id
        WHERE ws.user_id = %s AND ws.leave_time IS NULL
    """
    return fetch_one(sql, (user_id,))

def get_active_or_recent_session(user_id: int):
    sql = """
        SELECT ws.*, t.task_name, t.task_code
        FROM work_sessions ws
        LEFT JOIN tasks t ON ws.task_id = t.task_id
        WHERE ws.user_id = %s
        AND (ws.leave_time IS NULL OR ws.leave_time > NOW() - INTERVAL 15 MINUTE)
        ORDER BY ws.session_id DESC LIMIT 1
    """
    return fetch_one(sql, (user_id,))

def end_session(session_id: int):
    """End session, calculate duration, record final progress"""
    sql_update = """
        UPDATE work_sessions
        SET leave_time = NOW(),
            work_duration = TIMESTAMPDIFF(SECOND, join_time, NOW())
        WHERE session_id = %s
    """
    if not execute_query(sql_update, (session_id,)):
        return None

    updated_session = fetch_one("SELECT * FROM work_sessions WHERE session_id = %s", (session_id,))
    if not updated_session:
        return None

    duration = updated_session['work_duration']
    min_duration = 5
    
    if duration < min_duration:
        execute_query("DELETE FROM task_submissions WHERE session_id = %s", (session_id,))
        execute_query("DELETE FROM work_sessions WHERE session_id = %s", (session_id,))
        return None

    return updated_session

def update_session_verification(session_id: int, is_verified: bool):
    sql = "UPDATE work_sessions SET is_verified = %s WHERE session_id = %s"
    return execute_query(sql, (is_verified, session_id))

def update_session_counted_status(session_id: int, is_counted: bool):
    sql = "UPDATE work_sessions SET is_counted = %s WHERE session_id = %s"
    return execute_query(sql, (is_counted, session_id))

def get_accumulated_duration(user_id: int, task_id: int):
    sql = """
    SELECT SUM(work_duration) as total_seconds
    FROM work_sessions
    WHERE user_id = %s AND task_id = %s
    AND join_time > NOW() - INTERVAL 24 HOUR
    AND is_counted = 0
    """
    res = fetch_one(sql, (user_id, task_id))
    return int(res['total_seconds']) if res and res['total_seconds'] else 0

# --- Submissions ---
def create_submission(session_id: int, user_id: int, task_id: int, verify_code: str, link: str = None, progress: int = 100):
    """Create submission with progress and deliverable link"""
    # Detect link type
    deliverable_type = 'other'
    if link:
        if 'commit' in link.lower():
            deliverable_type = 'commit'
        elif 'branch' in link.lower() or '/tree/' in link:
            deliverable_type = 'branch'
        elif 'pull' in link.lower() or '/pull/' in link:
            deliverable_type = 'pr'
    
    sql = """
        INSERT INTO task_submissions
        (session_id, user_id, task_id, submitted_at, verify_code, submission_link, deliverable_type, progress_reported)
        VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s)
    """
    return execute_query(sql, (session_id, user_id, task_id, verify_code, link, deliverable_type, progress))

def check_submission_exists(session_id: int):
    sql = "SELECT 1 FROM task_submissions WHERE session_id = %s LIMIT 1"
    return fetch_one(sql, (session_id,)) is not None

def get_submission_code(session_id: int):
    sql = "SELECT verify_code FROM task_submissions WHERE session_id = %s ORDER BY submission_id DESC LIMIT 1"
    res = fetch_one(sql, (session_id,))
    return res['verify_code'] if res else "N/A"

def get_submission_by_code(verify_code: str):
    sql = "SELECT * FROM task_submissions WHERE verify_code = %s AND verified = FALSE"
    return fetch_one(sql, (verify_code,))

def verify_submission(submission_id: int, boss_id: int, approved: bool = True):
    """Verify submission and update task progress"""
    status = "verified" if approved else "rejected"
    sql = """
        UPDATE task_submissions
        SET verified = TRUE, verified_by = %s, verified_at = NOW(), status = %s
        WHERE submission_id = %s AND verified = FALSE
    """
    
    if execute_query(sql, (boss_id, status, submission_id)):
        # Get submission details
        submission = fetch_one("SELECT task_id, progress_reported, submission_link FROM task_submissions WHERE submission_id = %s", (submission_id,))
        
        if submission and approved:
            # Update task progress
            update_task_progress(submission['task_id'], submission['progress_reported'], 'Đã hoàn thành' if submission['progress_reported'] >= 100 else 'Đang thực hiện')
            
            # Add deliverable link if provided
            if submission['submission_link']:
                update_task_deliverable(submission['task_id'], submission['submission_link'])
        
        return True
    return False

# --- Stats ---
def get_user_stats(user_id: int):
    sql_duration = """
        SELECT SUM(work_duration) as total_seconds
        FROM work_sessions
        WHERE user_id = %s AND is_counted = TRUE AND join_time > NOW() - INTERVAL 30 DAY
    """
    duration_res = fetch_one(sql_duration, (user_id,))
    total_seconds = int(duration_res['total_seconds']) if duration_res and duration_res['total_seconds'] else 0

    sql_completed = """
        SELECT COUNT(*) as completed_count
        FROM task_submissions ts
        JOIN work_sessions ws ON ts.session_id = ws.session_id
        WHERE ws.user_id = %s AND ts.verified = TRUE AND ts.submitted_at > NOW() - INTERVAL 30 DAY
    """
    completed_res = fetch_one(sql_completed, (user_id,))
    completed_count = int(completed_res['completed_count']) if completed_res and completed_res['completed_count'] else 0

    return {
        'total_hours': round(total_seconds / 3600, 2),
        'completed_tasks': completed_count
    }

def get_leaderboard(limit: int = 10):
    sql = """
        SELECT u.user_id, u.username, SUM(ws.work_duration) as total_seconds
        FROM users u
        JOIN work_sessions ws ON u.user_id = ws.user_id
        WHERE ws.is_counted = TRUE AND ws.join_time > NOW() - INTERVAL 30 DAY
        GROUP BY u.user_id, u.username
        ORDER BY total_seconds DESC
        LIMIT %s
    """
    return fetch_all(sql, (limit,))