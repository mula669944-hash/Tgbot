import os
import sys
import shutil
import time
import uuid
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler
from core.database import (
    register_user, get_user, get_user_projects, get_project,
    add_project, delete_project_record, get_setting, create_payment_request
)
from core.process_manager import pm
from core.channel_guard import check_user_membership
from core.keyboards import (
    main_reply_keyboard, my_bots_keyboard, bot_control_keyboard,
    channel_guard_keyboard, premium_plans_keyboard, payment_methods_keyboard,
    admin_payment_decision_keyboard
)
from core.utils import load_config, safe_extract_zip, sanitize_filename

AWAITING_FILE, ENTERING_NAME = range(2)
AWAITING_TRX_ID = 10

# --- চ্যানেল গার্ড ভেরিফিকেশন ---
async def check_guard_and_respond(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    allowed, channels = await check_user_membership(context.bot, user.id)
    if not allowed:
        text = (
            "⚠️ <b>চ্যানেল সাবস্ক্রিপশন প্রয়োজন</b>\n\n"
            f"বটটি ব্যবহার করতে নিচের <b>{len(channels)}টি চ্যানেলে</b> জয়েন করুন।\n"
            "সবগুলোতে জয়েন করার পর <b>Verify Membership</b> বাটনে চাপ দিন।"
        )
        markup = channel_guard_keyboard(channels)
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        elif update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return False
    return True

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.username, user.first_name, default_limit=1)

    if not await check_guard_and_respond(update, context):
        return

    is_admin = user.id in load_config()["admin_ids"]
    msg = (
        f"Welcome <b>{user.first_name}</b>!\n\n"
        "<b>Telegram Python Bot Hoster (Android Termux)</b>\n"
        "• Free Tier: 1 Bot Free Hosting Quota\n"
        "• Upgrade to Premium anytime to host more bots!\n\n"
        "Use the menu below to manage your bots:"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=main_reply_keyboard(is_admin))

async def verify_membership_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    allowed, channels = await check_user_membership(context.bot, user.id)
    if allowed:
        config = load_config()
        await query.edit_message_text("✅ ভেরিফিকেশন সফল হয়েছে। স্বাগতম!", parse_mode=ParseMode.HTML)
        await query.message.reply_text("মেনু থেকে অপশন সিলেক্ট করুন:", reply_markup=main_reply_keyboard(user.id in config["admin_ids"]))
    else:
        await query.edit_message_text(
            "❌ আপনি এখনও সব চ্যানেলে জয়েন করেননি। অনুগ্রহ করে সবগুলো চ্যানেলে জয়েন করে আবার ভেরিফাই করুন।",
            parse_mode=ParseMode.HTML,
            reply_markup=channel_guard_keyboard(channels)
        )

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"Your Telegram ID: <code>{user.id}</code>", parse_mode=ParseMode.HTML)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_guard_and_respond(update, context):
        return
    user = update.effective_user
    projects = get_user_projects(user.id)
    u = get_user(user.id)
    running = sum(1 for p in projects if pm.is_running(p["bot_id"]))
    msg = (
        "<b>Hosting Summary:</b>\n\n"
        f"• Active Running: <b>{running}</b>\n"
        f"• Stopped Bots: <b>{len(projects) - running}</b>\n"
        f"• Total Hosted: <b>{len(projects)} / {u['bot_limit']} Slots Used</b>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_guard_and_respond(update, context):
        return
    user = update.effective_user
    u = get_user(user.id)
    projects = get_user_projects(user.id)
    tier = "Free Plan (1 Bot)" if u['bot_limit'] <= 1 else f"Premium VIP ({u['bot_limit']} Bots)"
    await update.message.reply_text(
        "<b>Account Details:</b>\n\n"
        f"• User ID: <code>{user.id}</code>\n"
        f"• Current Plan: <b>{tier}</b>\n"
        f"• Bot Slot Limit: <b>{u['bot_limit']} Bots</b>\n"
        f"• Slots In Use: <b>{len(projects)} / {u['bot_limit']}</b>\n\n"
        "To upgrade slots, click <b>💎 Buy Premium</b> below.",
        parse_mode=ParseMode.HTML
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_guard_and_respond(update, context):
        return
    await update.message.reply_text(
        "<b>Help & Instructions:</b>\n\n"
        "1. Click <b>➕ Create Bot</b> to upload <code>.py</code> or <code>.zip</code> files.\n"
        "2. If uploading a zip archive, include <code>requirements.txt</code> to auto-install dependencies.\n"
        "3. Free users can host 1 bot. Upgrade to Premium for additional slots.",
        parse_mode=ParseMode.HTML
    )

# --- প্রিমিয়াম প্ল্যান কেনার ফ্লো ---
async def buy_premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_guard_and_respond(update, context):
        return

    s_p = get_setting("plan_starter_price", "50 BDT")
    s_b = get_setting("plan_starter_bots", "2")
    p_p = get_setting("plan_pro_price", "100 BDT")
    p_b = get_setting("plan_pro_bots", "5")
    u_p = get_setting("plan_ultra_price", "200 BDT")
    u_b = get_setting("plan_ultra_bots", "12")

    text = (
        "<b>Upgrade to Premium Bot Hosting:</b>\n\n"
        f"• Starter: +{s_b} Extra Bots — <b>{s_p}</b>\n"
        f"• Pro: +{p_b} Extra Bots — <b>{p_p}</b>\n"
        f"• Ultra: +{u_b} Extra Bots — <b>{u_p}</b>\n\n"
        "Select a package to continue:"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=premium_plans_keyboard())
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=premium_plans_keyboard())

async def plan_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_code = query.data.replace("buyplan_", "")

    price = get_setting(f"plan_{plan_code}_price", "100 BDT")
    extra = int(get_setting(f"plan_{plan_code}_bots", "5"))

    context.user_data["selected_plan_info"] = {
        "code": plan_code,
        "price": price,
        "extra": extra,
        "name": plan_code.capitalize() + " Plan"
    }

    text = (
        f"<b>Selected Package: {plan_code.capitalize()} Plan</b>\n"
        f"• Extra Slots: <b>+{extra} Bots</b>\n"
        f"• Price: <b>{price}</b>\n\n"
        "Choose your payment method:"
    )
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=payment_methods_keyboard(plan_code))

async def payment_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    method = parts[1]
    
    plan_info = context.user_data.get("selected_plan_info")
    if not plan_info:
        await query.edit_message_text("Session expired. Please click 💎 Buy Premium again.")
        return ConversationHandler.END

    pay_number = get_setting(f"pay_{method}", "Contact Admin")

    context.user_data["pending_payment"] = {
        "method": method.upper(),
        "amount": plan_info["price"],
        "extra": plan_info["extra"],
        "plan_name": plan_info["name"]
    }

    text = (
        f"<b>Payment Instructions ({method.upper()})</b>\n\n"
        f"• Plan: <b>{plan_info['name']} (+{plan_info['extra']} Bots)</b>\n"
        f"• Amount: <b>{plan_info['price']}</b>\n"
        f"• Send Money to: <code>{pay_number}</code>\n\n"
        "After payment, please send your <b>Transaction ID (TrxID)</b> here in text:\n\n"
        "<i>Send /cancel to abort.</i>"
    )
    await query.edit_message_text(text, parse_mode=ParseMode.HTML)
    return AWAITING_TRX_ID

async def handle_trx_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trx_id = update.message.text.strip()
    data = context.user_data.get("pending_payment")
    if not data:
        await update.message.reply_text("Session expired. Please try again.")
        return ConversationHandler.END

    user = update.effective_user
    req_id = create_payment_request(
        user_id=user.id,
        plan_name=data["plan_name"],
        extra_bots=data["extra"],
        amount=data["amount"],
        method=data["method"],
        trx_id=trx_id
    )

    await update.message.reply_text(
        "✅ <b>Payment Request Submitted!</b>\n\n"
        f"• TrxID: <code>{trx_id}</code>\n"
        f"• Plan: <b>{data['plan_name']}</b>\n\n"
        "Your request is being reviewed by the admin.",
        parse_mode=ParseMode.HTML
    )

    config = load_config()
    admin_text = (
        "<b>New Payment Request!</b>\n\n"
        f"• User: <b>{user.first_name}</b> (<code>{user.id}</code>)\n"
        f"• Username: @{user.username or 'N/A'}\n"
        f"• Plan: <b>{data['plan_name']} (+{data['extra']} Bots)</b>\n"
        f"• Amount: <b>{data['amount']}</b>\n"
        f"• Method: <b>{data['method']}</b>\n"
        f"• TrxID: <code>{trx_id}</code>"
    )
    for aid in config["admin_ids"]:
        try:
            await context.bot.send_message(
                chat_id=aid,
                text=admin_text,
                parse_mode=ParseMode.HTML,
                reply_markup=admin_payment_decision_keyboard(req_id)
            )
        except Exception:
            pass

    context.user_data.clear()
    return ConversationHandler.END

# --- বট আপলোড উইজার্ড (Auto-Requirements.txt সাপোর্টসহ) ---
async def start_wizard_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_guard_and_respond(update, context):
        return ConversationHandler.END

    user = update.effective_user
    u = get_user(user.id)
    projects = get_user_projects(user.id)

    if len(projects) >= u["bot_limit"]:
        limit_text = (
            f"❌ <b>Limit Reached!</b>\n\n"
            f"You have used <b>{len(projects)} of {u['bot_limit']}</b> allowed bot slots.\n\n"
            "Free users get 1 bot slot. Please upgrade to Premium to add more."
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 Buy Premium Plan", callback_data="buy_premium_start")],
            [InlineKeyboardButton("Cancel", callback_data="menu_close")]
        ])
        await update.message.reply_text(limit_text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return ConversationHandler.END

    await update.message.reply_text(
        "<b>Bot Upload Wizard:</b>\n\n"
        "Please send your bot file:\n"
        "• Send a <code>.py</code> script, OR\n"
        "• Send a <code>.zip</code> archive containing your project files.\n\n"
        "Send /cancel to stop.",
        parse_mode=ParseMode.HTML
    )
    return AWAITING_FILE

async def handle_uploaded_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        await update.message.reply_text("Please send a valid file (.py or .zip).")
        return AWAITING_FILE

    config = load_config()
    max_mb = config["max_upload_size_mb"]
    if doc.file_size > max_mb * 1024 * 1024:
        await update.message.reply_text(f"File exceeds maximum size limit of {max_mb}MB.")
        return ConversationHandler.END

    ext = os.path.splitext(doc.file_name)[1].lower()
    if ext not in [".py", ".zip"]:
        await update.message.reply_text("Only <code>.py</code> and <code>.zip</code> files are supported.", parse_mode=ParseMode.HTML)
        return AWAITING_FILE

    bot_id = str(uuid.uuid4())[:8]
    user_id = update.effective_user.id
    target_dir = os.path.join(config["storage_root"], "bots", str(user_id), bot_id)
    os.makedirs(target_dir, exist_ok=True)

    tg_file = await context.bot.get_file(doc.file_id)
    temp_path = os.path.join(config["storage_root"], "temp", f"{bot_id}_{doc.file_name}")
    await tg_file.download_to_drive(temp_path)

    context.user_data["deploy"] = {
        "bot_id": bot_id,
        "is_zip": (ext == ".zip"),
        "target_dir": target_dir,
        "temp_path": temp_path,
        "orig_name": doc.file_name
    }

    await update.message.reply_text("File received! Please enter a <b>Project Name</b>:", parse_mode=ParseMode.HTML)
    return ENTERING_NAME

async def handle_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_name = update.message.text.strip()
    name = sanitize_filename(raw_name)
    if not name or len(name) < 2:
        await update.message.reply_text("Invalid name. Please use alphanumeric characters:")
        return ENTERING_NAME

    data = context.user_data["deploy"]
    data["project_name"] = name
    config = load_config()

    if data["is_zip"]:
        ok, err = safe_extract_zip(data["temp_path"], data["target_dir"], config["max_zip_extracted_mb"], config["max_files_in_zip"])
        if os.path.exists(data["temp_path"]):
            os.remove(data["temp_path"])
        if not ok:
            shutil.rmtree(data["target_dir"], ignore_errors=True)
            await update.message.reply_text(f"Error: {err}")
            return ConversationHandler.END

        # --- স্বয়ংক্রিয় requirements.txt শনাক্ত ও ইনস্টল সিস্টেম ---
        req_file = os.path.join(data["target_dir"], "requirements.txt")
        if os.path.isfile(req_file):
            status_msg = await update.message.reply_text("📦 <b>requirements.txt পাওয়া গেছে!</b>\nপ্রয়োজনীয় প্যাকেজগুলো ইনস্টল করা হচ্ছে, অনুগ্রহ করে অপেক্ষা করুন...", parse_mode=ParseMode.HTML)
            try:
                install_proc = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--no-cache-dir"],
                    cwd=data["target_dir"],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if install_proc.returncode != 0:
                    err_preview = install_proc.stderr[-300:] if install_proc.stderr else "Installation failed."
                    await status_msg.edit_text(f"⚠️ <b>কিছু প্যাকেজ ইনস্টল হতে ব্যর্থ হয়েছে:</b>\n<pre>{err_preview}</pre>", parse_mode=ParseMode.HTML)
                else:
                    await status_msg.edit_text("✅ <b>সব প্যাকেজ সফলভাবে ইনস্টল হয়েছে!</b>", parse_mode=ParseMode.HTML)
            except subprocess.TimeoutExpired:
                await status_msg.edit_text("⚠️ প্যাকেজ ইনস্টল হতে সময় বেশি লাগছে। প্রজেক্ট ডিপ্লয় সম্পন্ন হচ্ছে...", parse_mode=ParseMode.HTML)
            except Exception as e:
                await status_msg.edit_text(f"⚠️ Pip এরর: {str(e)}")

        py_files = [f for f in os.listdir(data["target_dir"]) if f.endswith(".py")]
        if not py_files:
            shutil.rmtree(data["target_dir"], ignore_errors=True)
            await update.message.reply_text("No .py files found inside the zip archive.")
            return ConversationHandler.END

        if "main.py" in py_files:
            main_file = "main.py"
        elif "bot.py" in py_files:
            main_file = "bot.py"
        else:
            main_file = py_files[0]
        data["main_file"] = main_file
    else:
        dest = os.path.join(data["target_dir"], "main.py")
        shutil.move(data["temp_path"], dest)
        data["main_file"] = "main.py"

    add_project(
        bot_id=data["bot_id"],
        user_id=update.effective_user.id,
        project_name=data["project_name"],
        project_dir=data["target_dir"],
        main_file=data["main_file"]
    )

    await update.message.reply_text(
        "<b>Bot Deployed Successfully!</b>\n\n"
        f"• Project: <b>{data['project_name']}</b>\n"
        f"• Entry: <code>{data['main_file']}</code>\n"
        f"• ID: <code>{data['bot_id']}</code>\n\n"
        "Click <b>📂 My Bots</b> to start and control your bot.",
        parse_mode=ParseMode.HTML
    )
    context.user_data.pop("deploy", None)
    return ConversationHandler.END

async def cancel_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Action cancelled.")
    return ConversationHandler.END

# --- বটের তালিকা ও কন্ট্রোল বোর্ড (নিখুঁত আপটাইম সহ) ---
async def mybots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    if not await check_guard_and_respond(update, context):
        return

    user = update.effective_user
    projects = get_user_projects(user.id)

    if not projects:
        text = "You have no bots hosted. Click <b>➕ Create Bot</b> to deploy one."
        if query:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return

    text = "<b>Select a bot to manage:</b>"
    markup = my_bots_keyboard(projects)
    if query:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)

async def render_bot_details(query, bot_id: str, user_id: int):
    config = load_config()
    proj = get_project(bot_id)
    if not proj or (proj["user_id"] != user_id and user_id not in config["admin_ids"]):
        await query.edit_message_text("Bot not found or access denied.")
        return

    is_live = pm.is_running(bot_id)
    real_status = "RUNNING" if is_live else proj["status"]

    # সুন্দর ও নির্ভুল আপটাইম ফরম্যাটিং (দিন, ঘণ্টা, মিনিট, সেকেন্ড)
    uptime_str = "Offline"
    if is_live and proj["uptime_start"]:
        uptime_sec = int(time.time() - proj["uptime_start"])
        days = uptime_sec // 86400
        hours = (uptime_sec % 86400) // 3600
        minutes = (uptime_sec % 3600) // 60
        seconds = uptime_sec % 60
        
        if days > 0:
            uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
        elif hours > 0:
            uptime_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            uptime_str = f"{minutes}m {seconds}s"
        else:
            uptime_str = f"{seconds}s"

    text = (
        f"<b>Project: {proj['project_name']}</b>\n"
        f"• Status: <b>{real_status}</b>\n"
        f"• Entry File: <code>{proj['main_file']}</code>\n"
        f"• PID: <code>{proj['pid'] if is_live else 0}</code>\n"
        f"• Uptime: <b>{uptime_str}</b>\n"
        f"• Restarts: <b>{proj['restart_count']}</b>\n"
    )
    if proj["last_error"]:
        text += f"\nLast Error: <code>{proj['last_error'][:150]}</code>\n"

    try:
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=bot_control_keyboard(bot_id, real_status)
        )
    except Exception:
        pass

async def bot_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_id = query.data.replace("bot_manage_", "")
    await render_bot_details(query, bot_id, query.from_user.id)

async def bot_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = query.from_user
    config = load_config()

    action, bot_id = data.split("_")[1], data.split("_")[2]
    proj = get_project(bot_id)
    if not proj or (proj["user_id"] != user.id and user.id not in config["admin_ids"]):
        await query.answer("Unauthorized action.", show_alert=True)
        return

    if action == "start":
        ok, msg = pm.start_bot(bot_id)
        toast = "Bot started!" if ok else f"Failed: {msg}"
        await query.answer(toast)
        await render_bot_details(query, bot_id, user.id)
    elif action == "stop":
        ok, msg = pm.stop_bot(bot_id)
        toast = "Bot stopped!" if ok else f"Failed: {msg}"
        await query.answer(toast)
        await render_bot_details(query, bot_id, user.id)
    elif action == "restart":
        ok, msg = pm.restart_bot(bot_id)
        toast = "Bot restarted!" if ok else f"Failed: {msg}"
        await query.answer(toast)
        await render_bot_details(query, bot_id, user.id)
    elif action == "logs":
        await query.answer()
        log_path = pm.get_log_path(bot_id)
        if not os.path.exists(log_path):
            await query.message.reply_text("No logs recorded yet.")
        else:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-40:]
            chunk = "".join(lines).strip()
            if not chunk:
                chunk = "Log file is empty."
            await query.message.reply_text(f"<b>Recent Logs:</b>\n<pre>{chunk[-3500:]}</pre>", parse_mode=ParseMode.HTML)
    elif action == "clearlogs":
        log_path = pm.get_log_path(bot_id)
        if os.path.exists(log_path):
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"--- Cleared at {time.ctime()} ---\n")
        await query.answer("Logs cleared!")
    elif action == "backup":
        await query.answer("Creating backup...")
        zip_path = os.path.join(load_config()["storage_root"], "backups", f"{proj['project_name']}_{bot_id}.zip")
        shutil.make_archive(zip_path.replace(".zip", ""), 'zip', proj["project_dir"])
        await context.bot.send_document(chat_id=user.id, document=open(zip_path, 'rb'), caption=f"Backup: {proj['project_name']}")
    elif action == "delconf":
        pm.stop_bot(bot_id)
        if os.path.exists(proj["project_dir"]):
            shutil.rmtree(proj["project_dir"], ignore_errors=True)
        delete_project_record(bot_id)
        await query.answer("Bot deleted!")
        await query.edit_message_text(f"Project <b>{proj['project_name']}</b> deleted successfully.", parse_mode=ParseMode.HTML)

async def close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()