"""
Патчи поведения python-telegram-bot.

Telegram отвечает ошибкой "Message is not modified" (BadRequest), если
edit_message_text/edit_message_reply_markup вызван с текстом и клавиатурой,
которые уже стоят в сообщении (типичный случай — кнопка "Обновить"/"Обновити",
когда данные не изменились с прошлого раза). Это не сбой, а ожидаемая ситуация,
поэтому вместо try/except в каждом из десятков хендлеров патчим сам Bot один раз.
"""
from telegram import Bot
from telegram.error import BadRequest

_original_edit_message_text = Bot.edit_message_text
_original_edit_message_reply_markup = Bot.edit_message_reply_markup


async def _safe_edit_message_text(self, *args, **kwargs):
    try:
        return await _original_edit_message_text(self, *args, **kwargs)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return None
        raise


async def _safe_edit_message_reply_markup(self, *args, **kwargs):
    try:
        return await _original_edit_message_reply_markup(self, *args, **kwargs)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return None
        raise


def apply_patches():
    Bot.edit_message_text = _safe_edit_message_text
    Bot.edit_message_reply_markup = _safe_edit_message_reply_markup
