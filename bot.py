# bot.py (Version 7 - Random Movie Roulette)

import os
import logging
import requests
import random # We need the random library
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configuration (Unchanged) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
OMDB_API_KEY = os.environ.get("OMDB_API_KEY")

# --- Logging Setup (Unchanged) ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- NEW: /random command handler ---
async def random_movie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Finds a random, popular movie on Netflix."""
    await update.message.reply_text("Spinning the roulette... 🎲")

    try:
        headers = {"accept": "application/json", "Authorization": f"Bearer {TMDB_API_KEY}"}
        
        # --- API Call to Discover Endpoint ---
        # Parameters:
        # with_watch_providers=8  (8 is the ID for Netflix)
        # watch_region=US         (Change this to your preferred country code, e.g., IN, GB)
        # sort_by=popularity.desc (Get popular movies)
        # page=...                (We'll pick a random page)
        
        # First, get the total number of pages to choose from
        initial_url = "https://api.themoviedb.org/3/discover/movie?include_adult=false&language=en-US&sort_by=popularity.desc&watch_region=US&with_watch_providers=8"
        initial_response = requests.get(initial_url, headers=headers).json()
        total_pages = initial_response.get('total_pages', 1)
        
        # Pick a random page (up to a max of 500 as per TMDB API limits)
        random_page = random.randint(1, min(total_pages, 500))

        # Now, make the final request for the random page
        discover_url = f"https://api.themoviedb.org/3/discover/movie?include_adult=false&language=en-US&page={random_page}&sort_by=popularity.desc&watch_region=US&with_watch_providers=8"
        
        response = requests.get(discover_url, headers=headers)
        response.raise_for_status()
        data = response.json()

        if not data.get("results"):
            await update.message.reply_text("I couldn't find a random movie right now. Please try again!")
            return

        # Pick a random movie from the results on that page
        movie = random.choice(data["results"])
        
        # Use our existing function to send the reply
        await send_movie_info(update, movie['id'])

    except Exception as e:
        logger.error(f"Random movie failed: {e}")
        await update.message.reply_text("Sorry, something went wrong with the roulette. Please try again.")


# --- NEW: Reusable function to send movie info ---
# I've moved the message sending logic here so we can reuse it for both search and random.
async def send_movie_info(update: Update, movie_id: int):
    """Fetches details for a movie_id and sends the formatted reply."""
    headers = {"accept": "application/json", "Authorization": f"Bearer {TMDB_API_KEY}"}
    details_url = f"https://api.themoviedb.org/3/movie/{movie_id}?language=en-US"
    data = requests.get(details_url, headers=headers).json()

    # Extract and format data
    title = data.get("title", "N/A")
    rating = f"{data.get('vote_average', 0):.1f} / 10"
    genre = ", ".join([g['name'] for g in data.get("genres", [])])
    language = data.get("spoken_languages")[0]['english_name'] if data.get("spoken_languages") else "N/A"
    runtime = f"{data.get('runtime', 0) // 60}h {data.get('runtime', 0) % 60}m" if data.get('runtime') else "N/A"
    release_date = data.get("release_date", "N/A")
    poster_url = f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get('poster_path') else None
    button_url = f"https://www.themoviedb.org/movie/{movie_id}"

    caption = (
        f"🎬 *{title}*\n\n"
        f"⭐ *TMDB Rating:* {rating}\n"
        f"🎭 *Genre:* {genre}\n"
        f"🌐 *Language:* {language}\n"
        f"🕒 *Runtime:* {runtime}\n"
        f"📅 *Release Date:* {release_date}"
    )
    
    keyboard = [[InlineKeyboardButton("More Info on TMDB", url=button_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.effective_message.reply_photo(
        photo=poster_url,
        caption=caption,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


# --- MODIFIED: The main search handler now uses the new reusable function ---
async def search_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.message.text
    logger.info(f"Searching TMDB for: {query}")
    try:
        headers = {"accept": "application/json", "Authorization": f"Bearer {TMDB_API_KEY}"}
        search_url = f"https://api.themoviedb.org/3/search/movie?query={query}&include_adult=false&language=en-US&page=1"
        response = requests.get(search_url, headers=headers).json()
        
        if not response.get("results"):
            await update.message.reply_text("😞 Sorry, I couldn't find a movie with that name.")
            return
            
        movie_id = response["results"][0]["id"]
        await send_movie_info(update, movie_id)

    except Exception as e:
        logger.error(f"Search failed: {e}")
        await update.message.reply_text("An error occurred during the search.")


# --- Unchanged handlers and main function ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(f"Hi {user.first_name}! 🍿\n\nSend me a movie title or use /random to get a Netflix suggestion!")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main() -> None:
    if not all([TELEGRAM_TOKEN, TMDB_API_KEY]):
        logger.error("One or more API keys are missing!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add the new /random handler
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("random", random_movie)) # NEW
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_media))
    application.add_error_handler(error_handler)

    PORT = int(os.environ.get('PORT', 8443))
    APP_NAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if not APP_NAME:
        return
    
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_TOKEN,
        webhook_url=f"https://{APP_NAME}/{TELEGRAM_TOKEN}"
    )

if __name__ == '__main__':
    main()
