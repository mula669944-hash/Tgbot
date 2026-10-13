from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from typing import List, Dict, Any
from core.database import get_setting

# --- নিচের স্থায়ী মেনু বাটন (Reply Keyboard) ---
def main_reply_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("➕ Create Bot"), KeyboardButton("📂 My Bots")],
        [KeyboardButton("💎 Buy Premium"), KeyboardButton("⚡ Hosting Status")],
        [KeyboardButton("👤 Account Info"), KeyboardButton("❓ Help & Support")]
    ]
    if is_admin:
        keyboard.append([KeyboardButton("⚙️ Admin Panel")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- ক্লিন ও প্রফেশনাল চ্যানেল গার্ড কিবোর্ড (সবগুলো চ্যানেল সিরিয়াল অনুযায়ী দেখাবে) ---
def channel_guard_keyboard(channels: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons = []
    for idx, ch in enumerate(channels, 1):
        url = ch.get("invite_url") or "https://t.me"
        btn_text = f"Join {idx}: {ch['display_name']}"
        buttons.append([InlineKeyboardButton(btn_text, url=url)])

    # ভেরিফিকেশন বাটন
    buttons.append([InlineKeyboardButton("🔄 Verify Membership", callback_data="verify_membership")])
    return InlineKeyboardMarkup(buttons)

# --- প্রিমিয়াম প্ল্যান কিবোর্ড ---
def premium_plans_keyboard() -> InlineKeyboardMarkup:
    s_p = get_setting("plan_starter_price", "50 BDT")
    s_b = get_setting("plan_starter_bots", "2")
    p_p = get_setting("plan_pro_price", "100 BDT")
    p_b = get_setting("plan_pro_bots", "5")
    u_p = get_setting("plan_ultra_price", "200 BDT")
    u_b = get_setting("plan_ultra_bots", "12")

    buttons = [
        [InlineKeyboardButton(f"Starter (+{s_b} Bots) — {s_p}", callback_data="buyplan_starter")],
        [InlineKeyboardButton(f"Pro (+{p_b} Bots) — {p_p}", callback_data="buyplan_pro")],
        [InlineKeyboardButton(f"Ultra (+{u_b} Bots) — {u_p}", callback_data="buyplan_ultra")],
        [InlineKeyboardButton("Cancel", callback_data="menu_close")]
    ]
    return InlineKeyboardMarkup(buttons)

# --- পেমেন্ট মেথড নির্বাচন কিবোর্ড ---
def payment_methods_keyboard(plan_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("bKash (Personal)", callback_data=f"paym_bkash_{plan_code}")],
        [InlineKeyboardButton("Nagad (Personal)", callback_data=f"paym_nagad_{plan_code}")],
        [InlineKeyboardButton("Rocket", callback_data=f"paym_rocket_{plan_code}")],
        [InlineKeyboardButton("Binance / USDT", callback_data=f"paym_crypto_{plan_code}")],
        [InlineKeyboardButton("Back to Plans", callback_data="buy_premium_start")]
    ])

# --- অ্যাডমিন পেমেন্ট সিদ্ধান্ত বাটন ---
def admin_payment_decision_keyboard(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Approve", callback_data=f"adm_pay_appr_{request_id}"),
            InlineKeyboardButton("Reject", callback_data=f"adm_pay_rejc_{request_id}")
        ]
    ])

# --- হোস্ট করা বটের তালিকা ---
def my_bots_keyboard(bots: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    keyboard = []
    for b in bots:
        st_icon = "🟢" if b["status"] == "RUNNING" else ("🔴" if b["status"] == "STOPPED" else "⚠️")
        btn_text = f"{st_icon} {b['project_name']} [{b['status']}]"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"bot_manage_{b['bot_id']}")])
    keyboard.append([InlineKeyboardButton("Close", callback_data="menu_close")])
    return InlineKeyboardMarkup(keyboard)

# --- নির্দিষ্ট বট কন্ট্রোল করার কিবোর্ড ---
def bot_control_keyboard(bot_id: str, status: str) -> InlineKeyboardMarkup:
    buttons = []
    if status == "RUNNING":
        buttons.append([
            InlineKeyboardButton("Stop Bot", callback_data=f"act_stop_{bot_id}"),
            InlineKeyboardButton("Restart Bot", callback_data=f"act_restart_{bot_id}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton("Start Bot", callback_data=f"act_start_{bot_id}"),
            InlineKeyboardButton("Restart Bot", callback_data=f"act_restart_{bot_id}")
        ])
    buttons.append([
        InlineKeyboardButton("View Logs", callback_data=f"act_logs_{bot_id}"),
        InlineKeyboardButton("Clear Logs", callback_data=f"act_clearlogs_{bot_id}")
    ])
    buttons.append([
        InlineKeyboardButton("Backup Project", callback_data=f"act_backup_{bot_id}"),
        InlineKeyboardButton("Delete Bot", callback_data=f"act_delconf_{bot_id}")
    ])
    buttons.append([InlineKeyboardButton("Back to List", callback_data="menu_mybots_inline")])
    return InlineKeyboardMarkup(buttons)

# --- অ্যাডমিন ড্যাশবোর্ড কিবোর্ড ---
def admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Channel Guard Settings", callback_data="adm_ch_manage"),
            InlineKeyboardButton("Payment & Numbers", callback_data="adm_pay_settings")
        ],
        [
            InlineKeyboardButton("Plan & Price Settings", callback_data="adm_plan_settings"),
            InlineKeyboardButton("Users List", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton("All Hosted Bots", callback_data="admin_allbots"),
            InlineKeyboardButton("Broadcast Message", callback_data="admin_broadcast_info")
        ],
        [
            InlineKeyboardButton("System Diagnostics", callback_data="admin_sys_status"),
            InlineKeyboardButton("Maintenance Mode", callback_data="admin_toggle_maint")
        ],
        [InlineKeyboardButton("Close Panel", callback_data="menu_close")]
    ])