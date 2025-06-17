import requests
from django.conf import settings
import os
import logging

logger = logging.getLogger(__name__)


def send_to_telegram(message, chat_id=None):
    """Telegram kanaliga xabar yuborish."""
    if not hasattr(settings, 'TELEGRAM_BOT_TOKEN') or not hasattr(settings, 'TELEGRAM_CHAT_ID'):
        logger.error("Telegram sozlamalari topilmadi!")
        return False

    bot_token = settings.TELEGRAM_BOT_TOKEN
    chat_id = chat_id or settings.TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'  # Xabarni HTML formatida chiroyli ko‘rsatish
    }

    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            logger.info("Xabar Telegramga muvaffaqiyatli yuborildi!")
            return True
        else:
            logger.error(f"Xabar yuborishda xato: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Telegramga xabar yuborishda xato: {e}")
        return False


def send_file_to_telegram(file_path, original_filename, caption, chat_id=None):
    """Telegram kanaliga fayl yuborish, asl nom va format bilan."""
    if not os.path.exists(file_path):
        logger.error(f"Fayl topilmadi: {file_path}")
        return False

    if not hasattr(settings, 'TELEGRAM_BOT_TOKEN') or not hasattr(settings, 'TELEGRAM_CHAT_ID'):
        logger.error("Telegram sozlamalari topilmadi!")
        return False

    bot_token = settings.TELEGRAM_BOT_TOKEN
    chat_id = chat_id or settings.TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    try:
        with open(file_path, 'rb') as file:
            files = {'document': (original_filename, file)}  # Asl fayl nomini ishlatish
            payload = {
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, data=payload, files=files)
            if response.status_code == 200:
                logger.info(f"Fayl Telegramga muvaffaqiyatli yuborildi: {original_filename}")
                return True
            else:
                logger.error(f"Fayl yuborishda xato: {response.text}")
                return False
    except Exception as e:
        logger.error(f"Fayl yuborishda xato: {e}")
        return False