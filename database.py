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
    sql_check = "SELECT user_id FROM users WHERE user_id=%s"
    user = fetch_one(sql_check, (user_id,))

    if user:
        # User exits, update info (username, avatar)
        sql_update = "UPDATE users SET user_name=%s WHERE user_id=%s"
