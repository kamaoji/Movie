# bot.py (Version 3 - Modern, Async)

import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configuration ---
# These are the same environment variables.
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY") # This is your v4 Read Access Token

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Bot Command Handlers (Now using async/await) ---

# All handler functions must now be 'async'
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message for the /start command."""
    user = update.effective_user
    welcome_message = (
        f"Hi {user.first_name}! 🍿\n\n"
        "I am your modern Movie Info Bot, powered by TMDB!\n\n"
        "Just send me the name of any movie or TV show to get started."
    )
    # Every reply is now an 'await' call
    await update.message.reply_text(welcome_message)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs errors caused by updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)

async def search_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search for media on TMDB and reply with the details."""
    query = update.message.text
    
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {TMDB_API_KEY}"
    }
    
    search_url = f"https://api.themoviedb.org/3/search/movie?query={query}&include_adult=false&language=en-US&page=1"
    
    try:
        # Note: requests is a synchronous library. For high-performance bots,
        # an async library like httpx would be used, but for this bot, requests is fine.
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()
        search_data = response.json()

        if not search_data.get("results"):
            await update.message.reply_text("😞 Sorry, I couldn't find any movie with that name. Please check the spelling.")
            return

        top_result = search_data["results"][0]
        movie_id = top_result["id"]
        
        details_url = f"https://api.themoviedb.org/3/movie/{movie_id}?language=en-US"
        details_response = requests.get(details_url, headers=headers)
        details_response.raise_for_status()
        data = details_response.json()

        title = data.get("title", "N/A")
        tagline = data.get("tagline")
        overview = data.get("overview", "No plot summary available.")
        release_date = data.get("release_date", "N/A")
        vote_average = data.get("vote_average", 0)
        genres = ", ".join([genre['name'] for genre in data.get("genres", [])])
        runtime = data.get("runtime", 0)
        poster_path = data.get("poster_path")

        if runtime:
            hours = runtime // 60
            minutes = runtime % 60
            runtime_formatted = f"{hours}h {minutes}m"
        else:
            runtime_formatted = "N/A"
            
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
        
        caption = (
            f"🎬 *{title}*\n"
            f"_{tagline}_\n\n"
            f"*{'─'*30}*\n\n"
            f"*{overview}*\n\n"
            f"*{'─'*30}*\n\n"
            f"⭐ *Rating:* {vote_average:.1f} / 10\n"
            f"🎭 *Genre:* {genres}\n"
            f"🕒 *Runtime:* {runtime_formatted}\n"
            f"📅 *Release Date:* {release_date}\n"
        )
        
        if poster_url:
            await update.message.reply_photo(
                photo=poster_url,
                caption=caption,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(caption, parse_mode='Markdown')

    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        await update.message.reply_text("Sorry, I'm having trouble connecting to the movie database.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        await update.message.reply_text("An unexpected error occurred. Please try again later.")


# --- Main Function to Run the Bot ---
def main() -> None:
    """Start the bot."""
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable not set!")
        return
    if not TMDB_API_KEY:
        logger.error("TMDB_API_KEY environment variable not set!")
        return

    # The new way to build the bot application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_media))
    application.add_error_handler(error_handler)

    # For hosting on Render (Webhook)
    PORT = int(os.environ.get('PORT', 8443))
    
    # We get the app name from Render's environment variables
    # This makes the webhook URL dynamic and easier to manage
    APP_NAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if not APP_NAME:
        logger.error("RENDER_EXTERNAL_HOSTNAME environment variable not set!")
        return
    
    # The run_webhook method is part of the main 'run' loop
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_TOKEN,
        webhook_url=f"https://{APP_NAME}/{TELEGRAM_TOKEN}"
    )


if __name__ == '__main__':
    main()
