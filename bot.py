#
# --- DIAGNOSTIC CODE - DO NOT USE FOR PRODUCTION ---
#
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configuration ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PRIVATE_CHANNEL_ID = os.environ.get("PRIVATE_CHANNEL_ID") 

# --- Logging Setup ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- A simple start command to prove the bot is running ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Diagnostic Bot is running. Ready for channel test.")

# --- THE MOST IMPORTANT PART ---
# This function will only try to reply in the channel when it sees a new post.
async def channel_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Check if the update is a channel post and if the ID matches
    if not update.channel_post or str(update.channel_post.chat.id) != PRIVATE_CHANNEL_ID:
        logger.warning(f"Received a post from an unexpected channel: {update.channel_post.chat.id if update.channel_post else 'N/A'}")
        return

    chat_id = update.channel_post.chat.id
    message_id = update.channel_post.message_id
    
    logger.info(f"SUCCESS! I received message {message_id} from channel {chat_id}.")
    
    # Try to reply to the post. This is the ultimate test.
    try:
        reply_text = f"✅ I can see this message!\nMy Channel ID is: `{chat_id}`"
        await context.bot.send_message(chat_id=chat_id, text=reply_text, reply_to_message_id=message_id, parse_mode='Markdown')
        logger.info("Successfully replied in the channel.")
    except Exception as e:
        logger.error(f"I received the message, but FAILED TO REPLY. Error: {e}")

# --- Main function to run the bot ---
def main() -> None:
    if not TELEGRAM_TOKEN or not PRIVATE_CHANNEL_ID:
        logger.error("Missing TELEGRAM_TOKEN or PRIVATE_CHANNEL_ID in environment variables!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add only the necessary handlers for this test
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, channel_test))

    # Webhook setup
    PORT = int(os.environ.get('PORT', 8443))
    APP_NAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if not APP_NAME:
        logger.error("RENDER_EXTERNAL_HOSTNAME not set!")
        return
    
    application.run_webhook(listen="0.0.0.0", port=PORT, url_path=TELEGRAM_TOKEN, webhook_url=f"https://{APP_NAME}/{TELEGRAM_TOKEN}")
    logger.info("Diagnostic bot started and webhook is set.")

if __name__ == '__main__':
    main()
