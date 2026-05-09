from master_bot import build_app
from telegram import Update

if __name__ == "__main__":
    application = build_app()
    application.run_polling(allowed_updates=Update.ALL_TYPES)
