import requests
from django.conf import settings
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def send_to_telegram(message: str, chat_id: Optional[str] = None) -> bool:
    """
    Telegram kanaliga xabar yuborish.
    Args:
        message: Yuboriladigan xabar matni (HTML formatida).
        chat_id: Telegram kanali ID (agar berilmasa, settings dan olinadi).
    Returns:
        bool: Yuborish muvaffaqiyatli bo‘lsa True, aks holda False.
    """
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
    default_chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', None)

    if not bot_token or not (chat_id or default_chat_id):
        logger.error("Telegram sozlamalari topilmadi: bot_token yoki chat_id yo‘q")
        return False

    chat_id = chat_id or default_chat_id
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }

    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Xabar Telegramga yuborildi: {chat_id}")
        return True
    except requests.RequestException as e:
        logger.error(
            f"Telegramga xabar yuborishda xato: {e}, response: {response.text if 'response' in locals() else 'yo‘q'}")
        return False


def send_file_to_telegram(file_path: str, original_filename: str, caption: str, chat_id: Optional[str] = None) -> bool:
    """
    Telegram kanaliga fayl yuborish, asl nom va format bilan.
    Args:
        file_path: Faylning serverdagi yo‘li.
        original_filename: Faylning asl nomi.
        caption: Fayl bilan birga yuboriladigan izoh (HTML formatida).
        chat_id: Telegram kanali ID (agar berilmasa, settings dan olinadi).
    Returns:
        bool: Yuborish muvaffaqiyatli bo‘lsa True, aks holda False.
    """
    if not os.path.exists(file_path):
        logger.error(f"Fayl topilmadi: {file_path}")
        return False

    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
    default_chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', None)

    if not bot_token or not (chat_id or default_chat_id):
        logger.error("Telegram sozlamalari topilmadi: bot_token yoki chat_id yo‘q")
        return False

    chat_id = chat_id or default_chat_id
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    try:
        with open(file_path, 'rb') as file:
            files = {'document': (original_filename, file)}
            payload = {
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, data=payload, files=files, timeout=10)
            response.raise_for_status()
            logger.info(f"Fayl Telegramga yuborildi: {original_filename} -> {chat_id}")
            return True
    except requests.RequestException as e:
        logger.error(f"Fayl yuborishda xato: {e}, response: {response.text if 'response' in locals() else 'yo‘q'}")
        return False