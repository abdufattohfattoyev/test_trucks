import requests
from django.conf import settings
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def send_to_telegram(message: str, chat_id: Optional[str] = None) -> bool:
    """
    Send a message to a Telegram channel.
    Args:
        message: The message text to send (HTML format).
        chat_id: Telegram channel ID (if not provided, taken from settings).
    Returns:
        bool: True if successful, False otherwise.
    """
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
    default_chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', None)

    if not bot_token or not (chat_id or default_chat_id):
        logger.error("Telegram settings not found: bot_token or chat_id missing")
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
        logger.info(f"Message sent to Telegram: {chat_id}")
        return True
    except requests.RequestException as e:
        logger.error(
            f"Error sending message to Telegram: {e}, response: {response.text if 'response' in locals() else 'none'}")
        return False


def send_file_to_telegram(file_path: str, original_filename: str, caption: str, chat_id: Optional[str] = None) -> bool:
    """
    Send a file to a Telegram channel with its original name and format.
    Args:
        file_path: The file's path on the server.
        original_filename: The original name of the file.
        caption: Caption to send with the file (HTML format).
        chat_id: Telegram channel ID (if not provided, taken from settings).
    Returns:
        bool: True if successful, False otherwise.
    """
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return False

    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
    default_chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', None)

    if not bot_token or not (chat_id or default_chat_id):
        logger.error("Telegram settings not found: bot_token or chat_id missing")
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
            logger.info(f"File sent to Telegram: {original_filename} -> {chat_id}")
            return True
    except requests.RequestException as e:
        logger.error(
            f"Error sending file to Telegram: {e}, response: {response.text if 'response' in locals() else 'none'}")
        return False