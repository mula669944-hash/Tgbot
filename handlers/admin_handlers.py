import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler
from core.database import (
    get_all_users, get_all_projects, get_setting, set_setting,
    get_channels, add_channel, remove_channel,
    get_payment_request, update_payment_status, add_user_limit, get_user
)
from core.keyboards import admin_dashboard_keyboard
from core.process_manager import pm
from core.utils import load_config, get_system_metrics

ADM_AWAIT_CH_DETAILS = 20
ADM_AWAIT_SETTING_VAL = 21

async def admin_dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user = query.from_user
    else:
        user = update.effective_user

    config = load_config()
    if user.id not in config["admin_ids"]:
        if query:
            await query.edit_message_text("❌ Unauthorized access.")
        return

    users = get_all_users()
    projects = get_all_projects()
    running_bots = sum(1 for p in projects if pm.is_running(p["bot_id"]))
    guard_active = "ON 🟢" if get_setting("channel_protection") == "1" else "OFF 🔴"

    msg = (
        "⚙️ <b>Admin Control Dashboard</b>\n\n"
        f"• Total Users: <b>{len(users)}</b>\n"
        f"• Total Hosted Bots: <b>{len(projects)}</b> (Running: <b>{running_bots} 🟢</b>)\n"
        f"• Channel Guard: <b>{guard_active}</b>\n\n"
        "নিচের বাটনগুলো দিয়ে চ্যানেল, পেমেন্ট নম্বর ও প্যাকেজের মূল্য পরিবর্তন করুন:"
    )
    if query:
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=admin_dashboard_keyboard())
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=admin_dashboard_keyboard())

# --- চ্যানেল গার্ড ডায়নামিক ম্যানেজমেন্ট UI ---
async def admin_channel_manage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    channels = get_channels()
    status = "ON 🟢" if get_setting("channel_protection") == "1" else "OFF 🔴"

    text = f"🛡️ <b>Channel Guard Settings</b> (Status: <b>{status}</b>)\n\n<b>বর্তমান প্রয়োজনীয় চ্যানেলসমূহ:</b>\n"
    if not channels:
        text += "<i>কোনো চ্যানেল সেট করা নেই।</i>\n"
    else:
        for idx, ch in enumerate(channels, 1):
            text += f"{idx}. <b>{ch['display_name']}</b> (<code>{ch['channel_id']}</code>)\n   🔗 {ch['invite_url']}\n"

    buttons = [
        [
            InlineKeyboardButton("➕ Add Channel", callback_data="adm_ch_add"),
            InlineKeyboardButton("🗑️ Remove Channel", callback_data="adm_ch_rem_list")
        ],
        [
            InlineKeyboardButton("🔄 Toggle Guard (ON/OFF)", callback_data="adm_ch_toggle")
        ],
        [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_dashboard")]
    ]
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))

async def admin_channel_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    curr = get_setting("channel_protection", "1")
    new_val = "0" if curr == "1" else "1"
    set_setting("channel_protection", new_val)
    await admin_channel_manage_callback(update, context)

async def admin_channel_add_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "➕ <b>নতুন চ্যানেল যুক্ত করুন</b>\n\n"
        "একটি মেসেজে নিচের ফরমেটে তথ্য পাঠান:\n"
        "<code>Channel_ID | Channel Name | Invite Link</code>\n\n"
        "<b>উদাহরণ:</b>\n"
        "<code>@mychannel | My Updates | https://t.me/mychannel</code>\n\n"
        "<i>Cancel করতে /cancel লিখুন।</i>",
        parse_mode=ParseMode.HTML
    )
    return ADM_AWAIT_CH_DETAILS

async def admin_channel_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 3:
        await update.message.reply_text("❌ ফরম্যাট সঠিক হয়নি! <code>ID | Name | Link</code> এভাবে পাঠান:")
        return ADM_AWAIT_CH_DETAILS

    add_channel(parts[0], parts[1], parts[2])
    await update.message.reply_text(f"✅ চ্যানেল <b>{parts[1]}</b> সফলভাবে যুক্ত হয়েছে!", parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def admin_channel_remove_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    channels = get_channels()
    if not channels:
        await query.answer("কোনো চ্যানেল নেই!", show_alert=True)
        return

    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(f"❌ Delete {ch['display_name']}", callback_data=f"adm_ch_del_{ch['channel_id']}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="adm_ch_manage")])

    await query.edit_message_text("🗑️ যে চ্যানেলটি ডিলিট করতে চান সেটিতে ক্লিক করুন:", reply_markup=InlineKeyboardMarkup(buttons))

async def admin_channel_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ch_id = query.data.replace("adm_ch_del_", "")
    remove_channel(ch_id)
    await query.answer("চ্যানেল ডিলিট করা হয়েছে!", show_alert=True)
    await admin_channel_manage_callback(update, context)

# --- পেমেন্ট নম্বর এডিট প্যানেল ---
async def admin_payment_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    bkash = get_setting("pay_bkash")
    nagad = get_setting("pay_nagad")
    rocket = get_setting("pay_rocket")
    crypto = get_setting("pay_crypto")

    text = (
        "💳 <b>পেমেন্ট নম্বর সেটিংস</b>\n\n"
        f"• <b>bKash:</b> <code>{bkash}</code>\n"
        f"• <b>Nagad:</b> <code>{nagad}</code>\n"
        f"• <b>Rocket:</b> <code>{rocket}</code>\n"
        f"• <b>Crypto:</b> <code>{crypto}</code>\n\n"
        "যেটি পরিবর্তন করতে চান নিচের বাটনে ক্লিক করুন:"
    )
    buttons = [
        [
            InlineKeyboardButton("✏️ Edit bKash", callback_data="adm_edit_pay_bkash"),
            InlineKeyboardButton("✏️ Edit Nagad", callback_data="adm_edit_pay_nagad")
        ],
        [
            InlineKeyboardButton("✏️ Edit Rocket", callback_data="adm_edit_pay_rocket"),
            InlineKeyboardButton("✏️ Edit Crypto", callback_data="adm_edit_pay_crypto")
        ],
        [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_dashboard")]
    ]
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))

# --- প্যাকেজ ও মূল্য সেটিংস প্যানেল ---
async def admin_plan_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    s_p = get_setting("plan_starter_price")
    s_b = get_setting("plan_starter_bots")
    p_p = get_setting("plan_pro_price")
    p_b = get_setting("plan_pro_bots")
    u_p = get_setting("plan_ultra_price")
    u_b = get_setting("plan_ultra_bots")

    text = (
        "📦 <b>প্রিমিয়াম প্যাকেজ সেটিংস</b>\n\n"
        f"⭐ <b>Starter:</b> +{s_b} Bots | Price: <b>{s_p}</b>\n"
        f"🚀 <b>Pro:</b> +{p_b} Bots | Price: <b>{p_p}</b>\n"
        f"👑 <b>Ultra:</b> +{u_b} Bots | Price: <b>{u_p}</b>\n\n"
        "যে প্যাকেজের মূল্য পরিবর্তন করতে চান সিলেক্ট করুন:"
    )
    buttons = [
        [InlineKeyboardButton("✏️ Edit Starter Price", callback_data="adm_edit_plan_starter_price")],
        [InlineKeyboardButton("✏️ Edit Pro Price", callback_data="adm_edit_plan_pro_price")],
        [InlineKeyboardButton("✏️ Edit Ultra Price", callback_data="adm_edit_plan_ultra_price")],
        [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_dashboard")]
    ]
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))

async def admin_edit_setting_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    setting_key = query.data.replace("adm_edit_", "")
    context.user_data["editing_setting_key"] = setting_key

    await query.edit_message_text(
        f"✏️ <b>{setting_key}</b> এর নতুন মান/নম্বর লিখে পাঠান:\n\n"
        "<i>Cancel করতে /cancel লিখুন।</i>",
        parse_mode=ParseMode.HTML
    )
    return ADM_AWAIT_SETTING_VAL

async def admin_edit_setting_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    key = context.user_data.get("editing_setting_key")
    if key:
        set_setting(key, val)
        await update.message.reply_text(f"✅ <b>{key}</b> সফলভাবে আপডেট করা হয়েছে!", parse_mode=ParseMode.HTML)
    context.user_data.pop("editing_setting_key", None)
    return ConversationHandler.END

# --- পেমেন্ট অনুমোদন ---
async def admin_payment_decision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in load_config()["admin_ids"]:
        return

    data = query.data
    action = "APPROVE" if "appr" in data else "REJECT"
    req_id = int(data.split("_")[-1])

    req = get_payment_request(req_id)
    if not req or req["status"] != "PENDING":
        await query.edit_message_text("⚠️ This request has already been processed.")
        return

    target_user_id = req["user_id"]

    if action == "APPROVE":
        update_payment_status(req_id, "APPROVED")
        add_user_limit(target_user_id, req["extra_bots"])
        updated_user = get_user(target_user_id)

        await query.edit_message_text(
            f"✅ <b>Payment Approved!</b>\n"
            f"User <code>{target_user_id}</code> got <b>+{req['extra_bots']} Bots</b>.\n"
            f"Total Limit: <b>{updated_user['bot_limit']} Bots</b>.",
            parse_mode=ParseMode.HTML
        )

        try:
            user_msg = (
                "🎉 <b>পেমেন্ট অনুমোদিত হয়েছে!</b>\n\n"
                f"আপনার <b>{req['plan_name']}</b> পেমেন্ট ভেরিফাই হয়েছে।\n"
                f"• যুক্ত হওয়া বট স্লট: <b>+{req['extra_bots']}টি</b>\n"
                f"• বর্তমান মোট লিমিট: <b>{updated_user['bot_limit']}টি বট</b>\n\n"
                "এখন আপনি নতুন বট হোস্ট করতে পারেন!"
            )
            await context.bot.send_message(chat_id=target_user_id, text=user_msg, parse_mode=ParseMode.HTML)
        except Exception:
            pass
    else:
        update_payment_status(req_id, "REJECTED")
        await query.edit_message_text(f"❌ Payment request #{req_id} rejected.", parse_mode=ParseMode.HTML)
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="❌ <b>পেমেন্ট রিজেক্ট হয়েছে!</b> আপনার Transaction ID সঠিক নয়।",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

# --- অন্যান্য অ্যাডমিন ফিচার ---
async def admin_allbots_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    projects = get_all_projects()
    if not projects:
        await query.edit_message_text("🤖 সার্ভারে কোনো বট নেই।", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_dashboard")]]))
        return

    text = f"🤖 <b>All Hosted Bots ({len(projects)}):</b>\n\n"
    buttons = []
    for p in projects:
        is_live = pm.is_running(p["bot_id"])
        st_icon = "🟢" if is_live else "🔴"
        buttons.append([InlineKeyboardButton(f"{st_icon} {p['project_name']} (User: {p['user_id']})", callback_data=f"bot_manage_{p['bot_id']}")])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin_dashboard")])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))

async def admin_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    users = get_all_users()
    text = f"👥 <b>Users ({len(users)}):</b>\n\n"
    for u in users[-20:]:
        text += f"• <b>{u.get('first_name', 'User')}</b> (<code>{u['user_id']}</code>) | Quota: <b>{u['bot_limit']} Bots</b>\n"

    buttons = [[InlineKeyboardButton("🔙 Back", callback_data="admin_dashboard")]]
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))

async def admin_sys_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    metrics = get_system_metrics()
    text = (
        "📊 <b>System Diagnostics:</b>\n\n"
        f"• CPU: <b>{metrics['cpu_usage']}</b>\n"
        f"• RAM: <b>{metrics['mem_used']} / {metrics['mem_total']}</b>\n"
        f"• Disk: <b>{metrics['disk_free']} free</b>\n"
    )
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_dashboard")]]))

async def admin_toggle_maint_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    curr = get_setting("maintenance_mode", "0")
    new_val = "0" if curr == "1" else "1"
    set_setting("maintenance_mode", new_val)
    await admin_dashboard_callback(update, context)

async def admin_broadcast_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📢 <b>Broadcast Message:</b>\nমেসেজ পাঠাতে লিখুন:\n<code>/broadcast Your message</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_dashboard")]])
    )

async def admin_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in load_config()["admin_ids"]:
        return
    msg = " ".join(context.args)
    if not msg:
        return
    users = get_all_users()
    sent = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u["user_id"], text=f"📢 <b>Announcement:</b>\n\n{msg}", parse_mode=ParseMode.HTML)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await update.message.reply_text(f"✅ Delivered to {sent} users.")