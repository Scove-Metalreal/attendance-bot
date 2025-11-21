# 🌟 **Discord Attendance Bot — Python + MySQL**  
A smart attendance & task-tracking bot that automatically records work sessions through **Discord Voice Channels**, assigns tasks, verifies completion through secure codes, and calculates attendance based on time + verification.

---

## 📌 **Features**

### 🎧 Voice Activity Tracking
- Auto-detect when users **join** and **leave** voice channels  
- Start & end “work sessions” automatically  
- Track total working time in seconds  
- Automatically determine whether a session is **valid** based on minimum required time

### 📝 Task Assignment System
- Automatically assigns a task each time a user joins a voice channel  
- Tasks are stored in a MySQL database  
- Easy to add/disable tasks without modifying code

### 🔐 Verification System
- User completes tasks → sends `/done`  
- Bot generates a unique **6-digit verify code**  
- Code is forwarded to the boss  
- Boss approves using `/verify ABC123`  
- Only verified tasks count toward attendance

### 🕓 Automated Attendance Calculation
When a user leaves VC:
- If working time >= minimum required time  
- AND task is verified  
→ The bot marks the session as **counted attendance**

---

## 🛠 **Tech Stack**
| Component | Technology |
|----------|------------|
| Bot Framework | discord.py |
| Database | MySQL |
| Driver | mysql-connector-python |
| ENV Loader | python-dotenv |
| Language | Python 3.x |
| Deployment | Local / VPS / Docker |

---

## 📂 **Project Structure**

```
attendance-bot/
├── bot.py                # Main bot logic
├── .env                  # Environment variables
├── requirements.txt      # Python dependencies
├── README.md             # Documentation
└── sql/
    ├── schema.sql        # Database tables
```

---

## 🔧 **Setup Instructions**

### 1️⃣ Clone project
```bash
git clone <your-repo-url>
cd attendance-bot
```

### 2️⃣ Create virtual environment
```bash
python -m venv venv
source venv/Scripts/activate   # Windows
```

### 3️⃣ Install dependencies
```bash
pip install -r requirements.txt
```

---

## 🔐 **Environment Variables (.env)**

Create file `.env`:

```
DISCORD_TOKEN=YOUR_DISCORD_BOT_TOKEN
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASS=yourpassword
MYSQL_DATABASE=discord_attendance_bot
MIN_WORK_SECONDS=3600
```

⚠️ Never commit this file!

---

## 🗄 **Database Schema**

### `tasks`
```sql
CREATE TABLE tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    task_name VARCHAR(255),
    is_active TINYINT DEFAULT 1
);
```

### `work_sessions`
```sql
CREATE TABLE work_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    task_id INT NULL,
    voice_channel BIGINT,
    join_time DATETIME NOT NULL,
    end_time DATETIME NULL,
    duration_seconds INT,
    is_counted TINYINT DEFAULT 0
);
```

### `task_submissions`
```sql
CREATE TABLE task_submissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    session_id INT NOT NULL,
    task_id INT NOT NULL,
    verify_code VARCHAR(10) NOT NULL,
    submitted_at DATETIME NOT NULL,
    is_verified TINYINT DEFAULT 0
);
```

---

## ▶️ **Run the Bot**
```bash
python bot.py
```

When running correctly:
```
Bot online & slash commands synced!
MySQL connected!
```

---

## 🎮 **Bot Commands**

### `/done`
Submit completed task → bot generates verify code → sends to boss.

### `/verify <CODE>`
Boss verifies the code → session counted as completed.

---

## 🔁 **Workflow Overview**

### 🔹 1. User joins voice channel  
Bot creates a session → assigns a task automatically.

### 🔹 2. User completes task  
User sends `/done` → bot generates verify code.

### 🔹 3. Boss verifies  
Boss uses `/verify ABC123` → marks session as verified.

### 🔹 4. User leaves voice channel  
Bot checks:  
- Working time ≥ MIN_WORK_SECONDS  
- Task verified  
→ If valid → attendance counted.

---

## 📊 **Future Improvements**
- Web dashboard (Flask + Tailwind)  
- Admin panel to manage tasks  
- Export attendance to CSV/Excel  
- Leaderboard & performance ranking  
- Multi-team support  
- Anti-AFK detection  
- Real-time monitoring panel

---

## ❤️ Contribution
Pull requests are welcome! Suggestions & improvements are appreciated.

---

## 📜 License
MIT License — free to use & modify.

