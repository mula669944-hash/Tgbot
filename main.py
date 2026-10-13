import asyncio
import logging

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

import telegram.ext._updater
import telegram.ext._applicationbuilder

class PatchedUpdater(telegram.ext._updater.Updater):
    pass

telegram.ext._updater.Updater = PatchedUpdater
telegram.ext._applicationbuilder.Updater = PatchedUpdater
if hasattr(telegram.ext, "Updater"):
    telegram.ext.Updater = PatchedUpdater

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters
)
from core.database import init_db
from core.utils import ensure_directories, load_config
from core.process_manager import pm
from handlers.user_handlers import (
    start_command, id_command, status_command, mybots_command,
    account_command, help_command, buy_premium_menu, plan_select_callback,
    payment_method_callback, handle_trx_id, verify_membership_callback,
    bot_detail_callback, bot_action_callback,
    start_wizard_message, handle_uploaded_file, handle_project_name,
    cancel_wizard, close_callback, AWAITING_FILE, ENTERING_NAME, AWAITING_TRX_ID
)
from handlers.admin_handlers import (
    admin_dashboard_callback, admin_users_callback, admin_allbots_callback,
    admin_sys_status_callback, admin_toggle_maint_callback,
    admin_channel_manage_callback, admin_channel_toggle_callback,
    admin_channel_add_prompt, admin_channel_save, admin_channel_remove_list,
    admin_channel_delete_confirm, admin_payment_settings_callback,
    admin_plan_settings_callback, admin_edit_setting_prompt, admin_edit_setting_save,
    admin_payment_decision_callback, admin_broadcast_info_callback, admin_broadcast_command,
    ADM_AWAIT_CH_DETAILS, ADM_AWAIT_SETTING_VAL
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("TelegramBotHost")

async def post_init(application):
    ensure_directories()
    init_db()
    asyncio.create_task(pm.supervisor_loop())
    logger.info("Process Supervisor running.")

def main():
    config = load_config()
    token = config.get("bot_token")
    if not token:
        print("ERROR: bot_token is empty in config.json")
        return

    app = ApplicationBuilder().token(token).job_queue(None).post_init(post_init).build()

    # ১. Upload Wizard
    upload_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^➕ Create Bot$"), start_wizard_message),
            CommandHandler("create", start_wizard_message)
        ],
        states={
            AWAITING_FILE: [MessageHandler(filters.Document.ALL, handle_uploaded_file)],
            ENTERING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_project_name)]
        },
        fallbacks=[CommandHandler("cancel", cancel_wizard)],
        per_chat=True,
        per_user=True
    )

    # ২. User Payment TrxID Wizard
    payment_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(payment_method_callback, pattern="^paym_")],
        states={AWAITING_TRX_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_trx_id)]},
        fallbacks=[CommandHandler("cancel", cancel_wizard)],
        per_chat=True,
        per_user=True
    )

    # ৩. Admin Channel Add Wizard
    admin_ch_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_channel_add_prompt, pattern="^adm_ch_add$")],
        states={ADM_AWAIT_CH_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_channel_save)]},
        fallbacks=[CommandHandler("cancel", cancel_wizard)],
        per_chat=True,
        per_user=True
    )

    # ৪. Admin Setting Edit Wizard (bKash/Nagad/Price)
    admin_setting_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_edit_setting_prompt, pattern="^adm_edit_")],
        states={ADM_AWAIT_SETTING_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_setting_save)]},
        fallbacks=[CommandHandler("cancel", cancel_wizard)],
        per_chat=True,
        per_user=True
    )

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("id", id_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("mybots", mybots_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("broadcast", admin_broadcast_command))

    # Converstations
    app.add_handler(upload_conv)
    app.add_handler(payment_conv)
    app.add_handler(admin_ch_conv)
    app.add_handler(admin_setting_conv)

    # Reply Menu Buttons
    app.add_handler(MessageHandler(filters.Regex("^📂 My Bots$"), mybots_command))
    app.add_handler(MessageHandler(filters.Regex("^💎 Buy Premium$"), buy_premium_menu))
    app.add_handler(MessageHandler(filters.Regex("^⚡ Hosting Status$"), status_command))
    app.add_handler(MessageHandler(filters.Regex("^👤 Account Info$"), account_command))
    app.add_handler(MessageHandler(filters.Regex("^❓ Help & Support$"), help_command))
    app.add_handler(MessageHandler(filters.Regex("^⚙️ Admin Panel$"), admin_dashboard_callback))

    # User Callbacks
    app.add_handler(CallbackQueryHandler(verify_membership_callback, pattern="^verify_membership$"))
    app.add_handler(CallbackQueryHandler(buy_premium_menu, pattern="^buy_premium_start$"))
    app.add_handler(CallbackQueryHandler(plan_select_callback, pattern="^buyplan_"))
    app.add_handler(CallbackQueryHandler(mybots_command, pattern="^menu_mybots_inline$"))
    app.add_handler(CallbackQueryHandler(close_callback, pattern="^menu_close$"))
    app.add_handler(CallbackQueryHandler(bot_detail_callback, pattern="^bot_manage_"))
    app.add_handler(CallbackQueryHandler(bot_action_callback, pattern="^act_"))

    # Admin Panel Callbacks
    app.add_handler(CallbackQueryHandler(admin_dashboard_callback, pattern="^admin_dashboard$"))
    app.add_handler(CallbackQueryHandler(admin_channel_manage_callback, pattern="^adm_ch_manage$"))
    app.add_handler(CallbackQueryHandler(admin_channel_toggle_callback, pattern="^adm_ch_toggle$"))
    app.add_handler(CallbackQueryHandler(admin_channel_remove_list, pattern="^adm_ch_rem_list$"))
    app.add_handler(CallbackQueryHandler(admin_channel_delete_confirm, pattern="^adm_ch_del_"))
    
    app.add_handler(CallbackQueryHandler(admin_payment_settings_callback, pattern="^adm_pay_settings$"))
    app.add_handler(CallbackQueryHandler(admin_plan_settings_callback, pattern="^adm_plan_settings$"))
    app.add_handler(CallbackQueryHandler(admin_payment_decision_callback, pattern="^adm_pay_"))
    
    app.add_handler(CallbackQueryHandler(admin_users_callback, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_allbots_callback, pattern="^admin_allbots$"))
    app.add_handler(CallbackQueryHandler(admin_sys_status_callback, pattern="^admin_sys_status$"))
    app.add_handler(CallbackQueryHandler(admin_toggle_maint_callback, pattern="^admin_toggle_maint$"))
    app.add_handler(CallbackQueryHandler(admin_broadcast_info_callback, pattern="^admin_broadcast_info$"))

    logger.info("Bot hoster online.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()