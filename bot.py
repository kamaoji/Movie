# bot.py (Updated for python-telegram-bot v21+)

import os
import logging
import requests 
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configuration ---
# These are loaded from Render's Environment Variables
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OMDB_API_KEY = os.environ.get("OMDB_API_KEY")

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING) # Quiets the noisy httpx logger
logger = logging.getLogger(__name__)

# --- Bot Command Handlers (Now async) ---

# All handler functions are now 'async' and need 'await' for API calls
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    welcome_message = (
        f"Hi {user.first_name}! 🍿\n\n"
        "I'm your friendly Movie Info Bot.\n\n"
        "Just send me the name of any movie or TV show, and I'll find the details for you!\n\n"
        "For example, try sending: `The Matrix`"
    )
    # All replies are now awaited
    await update.message.reply_text(welcome_message)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error('Update "%s" caused error "%s"', update, context.error)
    # Optionally, inform the user that an error occurred
    await update.message.reply_text("Sorry, an internal error occurred. The developers have been notified.")


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Searches for the movie on OMDb and replies with the details."""
    movie_title = update.message.text
    api_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={movie_title}"
    
    try:
        # Using a standard 'requests' call is fine here
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()

        if data.get("Response") == "True":
            title = data.get("Title", "N/A")
            year = data.get("Year", "N/A")
            plot = data.get("Plot", "N/A")
            poster_url = data.get("Poster", "")
            imdb_rating = data.get("imdbRating", "N/A")
            genre = data.get("Genre", "N/A")

            caption = (
                f"🎬 *{title}* ({year})\n\n"
                f"*{plot}*\n\n"
                f"⭐ *IMDb Rating:* {imdb_rating}\n"
                f"🎭 *Genre:* {genre}\n"
            )

            if poster_url and poster_url != "N/A":
                await update.message.reply_photo(
                    photo=poster_url,
                    caption=caption,
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(caption, parse_mode='Markdown')
        else:
            error_message = data.get("Error", "Could not find that movie.")
            await update.message.reply_text(f"😞 Sorry, {error_message}")

    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        await update.message.reply_text("Sorry, I can't reach the movie database right now.")
    except Exception as e:
        logger.error(f"An unexpected error in search_movie: {e}")
        await update.message.reply_text("An unexpected error occurred.")

# --- Main Function to Run the Bot ---
def main() -> None:
    """Start the bot."""
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable not set!")
        return
    if not OMDB_API_KEY:
        logger.error("OMDB_API_KEY environment variable not set!")
        return

    # The new way to create the application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_movie))
    application.add_error_handler(error_handler)

    # --- Webhook setup for Render ---
    PORT = int(os.environ.get('PORT', 8443))
    # Get the app URL from Render's environment variables
    WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL')

    if WEBHOOK_URL:
        # Run the bot in webhook mode
        logger.info(f"Starting webhook on port {PORT}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TELEGRAM_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}"
        )
    else:
        # Run in polling mode for local testing if WEBHOOK_URL is not set
        logger.info("Starting bot in polling mode")
        application.run_polling()

    logger.info("Bot has started!")


if __name__ == '__main__':
    main()
