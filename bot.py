import discord
from discord import app_commands
from discord.ext import commands
import os
import secrets
from dotenv import load_dotenv
from datetime import timedelta, datetime
import random
import google_utils

# Import our custom database module
import database

# --- Setup & Configuration ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Cấu hình đường dẫn folder ảnh
REWARD_FOLDER = "reward_images"

# Lấy ID kênh target Voice (Chấm công)
TARGET_VC_ID = int(os.getenv('TARGET_VOICE_CHANNEL_ID', 0))

# Lấy ID kênh Log (Thông báo & Reward) - NEW
LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID', 0))

# --- MAPPING USER ---
# ID Discord : Tên Role trong cột D của Google Sheet
USER_MAPPING = {
    123456789012345678: "2. Lead Programmer", # Thay ID thật của bạn
    987654321098765432: "3. Lead Artist",
    # Thêm các thành viên khác vào đây
}

# Configure Intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

# Initialize Bot
bot = commands.Bot(command_prefix="!", intents=intents)


# --- Helper: Gửi thông báo vào kênh Log ---
async def send_to_log_channel(guild, content=None, embed=None, file=None):
    """
    Gửi tin nhắn vào kênh LOG_CHANNEL_ID thay vì DM.
    Luôn tag user trong content để họ biết.
    """
    if LOG_CHANNEL_ID == 0:
        print("⚠️ Chưa cấu hình LOG_CHANNEL_ID trong .env")
        return

    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel:
        try:
            await channel.send(content=content, embed=embed, file=file)
        except Exception as e:
            print(f"❌ Lỗi gửi tin vào Log Channel: {e}")
    else:
        print(f"❌ Không tìm thấy kênh Log có ID: {LOG_CHANNEL_ID}")


# --- Helper: Lấy ảnh Random ---
def get_random_reward_file():
    if not os.path.exists(REWARD_FOLDER):
        return None
    files = os.listdir(REWARD_FOLDER)
    valid_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
    images = [f for f in files if f.lower().endswith(valid_extensions)]
    if not images:
        return None
    selected_image = random.choice(images)
    return os.path.join(REWARD_FOLDER, selected_image)


# --- Event: Bot Ready ---
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"✅ Bot is online as {bot.user}")
        print(f"✅ Synced {len(synced)} slash commands")
        print(f"🎯 Monitoring Voice Channel ID: {TARGET_VC_ID}")
        print(f"📝 Logging to Channel ID: {LOG_CHANNEL_ID}")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

    # Logic tự sửa lỗi khi restart (Giữ nguyên như cũ)
    print("🔄 Checking for stale sessions...")
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT session_id, user_id, guild_id FROM work_sessions WHERE leave_time IS NULL")
    stale_sessions = cursor.fetchall()
    count_fixed = 0
    for session in stale_sessions:
        guild = bot.get_guild(session['guild_id'])
        if guild:
            member = guild.get_member(session['user_id'])
            is_in_voice = member and member.voice and member.voice.channel
            if not is_in_voice:
                database.end_session(session['session_id'])
                count_fixed += 1
    cursor.close()
    conn.close()
    print(f"✅ Fixed {count_fixed} stale sessions.")


# --- Event: Voice State Update ---
@bot.event
async def on_voice_state_update(member, before, after):
    if TARGET_VC_ID == 0:
        return

    user_id = member.id
    username = member.name
    avatar_url = str(member.avatar.url) if member.avatar else None
    guild = member.guild

    # Logic Lọc Kênh
    in_target_before = (before.channel is not None and before.channel.id == TARGET_VC_ID)
    in_target_after = (after.channel is not None and after.channel.id == TARGET_VC_ID)

    is_joining = not in_target_before and in_target_after
    is_leaving = in_target_before and not in_target_after
    is_staying = in_target_before and in_target_after

    # =========================================================
    # 1. XỬ LÝ KẾT THÚC SESSION (Giữ nguyên logic cũ)
    # =========================================================
    should_end = is_leaving or (is_staying and (after.self_deaf or after.self_mute))

    if should_end:
        session = database.get_active_session(user_id)
        if session:
            session_id = session['session_id']
            task_id = session['task_id']

            # Tính toán duration tạm thời
            join_time = session.get('join_time')
            provisional_duration = 0
            if join_time and isinstance(join_time, datetime):
                provisional_duration = int((datetime.now() - join_time).total_seconds())

            updated_session = database.end_session(session_id)

            if updated_session:
                current_duration = updated_session['work_duration']
                is_verified = updated_session['is_verified']
                total_duration = database.get_accumulated_duration(user_id, task_id)
                min_work_seconds = database.get_setting("min_work_seconds")

                # Auto-Generate Code Logic
                generated_code = None
                code_msg = ""
                if total_duration >= min_work_seconds and not is_verified:
                    if database.check_submission_exists(session_id):
                        generated_code = database.get_submission_code(session_id)
                        code_msg = f"Code cũ: `{generated_code}`"
                    else:
                        new_code = secrets.token_hex(3).upper()
                        database.create_submission(session_id, user_id, task_id, new_code)
                        generated_code = new_code
                        code_msg = f"✅ **AUTO-GENERATED:** `{new_code}`"

                # Status Logic
                status_msg = "❌ Session Invalid"
                if total_duration >= min_work_seconds:
                    if is_verified:
                        status_msg = "✅ Attendance COUNTED"
                        database.update_session_counted_status(session_id, True)
                    else:
                        status_msg = "⚠️ Đủ thời gian - Chờ Verify"
                else:
                    status_msg = "⚠️ Chưa đủ thời gian"

                # Create Embed
                embed = discord.Embed()
                if is_leaving:
                    embed.title = "🛑 Work Session Ended"
                    embed.color = discord.Color.orange()
                else:
                    embed.title = "⏸️ Session Paused"
                    embed.description = "Dừng tính giờ (Deafen/Mute)."
                    embed.color = discord.Color.red()

                embed.set_author(name=username, icon_url=avatar_url)
                embed.add_field(name="Phiên này", value=str(timedelta(seconds=current_duration)), inline=True)
                embed.add_field(name="Tổng cộng dồn", value=f"**{str(timedelta(seconds=total_duration))}**",
                                inline=True)
                embed.add_field(name="Trạng thái", value=status_msg, inline=False)

                if generated_code:
                    embed.add_field(name="🔐 VERIFY CODE", value=code_msg, inline=False)
                    embed.set_footer(text=f"Gửi code này cho Boss: /verify {generated_code}")

                await send_to_log_channel(guild, content=f"<@{user_id}>", embed=embed)

        if is_leaving or (is_staying and (after.self_deaf or after.self_mute)):
            return

    # =========================================================
    # 2. XỬ LÝ BẮT ĐẦU SESSION (Đã cập nhật Logic Google Sheet)
    # =========================================================
    should_start = (is_joining and not (after.self_deaf or after.self_mute)) or \
                   (is_staying and (before.self_deaf or before.self_mute) and not (after.self_deaf or after.self_mute))

    if should_start:
        if database.get_active_session(user_id):
            return

        # Đảm bảo user tồn tại trong DB
        database.get_or_create_user(user_id, username, avatar_url)

        # --- LOGIC TÌM TASK (GOOGLE SHEET -> RECENT -> RANDOM) ---
        task_id = None
        task_name = "Unknown Task"
        task_desc = "..."
        sheet_row_id = None  # Biến lưu dòng sheet
        source_msg = ""  # Để hiển thị nguồn task

        # 1. Xác định Role từ Mapping
        user_role = USER_MAPPING.get(user_id)

        # 2. Ưu tiên 1: Tìm trên Google Sheet
        if user_role:
            print(f"🔍 Checking Google Sheet for {username} ({user_role})...")
            sheet_task = google_utils.get_assigned_task_from_sheet(user_role)

            if sheet_task:
                # Tìm thấy task trên Sheet!
                sheet_task_name = f"[{sheet_task['task_code']}] {sheet_task['task_name']}"
                sheet_desc = "Task synced from Google Sheet"
                sheet_row_id = sheet_task['row_index']

                # Đồng bộ vào DB Tasks để lấy ID
                task_id = database.get_or_create_task(sheet_task_name, sheet_desc)
                task_name = sheet_task_name
                task_desc = sheet_desc
                source_msg = "📊 Google Sheet"
            else:
                print(f"⚠️ No active task found on Sheet for {user_role}")

        # 3. Ưu tiên 2: Nếu không có trên Sheet, tìm Task cũ (Resume)
        if not task_id:
            task_id = database.get_recent_task_id(user_id, minutes_threshold=15)
            if task_id:
                task_data = database.fetch_one("SELECT * FROM tasks WHERE task_id = %s", (task_id,))
                if task_data:
                    task_name = task_data['task_name'] + " (Resumed)"
                    task_desc = task_data['task_description']
                    source_msg = "🔄 Resumed Previous"

        # 4. Ưu tiên 3: Random Task (Fallback cuối cùng)
        if not task_id:
            task_data = database.get_random_active_task()
            if task_data:
                task_id = task_data['task_id']
                task_name = task_data['task_name']
                task_desc = task_data['task_description']
                source_msg = "🎲 Random Assigned"
            else:
                task_name = "No active tasks available"
                task_desc = "Please contact admin."
                source_msg = "⚠️ System"

        # 5. Tạo Session (Lưu kèm sheet_row_id nếu có)
        # Lưu ý: Cần cập nhật hàm start_session trong database.py để nhận sheet_row_id
        database.start_session(user_id, task_id, guild.id, after.channel.id, sheet_row_id)

        # Lấy tổng thời gian để hiển thị
        total_duration = 0
        if task_id:
            total_duration = database.get_accumulated_duration(user_id, task_id)

        # Gửi thông báo Start
        embed = discord.Embed(title="🚀 Work Session Started", color=discord.Color.green())
        if is_staying:
            embed.description = "Đã bật lại tai nghe. Tiếp tục tính giờ!"

        embed.set_author(name=username, icon_url=avatar_url)
        embed.add_field(name="Channel", value=after.channel.name, inline=False)
        embed.add_field(name="Task", value=f"**{task_name}**", inline=False)
        embed.add_field(name="Source", value=f"`{source_msg}`", inline=True)
        if sheet_row_id:
            embed.add_field(name="Sheet Row", value=f"Row #{sheet_row_id}", inline=True)

        embed.add_field(name="Đã làm hôm nay", value=str(timedelta(seconds=total_duration)), inline=False)

        await send_to_log_channel(guild, content=f"<@{user_id}> Chúc bạn làm việc hiệu quả! 💪", embed=embed)


# --- Slash Command: /done ---
@bot.tree.command(name="done", description="Báo cáo hoàn thành task.")
async def done(interaction: discord.Interaction):
    user_id = interaction.user.id

    # (Logic kiểm tra session - Giữ nguyên)
    session = database.get_active_or_recent_session(user_id)
    if not session:
        await interaction.response.send_message("❌ Bạn không có session làm việc nào gần đây.", ephemeral=True)
        return

    if database.check_submission_exists(session['session_id']):
        code = database.get_submission_code(session['session_id'])
        await interaction.response.send_message(f"⚠️ Đã có code rồi: `{code}`", ephemeral=True)
        return

    if not session['task_id']:
        await interaction.response.send_message("⚠️ Không có task.", ephemeral=True)
        return

    verify_code = secrets.token_hex(3).upper()
    database.create_submission(session['session_id'], user_id, session['task_id'], verify_code)

    task_data = database.get_task_by_id(session['task_id'])
    task_name = task_data['task_name'] if task_data else "Unknown Task"

    # 1. Phản hồi Ephemeral (Riêng tư) cho User biết là lệnh đã chạy
    embed_private = discord.Embed(title="✅ Đã nộp Task!", color=discord.Color.blue())
    embed_private.add_field(name="Code", value=f"`{verify_code}`")
    embed_private.set_footer(text="Bot đã gửi ảnh reward vào kênh chat chung!")
    await interaction.response.send_message(embed=embed_private, ephemeral=True)

    # 2. Gửi Reward + Thông báo công khai vào LOG CHANNEL
    image_path = get_random_reward_file()

    embed_public = discord.Embed(title="🎉 Task Completed!", color=discord.Color.gold())
    embed_public.set_author(name=interaction.user.name,
                            icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
    embed_public.description = f"<@{user_id}> vừa hoàn thành task **{task_name}**!"
    embed_public.add_field(name="🔐 Verify Code", value=f"`{verify_code}` (Boss verify giúp em nhé)")

    file = None
    if image_path:
        file = discord.File(image_path)
        embed_public.set_image(url=f"attachment://{os.path.basename(image_path)}")

    await send_to_log_channel(interaction.guild, content=f"<@{user_id}> Giỏi quá! 🎁", embed=embed_public, file=file)


# --- Slash Command: /verify ---
@bot.tree.command(name="verify", description="[BOSS] Duyệt task.")
async def verify(interaction: discord.Interaction, code: str):
    code = code.strip().upper()
    boss_id = interaction.user.id

    submission = database.get_submission_by_code(code)
    if not submission:
        await interaction.response.send_message("❌ Code không đúng hoặc đã duyệt.", ephemeral=True)
        return

    session_id = submission['session_id']
    worker_id = submission['user_id']

    database.verify_submission(submission['submission_id'], boss_id)
    database.update_session_verification(session_id, True)

    # Hồi tố (Re-check attendance)
    session_info = database.fetch_one("SELECT * FROM work_sessions WHERE session_id = %s", (session_id,))
    msg_extra = ""
    if session_info and session_info['leave_time']:
        duration = session_info['work_duration']
        min_work = database.get_setting("min_work_seconds")

        # Kiểm tra tổng thời gian cộng dồn task
        total_duration = database.get_accumulated_duration(worker_id, session_info['task_id'])

        if total_duration >= min_work:
            database.update_session_counted_status(session_id, True)
            msg_extra = f"⏱️ Tổng thời gian: {timedelta(seconds=total_duration)}. **Attendance COUNTED!**"
        else:
            msg_extra = f"⚠️ Tổng thời gian: {timedelta(seconds=total_duration)} (Chưa đủ {min_work}s)."

    # Thông báo công khai vào Log Channel
    embed = discord.Embed(title="✅ Task Verified", color=discord.Color.green())
    embed.description = f"Sếp <@{boss_id}> đã duyệt bài cho <@{worker_id}>.\nCode: `{code}`"
    if msg_extra:
        embed.add_field(name="Kết quả chấm công", value=msg_extra, inline=False)

    await interaction.response.send_message("Đã duyệt!", ephemeral=True)  # Phản hồi cho Boss biết
    await send_to_log_channel(interaction.guild, content=f"<@{worker_id}>", embed=embed)


# --- Slash Command: /status ---
@bot.tree.command(name="status", description="Xem trạng thái làm việc hiện tại.")
async def status(interaction: discord.Interaction):
    session = database.get_active_session(interaction.user.id)
    if not session:
        await interaction.response.send_message("💤 Bạn đang không trong phiên làm việc nào.", ephemeral=True)
    else:
        task_name = session['task_name']
        total_duration = database.get_accumulated_duration(interaction.user.id, session['task_id'])
        embed = discord.Embed(title="👨‍💻 Đang làm việc", color=discord.Color.green())
        embed.add_field(name="Task", value=task_name)
        embed.add_field(name="Tổng thời gian hôm nay", value=str(timedelta(seconds=total_duration)))
        await interaction.response.send_message(embed=embed, ephemeral=True)


# --- Slash Command: /help ---
@bot.tree.command(name="help", description="Hướng dẫn sử dụng Bot chấm công.")
async def help(interaction: discord.Interaction):
    """
    Hiển thị hướng dẫn sử dụng.
    """
    embed = discord.Embed(title="📖 Hướng dẫn sử dụng Attendance Bot", color=discord.Color.purple())

    # Kênh Voice
    target_channel = f"<#{TARGET_VC_ID}>" if TARGET_VC_ID else "kênh Voice quy định"
    min_time = timedelta(seconds=database.get_setting("min_work_seconds"))

    embed.description = f"Bot tự động chấm công khi bạn tham gia {target_channel}."

    embed.add_field(
        name="1️⃣ Bắt đầu làm việc",
        value=f"- Tham gia {target_channel}.\n- Bot sẽ tự động DM/Tag bạn và giao Task.\n- **Lưu ý:** Không tắt tai nghe (Deafen) quá lâu.",
        inline=False
    )

    embed.add_field(
        name="2️⃣ Báo cáo (Quan trọng)",
        value="- Khi làm xong (hoặc đủ thời gian), gõ lệnh `/done`.\n- Bot sẽ gửi ảnh Reward và **Code xác nhận**.",
        inline=False
    )

    embed.add_field(
        name="3️⃣ Xác nhận & Tính công",
        value=f"- Gửi Code xác nhận cho Sếp.\n- Sếp gõ `/verify <CODE>`.\n- Nếu tổng thời gian > **{min_time}** VÀ đã Verify -> **Được tính công**.",
        inline=False
    )

    embed.add_field(
        name="🛠️ Các lệnh khác",
        value="`/status`: Xem mình đang làm gì, bao lâu.\n`/help`: Xem bảng này.",
        inline=False
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found.")
    else:
        bot.run(TOKEN)