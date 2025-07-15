# bot.py

import os
import logging
import requests # To make API calls to OMDb
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# --- Configuration ---
# It's best practice to get these from environment variables instead of hardcoding
# On your hosting platform (like Render), you will set these variables.
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OMDB_API_KEY = os.environ.get("OMDB_API_KEY")

# --- Logging Setup (Good for debugging) ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- Bot Command Handlers ---

# Function for the /start command
def start(update: Update, context: CallbackContext) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    welcome_message = (
        f"Hi {user.first_name}! 🍿\n\n"
        "I'm your friendly Movie Info Bot.\n\n"
        "Just send me the name of any movie or TV show, and I'll find the details for you!\n\n"
        "For example, try sending: `The Matrix`"
    )
    update.message.reply_text(welcome_message)

# Function to handle errors
def error_handler(update: Update, context: CallbackContext) -> None:
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)

# Function to search for the movie
def search_movie(update: Update, context: CallbackContext) -> None:
    """Searches for the movie on OMDb and replies with the details."""
    movie_title = update.message.text
    
    # The URL for the OMDb API
    api_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={movie_title}"
    
    try:
        # Make the request to the API
        response = requests.get(api_url)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        data = response.json()

        # Check if the movie was found
        if data.get("Response") == "True":
            # Extract movie details
            title = data.get("Title", "N/A")
            year = data.get("Year", "N/A")
            rated = data.get("Rated", "N/A")
            released = data.get("Released", "N/A")
            runtime = data.get("Runtime", "N/A")
            genre = data.get("Genre", "N/A")
            director = data.get("Director", "N/A")
            plot = data.get("Plot", "N/A")
            poster_url = data.get("Poster", "")
            imdb_rating = data.get("imdbRating", "N/A")

            # Create the message caption
            caption = (
                f"🎬 *{title}* ({year})\n\n"
                f"*{'─'*30}*\n\n"
                f"*{plot}*\n\n"
                f"*{'─'*30}*\n\n"
                f"⭐ *IMDb Rating:* {imdb_rating}\n"
                f"🕒 *Runtime:* {runtime}\n"
                f"🎭 *Genre:* {genre}\n"
                f"🎬 *Director:* {director}\n"
                f"📅 *Released:* {released}\n"
            )

            # If there's a poster, send it as a photo with the caption
            if poster_url and poster_url != "N/A":
                update.message.reply_photo(
                    photo=poster_url,
                    caption=caption,
                    parse_mode='Markdown'
                )
            else:
                # Otherwise, just send the text
                update.message.reply_text(caption, parse_mode='Markdown')

        else:
            # If movie not found
            error_message = data.get("Error", "Could not find that movie. Please check the spelling.")
            update.message.reply_text(f"😞 Sorry, {error_message}")

    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        update.message.reply_text("Sorry, I'm having trouble connecting to the movie database right now.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        update.message.reply_text("An unexpected error occurred. Please try again later.")


# --- Main Function to Run the Bot ---
def main() -> None:
    """Start the bot."""
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable not set!")
        return
    if not OMDB_API_KEY:
        logger.error("OMDB_API_KEY environment variable not set!")
        return

    # Create the Updater and pass it your bot's token.
    updater = Updater(TELEGRAM_TOKEN)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Register command handlers
    dispatcher.add_handler(CommandHandler("start", start))

    # Register a message handler to listen for movie titles (non-command text)
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, search_movie))
    
    # Register the error handler
    dispatcher.add_handler(MessageHandler(Filters.all, error_handler))

    # Start the Bot
    # For hosting on Render, we use webhooks, not polling.
    # The PORT is provided by Render automatically.
    PORT = int(os.environ.get('PORT', '8443'))
    updater.start_webhook(listen="0.0.0.0",
                          port=PORT,
                          url_path=TELEGRAM_TOKEN,
                          webhook_url=f"https://your-app-name.onrender.com/{TELEGRAM_TOKEN}")
    
    #updater.start_polling() # Use this line for local testing instead of the webhook lines above

    logger.info("Bot has started!")
    updater.idle()


if __name__ == '__main__':
    main()