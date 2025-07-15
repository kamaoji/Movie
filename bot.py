# bot.py (Version 2 with TMDB API)

import os
import logging
import requests
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# --- Configuration ---
# Get your new TMDB token from your hosting environment variables
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY") # This is your v4 Read Access Token

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- Bot Command Handlers ---

def start(update: Update, context: CallbackContext) -> None:
    """Sends a welcome message for the /start command."""
    user = update.effective_user
    welcome_message = (
        f"Hi {user.first_name}! 🍿\n\n"
        "I'm your upgraded Movie Info Bot, now powered by TMDB!\n\n"
        "Send me the name of any movie or TV show to get started. For example: `Blade Runner 2049`"
    )
    update.message.reply_text(welcome_message)

def error_handler(update: Update, context: CallbackContext) -> None:
    """Logs errors."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def search_media(update: Update, context: CallbackContext) -> None:
    """Search for media (movie or TV) on TMDB and reply with the details."""
    query = update.message.text
    
    # Define the headers for TMDB API v4 authentication
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {TMDB_API_KEY}"
    }
    
    # --- Part 1: Search for the movie to get its ID ---
    search_url = f"https://api.themoviedb.org/3/search/movie?query={query}&include_adult=false&language=en-US&page=1"
    
    try:
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()
        search_data = response.json()

        if not search_data.get("results"):
            update.message.reply_text("😞 Sorry, I couldn't find any movie with that name. Please check the spelling.")
            return

        # Get the top result from the search
        top_result = search_data["results"][0]
        
        # --- Part 2: Use the ID to get detailed information ---
        movie_id = top_result["id"]
        details_url = f"https://api.themoviedb.org/3/movie/{movie_id}?language=en-US"
        
        details_response = requests.get(details_url, headers=headers)
        details_response.raise_for_status()
        data = details_response.json()

        # Extract movie details
        title = data.get("title", "N/A")
        tagline = data.get("tagline")
        overview = data.get("overview", "No plot summary available.")
        release_date = data.get("release_date", "N/A")
        vote_average = data.get("vote_average", 0)
        genres = ", ".join([genre['name'] for genre in data.get("genres", [])])
        runtime = data.get("runtime", 0)
        poster_path = data.get("poster_path")

        # Format runtime from minutes to hours and minutes
        if runtime:
            hours = runtime // 60
            minutes = runtime % 60
            runtime_formatted = f"{hours}h {minutes}m"
        else:
            runtime_formatted = "N/A"
            
        # Create the image URL
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
        
        # Create the message caption
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
        
        # Send the message
        if poster_url:
            update.message.reply_photo(
                photo=poster_url,
                caption=caption,
                parse_mode='Markdown'
            )
        else:
            update.message.reply_text(caption, parse_mode='Markdown')

    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        update.message.reply_text("Sorry, I'm having trouble connecting to the movie database.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        update.message.reply_text("An unexpected error occurred. Please try again later.")


# --- Main Function to Run the Bot ---
def main() -> None:
    """Start the bot."""
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable not set!")
        return
    if not TMDB_API_KEY:
        logger.error("TMDB_API_KEY environment variable not set!")
        return

    updater = Updater(TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, search_media))
    dispatcher.add_error_handler(error_handler)

    # For hosting on Render (Webhook)
    PORT = int(os.environ.get('PORT', '8443'))
    updater.start_webhook(listen="0.0.0.0",
                          port=PORT,
                          url_path=TELEGRAM_TOKEN,
                          webhook_url=f"https://your-app-name.onrender.com/{TELEGRAM_TOKEN}")
                          
    logger.info("Bot has started with TMDB integration!")
    updater.idle()

if __name__ == '__main__':
    main()
