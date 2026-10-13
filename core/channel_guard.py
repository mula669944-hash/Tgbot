import logging
from telegram import Bot
from telegram.error import TelegramError
from core.database import get_channels, get_setting

logger = logging.getLogger(__name__)

async def check_user_membership(bot: Bot, user_id: int) -> tuple:
    """
    Returns (True, []) if user joined all channels or protection is OFF.
    Returns (False, all_channels) if user is missing any channel.
    """
    protection_enabled = get_setting("channel_protection", "1")
    if protection_enabled != "1":
        return True, []

    channels = get_channels(enabled_only=True)
    if not channels:
        return True, []

    all_joined = True
    for ch in channels:
        target_id = ch["channel_id"]
        try:
            member = await bot.get_chat_member(chat_id=target_id, user_id=user_id)
            if member.status not in ["creator", "administrator", "member", "restricted"]:
                all_joined = False
                break
        except Exception as e:
            logger.warning(f"Error checking channel {target_id}: {e}")
            all_joined = False
            break

    if all_joined:
        return True, []

    # সব চ্যানেলে জয়েন না থাকলে অ্যাডমিন প্যানেলের সবগুলো চ্যানেল বাটনে প্রদর্শন করবে
    return False, channels