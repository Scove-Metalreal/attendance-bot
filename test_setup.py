# test_setup.py - Test configuration and connections
import os
from dotenv import load_dotenv
import sys

print("="*60)
print("🔍 TESTING BOT CONFIGURATION")
print("="*60)

# Test 1: .env file
print("\n1. Checking .env file...")
load_dotenv()

required_vars = [
    'DISCORD_TOKEN',
    'TARGET_VOICE_CHANNEL_ID',
    'LOG_CHANNEL_ID',
    'MYSQL_HOST',
    'MYSQL_USER',
    'MYSQL_PASS',
    'MYSQL_DATABASE'
]

missing_vars = []
for var in required_vars:
    value = os.getenv(var)
    if not value:
        missing_vars.append(var)
        print(f"   ❌ {var}: MISSING")
    else:
        # Mask sensitive data
        if 'TOKEN' in var or 'PASS' in var:
            display = value[:10] + "..." if len(value) > 10 else "***"
        else:
            display = value
        print(f"   ✅ {var}: {display}")

if missing_vars:
    print(f"\n❌ Missing required variables: {', '.join(missing_vars)}")
    sys.exit(1)

# Test 2: MySQL Connection
print("\n2. Testing MySQL connection...")
try:
    import mysql.connector
    conn = mysql.connector.connect(
        host=os.getenv('MYSQL_HOST'),
        user=os.getenv('MYSQL_USER'),
        password=os.getenv('MYSQL_PASS'),
        database=os.getenv('MYSQL_DATABASE')
    )
    print("   ✅ MySQL connection successful")
    
    # Check tables
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    tables = [table[0] for table in cursor.fetchall()]
    
    required_tables = ['users', 'tasks', 'work_sessions', 'task_submissions', 'settings']
    for table in required_tables:
        if table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"   ✅ Table '{table}': {count} rows")
        else:
            print(f"   ❌ Table '{table}': NOT FOUND")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"   ❌ MySQL connection failed: {e}")
    sys.exit(1)

# Test 3: Google Sheets Connection
print("\n3. Testing Google Sheets connection...")
try:
    import gspread
    
    if not os.path.exists('credentials.json'):
        print("   ❌ credentials.json NOT FOUND")
        print("   → Download from Google Cloud Console")
    else:
        print("   ✅ credentials.json found")
        
        try:
            gc = gspread.service_account(filename='credentials.json')
            print("   ✅ Service account loaded")
            
            # Try to open sheet
            from google_utils import SHEET_URL, get_sheet
            ws = get_sheet()
            
            if ws:
                print(f"   ✅ Connected to Google Sheet: {ws.title}")
                
                # Check structure
                all_values = ws.get_all_values()
                if len(all_values) >= 6:
                    header = all_values[4]  # Row 5 (0-indexed)
                    print(f"   ✅ Sheet has {len(all_values)} rows")
                    print(f"   ✅ Header row detected: {len(header)} columns")
                    
                    # Expected columns
                    expected_cols = ['Mã công việc', 'Việc cần làm', 'Mức độ Ưu tiên', 
                                   'Chủ sở hữu', 'Tiến trình', '%', 'Trạng thái']
                    
                    for i, col in enumerate(expected_cols):
                        if i < len(header) and col.lower() in header[i].lower():
                            print(f"   ✅ Column {chr(65+i)}: {col}")
                        else:
                            print(f"   ⚠️  Column {chr(65+i)}: Expected '{col}', got '{header[i] if i < len(header) else 'MISSING'}'")
                else:
                    print(f"   ⚠️  Sheet has only {len(all_values)} rows (need at least 6)")
            else:
                print("   ❌ Failed to open Google Sheet")
                print("   → Check SHEET_URL in google_utils.py")
                print("   → Check if service account has access to the sheet")
                
        except Exception as e:
            print(f"   ❌ Google Sheets error: {e}")
            
except ImportError:
    print("   ❌ gspread not installed")
    print("   → Run: pip install gspread")

# Test 4: Discord.py
print("\n4. Testing discord.py...")
try:
    import discord
    print(f"   ✅ discord.py version: {discord.__version__}")
except ImportError:
    print("   ❌ discord.py not installed")
    print("   → Run: pip install discord.py")

# Test 5: Check reward images folder
print("\n5. Checking reward images...")
reward_folder = "reward_images"
if os.path.exists(reward_folder):
    images = [f for f in os.listdir(reward_folder) 
              if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))]
    if images:
        print(f"   ✅ Found {len(images)} reward images")
        for img in images[:3]:
            print(f"      - {img}")
        if len(images) > 3:
            print(f"      ... and {len(images)-3} more")
    else:
        print(f"   ⚠️  Folder exists but no images found")
else:
    print(f"   ⚠️  Folder '{reward_folder}' not found (optional)")
    print("   → Create folder and add images for rewards")

# Test 6: Check bot.py configuration
print("\n6. Checking bot.py configuration...")
try:
    # Import to check syntax
    import bot
    
    # Check USER_ROLE_MAPPING
    if hasattr(bot, 'USER_ROLE_MAPPING'):
        mapping = bot.USER_ROLE_MAPPING
        print(f"   ✅ USER_ROLE_MAPPING found: {len(mapping)} users")
        for user_id, role in list(mapping.items())[:3]:
            print(f"      - {user_id} → {role}")
        if len(mapping) > 3:
            print(f"      ... and {len(mapping)-3} more")
    else:
        print("   ❌ USER_ROLE_MAPPING not found in bot.py")
    
    # Check LEADERS
    if hasattr(bot, 'LEADERS'):
        leaders = bot.LEADERS
        print(f"   ✅ LEADERS found: {len(leaders)} leaders")
    else:
        print("   ❌ LEADERS not found in bot.py")
        
except Exception as e:
    print(f"   ❌ Error loading bot.py: {e}")

# Summary
print("\n" + "="*60)
print("📊 CONFIGURATION TEST SUMMARY")
print("="*60)

if not missing_vars:
    print("✅ All required environment variables are set")
else:
    print(f"❌ Missing variables: {', '.join(missing_vars)}")

print("\n🚀 Next steps:")
print("   1. Fix any ❌ errors above")
print("   2. Update USER_ROLE_MAPPING in bot.py with real Discord IDs")
print("   3. Update LEADERS list in bot.py")
print("   4. Run: python bot.py")
print("\n" + "="*60)