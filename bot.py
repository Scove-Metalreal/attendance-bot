# Updated bot.py - Smart Task Assignment System
import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import secrets
from dotenv import load_dotenv
from datetime import timedelta, datetime
import random

import database

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
REWARD_FOLDER = "reward_images"
TARGET_VC_ID = int(os.getenv('TARGET_VOICE_CHANNEL_ID', 0))
LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID', 0))

# Leader role/user IDs
LEADERS = [123456789012345678]  # Add leader Discord IDs

# USER ROLE MAPPING (Discord ID -> Role in Sheet)
USER_ROLE_MAPPING = {
    1025600433722499152: "Project Lead",
    774590488811405372: "Tech Lead",
    1409363976386515015: "Level Builder/QA",
    939678863745757304: "Gameplay Prog",
    # Add more mappings here
}

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- Helper Functions ---
async def send_to_log_channel(guild, content=None, embed=None, file=None):
    if LOG_CHANNEL_ID == 0:
        return
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel:
        try:
            await channel.send(content=content, embed=embed, file=file)
        except Exception as e:
            print(f"❌ Error sending to log: {e}")

def get_random_reward_file():
    if not os.path.exists(REWARD_FOLDER):
        return None
    files = os.listdir(REWARD_FOLDER)
    images = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))]
    if not images:
        return None
    return os.path.join(REWARD_FOLDER, random.choice(images))

def is_leader(user_id: int):
    return user_id in LEADERS

# --- Events ---
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"✅ Bot online as {bot.user}")
        print(f"✅ Synced {len(synced)} commands")
        print(f"🎯 Monitoring VC: {TARGET_VC_ID}")
        print(f"📢 Log Channel: {LOG_CHANNEL_ID}")
    except Exception as e:
        print(f"❌ Failed to sync: {e}")

    # Sync tasks from sheet
    print("📊 Syncing tasks from Sheet...")
    database.sync_tasks_from_sheet()

    # Start auto-sync task
    auto_sync_tasks.start()

    # Fix stale sessions
    print("🔄 Fixing stale sessions...")
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT session_id, user_id, guild_id FROM work_sessions WHERE leave_time IS NULL")
    stale = cursor.fetchall()
    count = 0
    for s in stale:
        guild = bot.get_guild(s['guild_id'])
        if guild:
            member = guild.get_member(s['user_id'])
            if not (member and member.voice and member.voice.channel):
                database.end_session(s['session_id'])
                count += 1
    cursor.close()
    conn.close()
    print(f"✅ Fixed {count} stale sessions")

@tasks.loop(minutes=30)
async def auto_sync_tasks():
    """Auto-sync tasks from Google Sheet every 30 minutes"""
    print("📊 Auto-syncing tasks...")
    database.sync_tasks_from_sheet()

@bot.event
async def on_voice_state_update(member, before, after):
    if TARGET_VC_ID == 0:
        return

    user_id = member.id
    username = member.name
    display_name = member.display_name
    avatar_url = str(member.avatar.url) if member.avatar else None
    guild = member.guild

    # Determine user role
    user_role = USER_ROLE_MAPPING.get(user_id)
    
    # Update user in DB with role
    database.get_or_create_user(user_id, username, avatar_url, display_name, user_role)

    # Check if in target channel
    in_target_before = (before.channel and before.channel.id == TARGET_VC_ID)
    in_target_after = (after.channel and after.channel.id == TARGET_VC_ID)

    is_joining = not in_target_before and in_target_after
    is_leaving = in_target_before and not in_target_after
    is_staying = in_target_before and in_target_after

    # ========== END SESSION ==========
    should_end = is_leaving or (is_staying and (after.self_deaf or after.self_mute))

    if should_end:
        session = database.get_active_session(user_id)
        if session:
            session_id = session['session_id']
            task_id = session['task_id']
            updated_session = database.end_session(session_id)

            if updated_session:
                duration = updated_session['work_duration']
                is_verified = updated_session['is_verified']
                total_duration = database.get_accumulated_duration(user_id, task_id)
                min_work = database.get_setting("min_work_seconds")

                # Auto-generate code
                generated_code = None
                code_msg = ""
                if total_duration >= min_work and not is_verified:
                    if database.check_submission_exists(session_id):
                        generated_code = database.get_submission_code(session_id)
                        code_msg = f"Code cũ: `{generated_code}`"
                    else:
                        new_code = secrets.token_hex(3).upper()
                        database.create_submission(session_id, user_id, task_id, new_code)
                        generated_code = new_code
                        code_msg = f"✅ **AUTO-GENERATED:** `{new_code}`"

                # Status message
                status_msg = "❌ Session Invalid"
                if total_duration >= min_work:
                    if is_verified:
                        status_msg = "✅ Attendance COUNTED"
                        database.update_session_counted_status(session_id, True)
                    else:
                        status_msg = "⚠️ Đủ thời gian - Chờ Verify"
                else:
                    status_msg = "⚠️ Chưa đủ thời gian"

                # Create embed
                embed = discord.Embed()
                if is_leaving:
                    embed.title = "🛑 Work Session Ended"
                    embed.color = discord.Color.orange()
                else:
                    embed.title = "⏸️ Session Paused"
                    embed.description = "Dừng tính giờ (Deafen/Mute)"
                    embed.color = discord.Color.red()

                embed.set_author(name=display_name, icon_url=avatar_url)
                embed.add_field(name="Phiên này", value=str(timedelta(seconds=duration)), inline=True)
                embed.add_field(name="Tổng cộng dồn", value=f"**{str(timedelta(seconds=total_duration))}**", inline=True)
                embed.add_field(name="Trạng thái", value=status_msg, inline=False)

                if session['task_name']:
                    task_code = session.get('task_code', 'N/A')
                    embed.add_field(name="Task", value=f"{session['task_name']} ({task_code})", inline=False)

                if generated_code:
                    embed.add_field(name="🔐 VERIFY CODE", value=code_msg, inline=False)
                    embed.set_footer(text=f"Gửi code này cho Boss: /verify {generated_code}")

                await send_to_log_channel(guild, content=f"<@{user_id}>", embed=embed)

        if is_leaving or (is_staying and (after.self_deaf or after.self_mute)):
            return

    # ========== START SESSION ==========
    should_start = (is_joining and not (after.self_deaf or after.self_mute)) or \
                   (is_staying and (before.self_deaf or before.self_mute) and not (after.self_deaf or after.self_mute))

    if should_start:
        if database.get_active_session(user_id):
            return

        # Smart task assignment
        task_id = None
        task_name = "Unknown Task"
        task_code = None
        task_desc = "..."
        source_msg = ""
        task_data = None

        # Priority 1: Smart assignment from synced sheet
        if user_role:
            print(f"🔍 Finding smart task for {display_name} ({user_role})...")
            task_data = database.get_smart_task_for_user(user_role)
            
            if task_data:
                task_id = task_data['task_id']
                task_code = task_data['task_code']
                task_name = f"[{task_code}] {task_data['task_name']}"
                task_desc = task_data['notes'] or task_data['deliverables'] or "..."
                
                priority_emoji = {
                    'Cao': '🔴',
                    'Trung bình': '🟡',
                    'Thấp': '🟢'
                }.get(task_data['priority'], '⚪')
                
                source_msg = f"📊 Sheet (Smart) {priority_emoji} {task_data['priority']}"
                
                # Show progress
                progress = task_data['progress']
                if progress > 0:
                    source_msg += f" | {progress}% done"
            else:
                print(f"⚠️ No suitable task found for {user_role}")

        # Priority 2: Resume recent task
        if not task_id:
            recent_session = database.get_active_or_recent_session(user_id)
            if recent_session and recent_session['task_id']:
                task_id = recent_session['task_id']
                task_data = database.fetch_one("SELECT * FROM tasks WHERE task_id = %s", (task_id,))
                if task_data:
                    task_code = task_data['task_code']
                    task_name = f"[{task_code}] {task_data['task_name']} (Resumed)"
                    task_desc = task_data['notes'] or "..."
                    source_msg = "🔄 Resumed Previous"

        # Priority 3: Fallback to any available task
        if not task_id:
            if user_role:
                all_tasks = database.get_tasks_by_owner(user_role)
                if all_tasks:
                    task_data = all_tasks[0]
                    task_id = task_data['task_id']
                    task_code = task_data['task_code']
                    task_name = f"[{task_code}] {task_data['task_name']}"
                    task_desc = task_data['notes'] or "..."
                    source_msg = "🎲 Fallback Assignment"

        if not task_id:
            task_name = "No active tasks available"
            task_desc = "Contact admin to assign tasks"
            source_msg = "⚠️ System"

        # Start session
        session_id = database.start_session(user_id, task_id, guild.id, after.channel.id)

        # Get accumulated time
        total_duration = 0
        if task_id:
            total_duration = database.get_accumulated_duration(user_id, task_id)

        # Send start notification
        embed = discord.Embed(title="🚀 Work Session Started", color=discord.Color.green())
        if is_staying:
            embed.description = "Đã bật lại tai nghe. Tiếp tục tính giờ!"

        embed.set_author(name=display_name, icon_url=avatar_url)
        embed.add_field(name="Channel", value=after.channel.name, inline=False)
        embed.add_field(name="Task", value=f"**{task_name}**", inline=False)
        
        if task_data:
            # Add task details
            if task_data.get('priority'):
                embed.add_field(name="Priority", value=task_data['priority'], inline=True)
            if task_data.get('start_date'):
                embed.add_field(name="Start Date", value=task_data['start_date'], inline=True)
            if task_data.get('end_date'):
                embed.add_field(name="Due Date", value=task_data['end_date'], inline=True)
            if task_data.get('phase'):
                embed.add_field(name="Phase", value=task_data['phase'], inline=False)
        
        embed.add_field(name="Source", value=f"`{source_msg}`", inline=False)
        
        if task_code:
            embed.add_field(name="Code", value=f"`{task_code}`", inline=True)
        
        if total_duration > 0:
            embed.add_field(name="Đã làm hôm nay", value=str(timedelta(seconds=total_duration)), inline=True)

        await send_to_log_channel(guild, content=f"<@{user_id}> Chúc bạn làm việc hiệu quả! 💪", embed=embed)

# --- Slash Commands ---

@bot.tree.command(name="working_on", description="Khai báo task đang làm để bot ghi chú lại")
@app_commands.describe(task="Task code from sheet (e.g., F-01)")
async def working_on(interaction: discord.Interaction, task: str):
    user_id = interaction.user.id
    task_data = database.get_task_by_code(task.upper())
    
    if not task_data:
        await interaction.response.send_message("❌ Không tìm thấy task với code này.", ephemeral=True)
        return

    session = database.get_active_or_recent_session(user_id)
    if not session:
        await interaction.response.send_message("❌ Bạn cần đang trong session làm việc.", ephemeral=True)
        return

    # Update session task
    sql = "UPDATE work_sessions SET task_id = %s WHERE session_id = %s"
    if database.execute_query(sql, (task_data['task_id'], session['session_id'])):
        task_name = f"[{task.upper()}] {task_data['task_name']}"
        embed = discord.Embed(title="✅ Đã cập nhật task", color=discord.Color.blue())
        embed.add_field(name="Task mới", value=task_name, inline=False)
        embed.add_field(name="Priority", value=task_data['priority'], inline=True)
        embed.add_field(name="Status", value=task_data['status'], inline=True)
        embed.add_field(name="Progress", value=task_data['progress_percent'], inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Update task status to 'Đang thực hiện'
        database.update_task_progress(task_data['task_id'], task_data['progress'], 'Đang thực hiện')
    else:
        await interaction.response.send_message("❌ Lỗi cập nhật.", ephemeral=True)

@bot.tree.command(name="done", description="Nộp bài, yêu cầu Review (bắt buộc có link Git)")
@app_commands.describe(
    task="Task code (e.g., F-01)",
    link="Git commit/branch/PR link (required)",
    progress="Progress % (default: 100)"
)
async def done(interaction: discord.Interaction, task: str, link: str, progress: int = 100):
    user_id = interaction.user.id
    
    # Validate link
    if not link or not ('github.com' in link.lower() or 'gitlab' in link.lower() or 'bitbucket' in link.lower()):
        await interaction.response.send_message("❌ Vui lòng cung cấp link Git hợp lệ (GitHub/GitLab/Bitbucket).", ephemeral=True)
        return
    
    # Validate progress
    if not (0 <= progress <= 100):
        await interaction.response.send_message("❌ Progress phải từ 0-100%.", ephemeral=True)
        return

    session = database.get_active_or_recent_session(user_id)
    if not session:
        await interaction.response.send_message("❌ Bạn không có session làm việc nào gần đây.", ephemeral=True)
        return

    task_data = database.get_task_by_code(task.upper())
    if not task_data:
        await interaction.response.send_message("❌ Không tìm thấy task với code này.", ephemeral=True)
        return

    if database.check_submission_exists(session['session_id']):
        code = database.get_submission_code(session['session_id'])
        await interaction.response.send_message(f"⚠️ Đã có code rồi: `{code}`", ephemeral=True)
        return

    verify_code = secrets.token_hex(3).upper()
    database.create_submission(session['session_id'], user_id, task_data['task_id'], verify_code, link, progress)
    
    # Update task progress immediately (pending verification)
    new_status = 'Đã hoàn thành' if progress >= 100 else 'Đang thực hiện'
    database.update_task_progress(task_data['task_id'], progress, new_status)

    task_name = f"[{task.upper()}] {task_data['task_name']}"

    # Private response
    embed_private = discord.Embed(title="✅ Đã nộp Task!", color=discord.Color.blue())
    embed_private.add_field(name="Code", value=f"`{verify_code}`")
    embed_private.add_field(name="Progress", value=f"{progress}%", inline=True)
    embed_private.add_field(name="Link", value=link, inline=False)
    embed_private.set_footer(text="Bot đã gửi ảnh reward vào kênh chat chung!")
    await interaction.response.send_message(embed=embed_private, ephemeral=True)

    # Public reward notification
    image_path = get_random_reward_file()
    embed_public = discord.Embed(title="🎉 Task Completed!", color=discord.Color.gold())
    embed_public.set_author(
        name=interaction.user.display_name,
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    embed_public.description = f"<@{user_id}> vừa hoàn thành task **{task_name}**!"
    embed_public.add_field(name="Progress", value=f"{progress}%", inline=True)
    embed_public.add_field(name="🔐 Verify Code", value=f"`{verify_code}` (Leader verify giúp nhé)", inline=False)
    embed_public.add_field(name="🔗 Git Link", value=link, inline=False)

    file = None
    if image_path:
        file = discord.File(image_path)
        embed_public.set_image(url=f"attachment://{os.path.basename(image_path)}")

    await send_to_log_channel(interaction.guild, content=f"<@{user_id}> Giỏi quá! 🎊", embed=embed_public, file=file)

@bot.tree.command(name="my_stats", description="Xem tổng số giờ làm, số task đã xong của bản thân")
async def my_stats(interaction: discord.Interaction):
    user_id = interaction.user.id
    stats = database.get_user_stats(user_id)
    
    embed = discord.Embed(title="📊 Thống kê cá nhân", color=discord.Color.blue())
    embed.set_author(
        name=interaction.user.display_name,
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    embed.add_field(name="Tổng giờ làm (30 ngày)", value=f"{stats['total_hours']} giờ", inline=True)
    embed.add_field(name="Task hoàn thành", value=str(stats['completed_tasks']), inline=True)
    
    # Get current session if any
    session = database.get_active_session(user_id)
    if session and session['task_name']:
        embed.add_field(name="Đang làm", value=f"{session['task_name']}", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="todo", description="Xem danh sách task đang được gán cho mình")
async def todo(interaction: discord.Interaction):
    user_id = interaction.user.id
    user_role = database.get_user_role(user_id)
    
    if not user_role:
        await interaction.response.send_message("📝 Chưa có role được gán. Liên hệ admin.", ephemeral=True)
        return
    
    tasks = database.get_tasks_by_owner(user_role)
    if not tasks:
        await interaction.response.send_message("📝 Không có task nào đang chờ bạn.", ephemeral=True)
        return

    embed = discord.Embed(title=f"📋 Todo List ({user_role})", color=discord.Color.orange())
    
    for task in tasks[:10]:  # Limit to 10 tasks
        priority_emoji = {'Cao': '🔴', 'Trung bình': '🟡', 'Thấp': '🟢'}.get(task['priority'], '⚪')
        
        task_info = f"**[{task['task_code']}] {task['task_name']}**\n"
        task_info += f"{priority_emoji} {task['priority']} | {task['status']} | {task['progress_percent']}\n"
        
        if task['start_date']:
            task_info += f"📅 Start: {task['start_date']}"
        if task['end_date']:
            task_info += f" → Due: {task['end_date']}"
        
        if task['notes']:
            task_info += f"\n💡 {task['notes'][:50]}..."
        
        embed.add_field(name=task['phase'] or "No Phase", value=task_info, inline=False)
    
    if len(tasks) > 10:
        embed.set_footer(text=f"Showing 10/{len(tasks)} tasks")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="leaderboard", description="Xem xếp hạng chăm chỉ của cả team")
async def leaderboard(interaction: discord.Interaction):
    board = database.get_leaderboard(10)
    embed = discord.Embed(title="🏆 Leaderboard (Giờ làm - 30 ngày)", color=discord.Color.gold())
    
    medals = ['🥇', '🥈', '🥉']
    for i, entry in enumerate(board, 1):
        hours = round(int(entry['total_seconds']) / 3600, 1)
        medal = medals[i-1] if i <= 3 else f"{i}."
        embed.add_field(name=f"{medal} {entry['username']}", value=f"{hours} giờ", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=False)

@bot.tree.command(name="status", description="Xem trạng thái làm việc hiện tại")
async def status(interaction: discord.Interaction):
    session = database.get_active_session(interaction.user.id)
    
    if not session:
        await interaction.response.send_message("💤 Bạn đang không trong phiên làm việc nào.", ephemeral=True)
    else:
        task_name = session.get('task_name', 'Unknown')
        task_code = session.get('task_code', 'N/A')
        progress = session.get('progress', 0)
        total_duration = database.get_accumulated_duration(interaction.user.id, session['task_id'])
        
        embed = discord.Embed(title="👨‍💻 Đang làm việc", color=discord.Color.green())
        embed.add_field(name="Task", value=f"[{task_code}] {task_name}")
        embed.add_field(name="Progress", value=f"{progress}%", inline=True)
        embed.add_field(name="Tổng thời gian hôm nay", value=str(timedelta(seconds=total_duration)))
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Leader Commands ---

@bot.tree.command(name="verify", description="[BOSS] Duyệt task")
async def verify(interaction: discord.Interaction, code: str):
    if not is_leader(interaction.user.id):
        await interaction.response.send_message("❌ Chỉ Leader mới dùng được lệnh này.", ephemeral=True)
        return
    
    code = code.strip().upper()
    boss_id = interaction.user.id

    submission = database.get_submission_by_code(code)
    if not submission:
        await interaction.response.send_message("❌ Code không đúng hoặc đã duyệt.", ephemeral=True)
        return

    session_id = submission['session_id']
    worker_id = submission['user_id']

    database.verify_submission(submission['submission_id'], boss_id, approved=True)
    database.update_session_verification(session_id, True)

    # Re-check attendance
    session_info = database.fetch_one("SELECT * FROM work_sessions WHERE session_id = %s", (session_id,))
    msg_extra = ""
    if session_info and session_info['leave_time']:
        total_duration = database.get_accumulated_duration(worker_id, session_info['task_id'])
        min_work = database.get_setting("min_work_seconds")

        if total_duration >= min_work:
            database.update_session_counted_status(session_id, True)
            msg_extra = f"⏱️ Total: {timedelta(seconds=total_duration)}. **Attendance COUNTED!**"
        else:
            msg_extra = f"⚠️ Total: {timedelta(seconds=total_duration)} (Not enough)"

    # Public notification
    embed = discord.Embed(title="✅ Task Verified", color=discord.Color.green())
    embed.description = f"Sếp <@{boss_id}> đã duyệt bài cho <@{worker_id}>.\nCode: `{code}`"
    
    if submission['submission_link']:
        embed.add_field(name="🔗 Git Link", value=submission['submission_link'], inline=False)
    
    if msg_extra:
        embed.add_field(name="Kết quả chấm công", value=msg_extra, inline=False)

    await interaction.response.send_message("Đã duyệt! ✅", ephemeral=True)
    await send_to_log_channel(interaction.guild, content=f"<@{worker_id}>", embed=embed)

@bot.tree.command(name="approve", description="[Leader] Duyệt task, xác nhận hoàn thành")
@app_commands.describe(task="Task code (e.g., F-01)")
async def approve(interaction: discord.Interaction, task: str):
    if not is_leader(interaction.user.id):
        await interaction.response.send_message("❌ Chỉ Leader mới dùng được lệnh này.", ephemeral=True)
        return

    task_data = database.get_task_by_code(task.upper())
    if not task_data:
        await interaction.response.send_message("❌ Không tìm thấy task.", ephemeral=True)
        return

    if database.update_task_progress(task_data['task_id'], 100, "Đã hoàn thành"):
        embed = discord.Embed(title="✅ Task Approved", color=discord.Color.green())
        embed.description = f"Task **{task_data['task_name']}** đã được duyệt!"
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await send_to_log_channel(interaction.guild, content=f"<@{interaction.user.id}> approved {task.upper()}", embed=embed)
    else:
        await interaction.response.send_message("❌ Lỗi cập nhật.", ephemeral=True)

@bot.tree.command(name="reject", description="[Leader] Trả task về yêu cầu sửa lại")
@app_commands.describe(task="Task code (e.g., F-01)")
async def reject(interaction: discord.Interaction, task: str):
    if not is_leader(interaction.user.id):
        await interaction.response.send_message("❌ Chỉ Leader mới dùng được lệnh này.", ephemeral=True)
        return

    task_data = database.get_task_by_code(task.upper())
    if not task_data:
        await interaction.response.send_message("❌ Không tìm thấy task.", ephemeral=True)
        return

    if database.update_task_progress(task_data['task_id'], task_data['progress'], "Cần sửa"):
        embed = discord.Embed(title="❌ Task Rejected", color=discord.Color.red())
        embed.description = f"Task **{task_data['task_name']}** cần sửa lại."
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await send_to_log_channel(interaction.guild, content=f"<@{interaction.user.id}> rejected {task.upper()}", embed=embed)
    else:
        await interaction.response.send_message("❌ Lỗi cập nhật.", ephemeral=True)

@bot.tree.command(name="force_checkout", description="[Leader] Đá thành viên ra khỏi phiên làm việc")
@app_commands.describe(user="User to checkout")
async def force_checkout(interaction: discord.Interaction, user: discord.Member):
    if not is_leader(interaction.user.id):
        await interaction.response.send_message("❌ Chỉ Leader mới dùng được lệnh này.", ephemeral=True)
        return

    target_id = user.id
    session = database.get_active_session(target_id)
    if not session:
        await interaction.response.send_message("❌ User không có session active.", ephemeral=True)
        return

    database.end_session(session['session_id'])
    embed = discord.Embed(title="🛑 Forced Checkout", color=discord.Color.red())
    embed.description = f"<@{target_id}> đã bị checkout bởi <@{interaction.user.id}>."
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await send_to_log_channel(interaction.guild, content=f"<@{target_id}>", embed=embed)

@bot.tree.command(name="sync_sheet", description="[Leader] Đồng bộ tasks từ Google Sheet")
async def sync_sheet(interaction: discord.Interaction):
    if not is_leader(interaction.user.id):
        await interaction.response.send_message("❌ Chỉ Leader mới dùng được lệnh này.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        success = database.sync_tasks_from_sheet()
        if success:
            await interaction.followup.send("✅ Đã đồng bộ tasks từ Sheet thành công!", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Không có tasks mới để đồng bộ.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Lỗi đồng bộ: {e}", ephemeral=True)

@bot.tree.command(name="update_progress", description="[Leader] Cập nhật progress của task")
@app_commands.describe(
    task="Task code (e.g., F-01)",
    progress="Progress % (0-100)"
)
async def update_progress(interaction: discord.Interaction, task: str, progress: int):
    if not is_leader(interaction.user.id):
        await interaction.response.send_message("❌ Chỉ Leader mới dùng được lệnh này.", ephemeral=True)
        return
    
    if not (0 <= progress <= 100):
        await interaction.response.send_message("❌ Progress phải từ 0-100%.", ephemeral=True)
        return
    
    task_data = database.get_task_by_code(task.upper())
    if not task_data:
        await interaction.response.send_message("❌ Không tìm thấy task.", ephemeral=True)
        return
    
    new_status = None
    if progress >= 100:
        new_status = "Đã hoàn thành"
    elif progress > 0 and task_data['status'] == 'Chưa bắt đầu':
        new_status = "Đang thực hiện"
    
    if database.update_task_progress(task_data['task_id'], progress, new_status):
        embed = discord.Embed(title="✅ Progress Updated", color=discord.Color.blue())
        embed.description = f"Task **{task_data['task_name']}**"
        embed.add_field(name="Progress", value=f"{progress}%", inline=True)
        if new_status:
            embed.add_field(name="Status", value=new_status, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message("❌ Lỗi cập nhật.", ephemeral=True)

@bot.tree.command(name="task_info", description="Xem thông tin chi tiết của task")
@app_commands.describe(task="Task code (e.g., F-01)")
async def task_info(interaction: discord.Interaction, task: str):
    task_data = database.get_task_by_code(task.upper())
    if not task_data:
        await interaction.response.send_message("❌ Không tìm thấy task.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"[{task_data['task_code']}] {task_data['task_name']}", 
        color=discord.Color.blue()
    )
    
    # Priority with emoji
    priority_emoji = {
        'Cao': '🔴',
        'Trung bình': '🟡',
        'Thấp': '🟢'
    }.get(task_data['priority'], '⚪')
    
    embed.add_field(name="Priority", value=f"{priority_emoji} {task_data['priority']}", inline=True)
    embed.add_field(name="Owner", value=task_data['owner'] or "Unassigned", inline=True)
    embed.add_field(name="Progress", value=task_data['progress_percent'], inline=True)
    embed.add_field(name="Status", value=task_data['status'], inline=True)
    
    if task_data['start_date']:
        embed.add_field(name="Start Date", value=task_data['start_date'], inline=True)
    if task_data['end_date']:
        embed.add_field(name="Due Date", value=task_data['end_date'], inline=True)
    if task_data['duration']:
        embed.add_field(name="Duration", value=f"{task_data['duration']} days", inline=True)
    if task_data['phase']:
        embed.add_field(name="Phase", value=task_data['phase'], inline=False)
    if task_data['deliverables']:
        embed.add_field(name="🔗 Deliverables", value=task_data['deliverables'][:500], inline=False)
    if task_data['notes']:
        embed.add_field(name="📝 Notes", value=task_data['notes'][:500], inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="help", description="Hướng dẫn sử dụng Bot chấm công")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="📖 Hướng dẫn sử dụng Attendance Bot", color=discord.Color.purple())

    target_channel = f"<#{TARGET_VC_ID}>" if TARGET_VC_ID else "kênh Voice quy định"
    min_time = timedelta(seconds=database.get_setting("min_work_seconds"))

    embed.description = f"Bot tự động chấm công và giao việc thông minh khi bạn tham gia {target_channel}."

    embed.add_field(
        name="1️⃣ Bắt đầu làm việc",
        value=f"- Tham gia {target_channel}.\n"
              f"- Bot sẽ **tự động giao task** phù hợp nhất dựa trên:\n"
              f"  • Role của bạn\n"
              f"  • Độ ưu tiên công việc\n"
              f"  • Ngày bắt đầu/deadline\n"
              f"  • Tiến trình hiện tại\n"
              f"- **Lưu ý:** Không tắt tai nghe (Deafen) quá lâu.\n"
              f"- Dùng `/working_on [task_code]` để chuyển task thủ công.",
        inline=False
    )

    embed.add_field(
        name="2️⃣ Báo cáo hoàn thành",
        value="- Khi làm xong, gõ `/done [task_code] [git_link] [progress]`.\n"
              "- **Bắt buộc** phải có link Git (commit/branch/PR).\n"
              "- Bot gửi Code xác nhận và ảnh Reward.\n"
              "- Progress mặc định 100%, có thể điều chỉnh (0-100%).",
        inline=False
    )

    embed.add_field(
        name="3️⃣ Xác nhận & Tính công",
        value=f"- Gửi Code cho Leader.\n"
              f"- Leader dùng `/verify [code]` hoặc `/approve [task_code]`.\n"
              f"- Nếu tổng thời gian > **{min_time}** VÀ đã Verify → **Được tính công**.\n"
              f"- Task và Git link tự động cập nhật lên Google Sheet.",
        inline=False
    )

    embed.add_field(
        name="🛠️ Lệnh cá nhân",
        value="`/my_stats`: Thống kê cá nhân.\n"
              "`/todo`: Danh sách task của bạn.\n"
              "`/status`: Trạng thái hiện tại.\n"
              "`/task_info [task_code]`: Chi tiết task.\n"
              "`/leaderboard`: Xếp hạng team.\n"
              "`/working_on [task]`: Chuyển task thủ công.",
        inline=False
    )

    embed.add_field(
        name="👑 Lệnh Leader",
        value="`/verify [code]`: Duyệt task bằng code.\n"
              "`/approve [task]`: Duyệt task trực tiếp.\n"
              "`/reject [task]`: Từ chối, yêu cầu sửa.\n"
              "`/update_progress [task] [%]`: Cập nhật tiến độ.\n"
              "`/force_checkout [@user]`: Buộc thoát session.\n"
              "`/sync_sheet`: Đồng bộ tasks từ Sheet.",
        inline=False
    )

    embed.set_footer(text="💡 Bot tự động đồng bộ Sheet mỗi 30 phút")

    await interaction.response.send_message(embed=embed, ephemeral=True)

if __name__ == "__main__":
    if not TOKEN:
        print("❌ Error: DISCORD_TOKEN not found.")
    else:
        bot.run(TOKEN)