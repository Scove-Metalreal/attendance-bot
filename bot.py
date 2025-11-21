import discord
from discord import app_commands
from discord.ext import commands
import os
import secrets
from dotenv import load_dotenv
from datetime import timedelta, datetime
import random

# Import our custom database module
import database

# --- Setup & Configuration ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Cấu hình đường dẫn folder ảnh
REWARD_FOLDER = "reward_images"

# Lấy ID kênh target, chuyển sang int. Nếu lỗi (quên set) thì để 0 (sẽ không chạy)
TARGET_VC_ID = int(os.getenv('TARGET_VOICE_CHANNEL_ID', 0))

# Configure Intents (Permissions)
intents = discord.Intents.default()
intents.message_content = True  # Required for reading messages (if needed)
intents.voice_states = True  # REQUIRED: To track Voice Channel activity
intents.members = True  # REQUIRED: To fetch user details

# Initialize Bot
bot = commands.Bot(command_prefix="!", intents=intents)


# --- Event: Bot Ready ---
@bot.event
async def on_ready():
    """Triggered when the bot successfully connects and performs self-correction."""
    try:
        # Sync Slash Commands with Discord
        synced = await bot.tree.sync()
        print(f"✅ Bot is online as {bot.user}")
        print(f"✅ Synced {len(synced)} slash commands")
        print("------")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

    # --- LOGIC TỰ SỬA LỖI KHI RESTART (Chèn vào đây) ---
    print("🔄 Checking for stale sessions...")

    # Lấy tất cả session đang active trong DB
    # (Đảm bảo database.py của bạn có hàm get_db_connection/end_session)
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Query các session đang active (leave_time IS NULL)
    cursor.execute("SELECT session_id, user_id, guild_id FROM work_sessions WHERE leave_time IS NULL")
    stale_sessions = cursor.fetchall()

    count_fixed = 0
    # Lấy thời gian hiện tại để dùng làm leave_time cho các session bị sửa lỗi
    # Giả sử database.end_session tự động set leave_time = NOW() hoặc bạn cần truyền vào.

    for session in stale_sessions:
        guild = bot.get_guild(session['guild_id'])

        # 1. Kiểm tra Bot có còn trong Guild đó không
        if guild:
            member = guild.get_member(session['user_id'])

            is_in_voice = False
            # 2. Kiểm tra Member có trong Guild và đang trong Kênh thoại không
            if member and member.voice and member.voice.channel:
                is_in_voice = True

            # Nếu DB nói "Đang làm" VÀ thực tế "Không có trong Voice"
            # (Hoặc member không còn trong server, hoặc không có voice state)
            if not is_in_voice:
                # End session ngay lập tức (Database tự tính work_duration)
                print(
                    f"  -> Closing stale session {session['session_id']} for user {session['user_id']} (Guild ID: {session['guild_id']})")

                # Hàm end_session sẽ tính duration dựa trên start_time và thời gian hiện tại
                database.end_session(session['session_id'])

                count_fixed += 1
            # else:
            #   Member VẪN đang trong voice channel (đúng như DB ghi nhận). Không làm gì.

    cursor.close()
    conn.close()
    print(f"✅ Fixed {count_fixed} stale sessions.")
    print("----------------------------------------------------------------------")


def get_random_reward_file():
    """
    Quét folder REWARD_FOLDER và trả về đường dẫn của 1 ảnh ngẫu nhiên.
    Nếu folder rỗng hoặc không tồn tại, trả về None.
    """
    if not os.path.exists(REWARD_FOLDER):
        print(f"⚠️ Folder {REWARD_FOLDER} không tồn tại. Hãy tạo nó và thêm ảnh vào.")
        return None

    # Lấy danh sách tất cả file trong folder
    files = os.listdir(REWARD_FOLDER)

    # Lọc chỉ lấy file ảnh (jpg, png, gif, webp...)
    valid_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
    images = [f for f in files if f.lower().endswith(valid_extensions)]

    if not images:
        return None

    # Chọn ngẫu nhiên 1 ảnh
    selected_image = random.choice(images)
    return os.path.join(REWARD_FOLDER, selected_image)

# --- Event: Voice State Update (Core Logic) ---
@bot.event
async def on_voice_state_update(member, before, after):
    # 1. Check xem Target ID đã config chưa
    if TARGET_VC_ID == 0:
        print("⚠️ Chưa cấu hình TARGET_VOICE_CHANNEL_ID trong .env")
        return

    user_id = member.id
    username = member.name
    avatar_url = str(member.avatar.url) if member.avatar else None

    # --- LOGIC LỌC KÊNH (TARGET CHANNEL FILTER) ---

    # Helper: User có đang ở trong kênh Target không?
    # True nếu kênh hiện tại trùng với Target ID
    in_target_before = (before.channel is not None and before.channel.id == TARGET_VC_ID)
    in_target_after = (after.channel is not None and after.channel.id == TARGET_VC_ID)

    # JOINING: Trước đó KHÔNG ở Target -> Sau đó Ở Target
    is_joining = not in_target_before and in_target_after

    # LEAVING: Trước đó Ở Target -> Sau đó KHÔNG ở Target (Rời hẳn hoặc sang kênh khác)
    is_leaving = in_target_before and not in_target_after

    # STAYING: Trước và Sau đều ở Target (Chỉ đổi trạng thái Mic/Loa)
    is_staying = in_target_before and in_target_after

    # =========================================================
    # 1. XỬ LÝ KẾT THÚC SESSION (Rời phòng HOẶC Tắt tai nghe/mic)
    # =========================================================
    should_end = is_leaving or (is_staying and (after.self_deaf or after.self_mute))

    if should_end:
        session = database.get_active_session(user_id)

        if session:
            session_id = session['session_id']
            task_id = session['task_id']

            # --- A. TÍNH TOÁN DURATION TẠM THỜI (Đề phòng session bị xóa) ---
            join_time = session.get('join_time')
            provisional_duration = 0
            if join_time and isinstance(join_time, datetime):
                time_difference = datetime.now() - join_time
                provisional_duration = int(time_difference.total_seconds())

            # --- B. KẾT THÚC SESSION ---
            # (Hàm này trả về None nếu duration < 60s và bị xóa)
            updated_session = database.end_session(session_id)

            # --- C. XỬ LÝ LOGIC VÀ GỬI THÔNG BÁO ---

            # === TRƯỜNG HỢP 1: SESSION HỢP LỆ (Đủ dài) ===
            if updated_session:
                current_duration = updated_session['work_duration']
                is_verified = updated_session['is_verified']

                # Lấy tổng thời gian cộng dồn cho Task này
                total_duration = database.get_accumulated_duration(user_id, task_id)
                min_work_seconds = database.get_setting("min_work_seconds")

                # >>> LOGIC MỚI: TỰ ĐỘNG TẠO CODE (AUTO-GENERATE) <<<
                generated_code = None
                code_msg = ""

                # Nếu (Đủ thời gian) VÀ (Chưa Verify) -> Tự động xử lý Code
                if total_duration >= min_work_seconds and not is_verified:

                    # Kiểm tra xem đã có code cũ chưa?
                    if database.has_active_submission(session_id):
                        generated_code = database.get_submission_code(session_id)
                        code_msg = f"Code cũ của bạn: `{generated_code}`"
                    else:
                        # CHƯA CÓ -> TẠO MỚI LUÔN
                        new_code = secrets.token_hex(3).upper()
                        database.create_submission(session_id, user_id, task_id, new_code)
                        generated_code = new_code
                        code_msg = f"✅ **AUTO-GENERATED:** `{new_code}`"

                # >>> XÁC ĐỊNH TRẠNG THÁI <<<
                status_msg = "❌ Session Invalid"
                if total_duration >= min_work_seconds:
                    if is_verified:
                        status_msg = "✅ Attendance COUNTED"
                        database.update_session_counted_status(session_id, True)
                    else:
                        status_msg = "⚠️ Đủ thời gian - Đang chờ Verify"
                else:
                    status_msg = "⚠️ Chưa đủ thời gian làm việc"

                # >>> TẠO EMBED <<<
                embed = discord.Embed()
                if is_leaving:
                    embed.title = "🛑 Work Session Ended"
                    embed.color = discord.Color.orange()
                else:
                    embed.title = "⏸️ Session Paused"
                    embed.description = "Dừng tính giờ (Deafen/Mute)."
                    embed.color = discord.Color.red()

                embed.add_field(name="Phiên này", value=str(timedelta(seconds=current_duration)), inline=True)
                embed.add_field(name="Tổng cộng dồn", value=f"**{str(timedelta(seconds=total_duration))}**",
                                inline=True)
                embed.add_field(name="Trạng thái", value=status_msg, inline=False)

                # Nếu có Code (Tự tạo hoặc Cũ) -> Hiển thị luôn
                if generated_code:
                    embed.add_field(name="🔐 VERIFY CODE", value=code_msg, inline=False)
                    embed.set_footer(text=f"Gửi code này cho Boss: /verify {generated_code}")
                elif total_duration < min_work_seconds:
                    embed.set_footer(text=f"Cần làm thêm để nhận Code (Min: {min_work_seconds}s)")

            # === TRƯỜNG HỢP 2: SESSION BỊ XÓA (Quá ngắn) ===
            else:
                # Sử dụng thời gian tạm tính (provisional_duration)
                current_duration_str = str(timedelta(seconds=provisional_duration))

                embed = discord.Embed()
                if is_leaving:
                    embed.title = "🛑 Work Session Ended"
                    embed.color = discord.Color.orange()
                else:
                    embed.title = "⏸️ Session Paused"
                    embed.color = discord.Color.red()

                embed.add_field(name="Duration", value=current_duration_str, inline=True)
                embed.add_field(name="Verified", value="No", inline=True)
                embed.add_field(name="Status", value="⚠️ Time too short (Deleted)", inline=False)
                embed.set_footer(text="Session dưới 1 phút không được ghi nhận.")

            # Gửi DM
            try:
                await member.send(embed=embed)
            except discord.Forbidden:
                pass

        # Nếu là leaving hoặc mute thì xong việc, return luôn
        if is_leaving or (is_staying and (after.self_deaf or after.self_mute)):
            return

    # =========================================================
    # 2. XỬ LÝ BẮT ĐẦU SESSION (Vào phòng HOẶC Bật lại tai nghe)
    # =========================================================
    should_start = (is_joining and not (after.self_deaf or after.self_mute)) or \
                   (is_staying and (before.self_deaf or before.self_mute) and not (after.self_deaf or after.self_mute))

    if should_start:
        if database.get_active_session(user_id):
            return

        database.get_or_create_user(user_id, username, avatar_url)

        # --- LOGIC RESUME TASK ---
        task_id = database.get_recent_task_id(user_id, minutes_threshold=15)

        if task_id:
            task_data = database.fetch_one("SELECT * FROM tasks WHERE task_id = %s", (task_id,))
            task_name = task_data['task_name'] + " (Resumed)"
            task_desc = task_data['task_description']
        else:
            task_data = database.get_random_active_task()
            task_id = task_data['task_id'] if task_data else None
            task_name = task_data['task_name'] if task_data else "No active tasks"
            task_desc = task_data['task_description'] if task_data else "..."

        database.start_session(
            user_id=user_id,
            task_id=task_id,
            guild_id=member.guild.id,
            voice_channel_id=after.channel.id
        )

        total_duration = database.get_accumulated_duration(user_id, task_id)
        total_duration_str = str(timedelta(seconds=total_duration))

        embed = discord.Embed(title="🚀 Work Session Started", color=discord.Color.green())
        if is_staying:
            embed.description = "Bạn đã bật lại tai nghe. Tiếp tục tính giờ!"

        embed.add_field(name="Channel", value=after.channel.name, inline=False)
        embed.add_field(name="Task", value=f"**{task_name}**", inline=False)
        embed.add_field(name="Task Description", value=task_desc, inline=False)
        embed.add_field(name="Total Task Time", value=f"**{total_duration_str}**", inline=False)

        try:
            await member.send(embed=embed)
        except discord.Forbidden:
            print(f"Cannot DM {username}")


# --- Slash Command: /done (ĐÃ CẬP NHẬT LOGIC TÌM SESSION) ---
@bot.tree.command(name="done", description="Submit your assigned task as complete.")
async def done(interaction: discord.Interaction):
    """
    User submits their task. Bot generates a code.
    MỚI: Cho phép /done cho session vừa kết thúc (trong vòng 15 phút).
    """
    user_id = interaction.user.id

    # 1. Check for Active OR Recently Ended Session
    # *** Cần định nghĩa database.get_active_or_recent_session(user_id) ***
    # Đây là logic SQL bạn đã cung cấp, nhưng được đặt trong database.py:
    # SELECT * FROM work_sessions
    # WHERE user_id = %s
    # AND (leave_time IS NULL OR leave_time > NOW() - INTERVAL 15 MINUTE)
    # ORDER BY session_id DESC LIMIT 1
    session = database.get_active_or_recent_session(user_id)

    # 1.1. Báo lỗi nếu không tìm thấy session hợp lệ
    if not session:
        await interaction.response.send_message(
            "❌ Bạn không có session làm việc đang hoạt động, hoặc session cuối cùng đã kết thúc quá 15 phút. \n"
            "Vui lòng vào lại Voice Channel để bắt đầu session mới.",
            ephemeral=True
        )
        return

    # 1.2. Kiểm tra xem session đã có submission chưa (ngăn spam /done)
    if database.has_active_submission(session['session_id']):
        await interaction.response.send_message(
            f"⚠️ Bạn đã gõ /done cho session này rồi. Code hiện tại là: `{database.get_submission_code(session['session_id'])}`",
            ephemeral=True
        )
        return

    # 1.3. Kiểm tra Task Assignment (Logic giữ nguyên)
    if not session['task_id']:
        await interaction.response.send_message("⚠️ Bạn không có Assigned Task cho session này.", ephemeral=True)
        return

    # 2. Generate Secure Code (Logic giữ nguyên)
    verify_code = secrets.token_hex(3).upper()

    # 3. Save Submission to DB (Logic giữ nguyên)
    database.create_submission(
        session_id=session['session_id'],
        user_id=user_id,
        task_id=session['task_id'],
        verify_code=verify_code
    )

    # 4. Respond to User (Logic giữ nguyên)
    # Cần lấy Task Name lại nếu session đã kết thúc (vì nó không còn là active session nữa)
    # Nếu DB có lưu Task Name trong session, thì dùng luôn. Nếu không:
    task_data = database.get_task_by_id(session['task_id'])
    task_name = task_data['task_name'] if task_data else "Unknown Task"

    embed = discord.Embed(title="📝 Task Submitted", color=discord.Color.blue())
    embed.description = f"Vui lòng gửi code này cho Boss/Manager để verify công việc của bạn."
    embed.add_field(name="Task", value=task_name)
    embed.add_field(name="🔐 Verification Code", value=f"`{verify_code}`")
    embed.set_footer(text="Boss uses: /verify <code>")

    await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------------------------------------------------------
    # [TÍNH NĂNG MỚI] GỬI REWARD IMAGE VÀO DM
    # ---------------------------------------------------------

    # 1. Lấy đường dẫn ảnh
    image_path = get_random_reward_file()

    if image_path:
        try:
            # 2. Tạo đối tượng File của Discord
            file = discord.File(image_path)

            # 3. Tạo Embed chúc mừng (Optional)
            reward_embed = discord.Embed(
                title="🎉 Good Job!",
                description="Cảm ơn bạn đã hoàn thành công việc! Đây là phần thưởng tinh thần cho bạn.",
                color=discord.Color.gold()
            )
            # Đặt ảnh vào trong embed (hoặc gửi rời cũng được)
            reward_embed.set_image(url=f"attachment://{os.path.basename(image_path)}")

            # 4. Gửi thẳng vào DM của User
            await interaction.user.send(embed=reward_embed, file=file)
            print(f"Sent reward {os.path.basename(image_path)} to {interaction.user.name}")

        except discord.Forbidden:
            # User chặn DM
            print(f"Cannot send reward DM to {interaction.user.name}")
        except Exception as e:
            print(f"Error sending reward image: {e}")


# --- Slash Command: /verify (ĐÃ CẬP NHẬT) ---
@bot.tree.command(name="verify", description="[BOSS ONLY] Verify a user's task code.")
@app_commands.describe(code="The 6-character verification code")
async def verify(interaction: discord.Interaction, code: str):
    """
    Boss verifies a code.
    """
    # OPTIONAL: Add logic here to check if interaction.user has a specific 'Boss' role.
    # ... (Permission Check - Giữ nguyên)

    code = code.strip().upper()
    boss_id = interaction.user.id

    # 1. Find Submission
    submission = database.get_submission_by_code(code)

    if not submission:
        await interaction.response.send_message("❌ Invalid or already verified code.", ephemeral=True)
        return

    session_id = submission['session_id']
    worker_id = submission['user_id']

    # 2. Mark as Verified in DB (both tables)
    database.verify_submission(submission['submission_id'], boss_id)
    database.update_session_verification(session_id, True)

    # 3. Thông báo ban đầu cho Boss (để tránh lỗi timeout)
    await interaction.response.send_message(f"✅ Code verified for <@{worker_id}>! Checking attendance status...",
                                            ephemeral=False)

    # 4. [NEW] RE-CHECK ATTENDANCE (Hồi tố)

    # Lấy thông tin session để xem nó đã kết thúc chưa
    session_info = database.fetch_one("SELECT * FROM work_sessions WHERE session_id = %s", (session_id,))

    if session_info:
        # Lấy thông tin cần thiết
        leave_time = session_info.get('leave_time')
        duration = session_info.get('work_duration', 0)  # Dùng .get để an toàn

        # Kiểm tra xem session đã kết thúc chưa (leave_time IS NOT NULL)
        if leave_time is not None:
            # Session đã kết thúc, giờ kiểm tra lại thời gian xem đủ chưa
            min_work = database.get_setting("min_work_seconds")

            # Logic: Đủ thời gian VÀ đã verify (luôn đúng vì vừa verify ở trên)
            if duration >= min_work:
                # CẬP NHẬT LẠI TRẠNG THÁI COUNTED
                database.update_session_counted_status(session_id, True)

                # Format duration để hiển thị đẹp hơn
                duration_str = str(timedelta(seconds=duration))

                # Gửi follow-up (cập nhật thông báo ban đầu)
                await interaction.followup.send(
                    f"✅ Session đã được verified và kết thúc. Thời gian làm việc: **{duration_str}**. **Attendance COUNTED!**"
                )
            else:
                # Gửi follow-up
                await interaction.followup.send(
                    f"✅ Session đã được verified nhưng thời gian làm việc ({duration}s) quá ngắn. Not counted."
                )
        else:
            # Session vẫn đang chạy, chỉ xác nhận verify
            await interaction.followup.send(
                f"✅ Verified! User <@{worker_id}> is still working. Attendance will be calculated when they leave.",
                ephemeral=True
            )
    else:
        # Lỗi: Không tìm thấy session
        await interaction.followup.send("❌ Error: Could not find session information.", ephemeral=True)



# --- Slash Command: /status ---
@bot.tree.command(name="status", description="Check your current session status.")
async def status(interaction: discord.Interaction):
    session = database.get_active_session(interaction.user.id)

    if not session:
        await interaction.response.send_message("💤 You are not currently working.", ephemeral=True)
    else:
        join_time = session['join_time']
        task_name = session['task_name']
        embed = discord.Embed(title="Currently Working 👨‍💻", color=discord.Color.green())
        embed.add_field(name="Task", value=task_name)
        embed.add_field(name="Started At", value=discord.utils.format_dt(join_time, style='R'))
        await interaction.response.send_message(embed=embed, ephemeral=True)


# --- Run the Bot ---
if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found in .env file.")
    else:
        bot.run(TOKEN)