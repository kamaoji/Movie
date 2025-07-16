# bot.py (Version 16 - Advanced Button Parsing)

import os
import logging
import requests
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler, PicklePersistence
)

# --- Configuration & Logging ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
PRIVATE_CHANNEL_ID = os.environ.get("PRIVATE_CHANNEL_ID")
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Language and Button Data ---
LANGUAGE_DATA = {
    'en': {'name': 'English', 'region': 'US'}, 'hi': {'name': 'Hindi', 'region': 'IN'},
    'ta': {'name': 'Tamil', 'region': 'IN'}, 'te': {'name': 'Telugu', 'region': 'IN'},
    'es': {'name': 'Spanish', 'region': 'ES'}, 'fr': {'name': 'French', 'region': 'FR'},
}

def get_main_menu_keyboard():
    keyboard = [[InlineKeyboardButton("🇮🇳 Hindi", callback_data='lang_hi'), InlineKeyboardButton("🇬🇧 English", callback_data='lang_en')], [InlineKeyboardButton("More Languages 🌍", callback_data='show_more_langs')]]
    return InlineKeyboardMarkup(keyboard)

def get_more_languages_keyboard():
    keyboard = [[InlineKeyboardButton("Tamil", callback_data='lang_ta'), InlineKeyboardButton("Telugu", callback_data='lang_te')], [InlineKeyboardButton("Spanish", callback_data='lang_es'), InlineKeyboardButton("French", callback_data='lang_fr')], [InlineKeyboardButton("« Back", callback_data='back_to_main')]]
    return InlineKeyboardMarkup(keyboard)

# --- Bot Handlers (Start & Button unchanged) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome_message = f"Hey {user.first_name}! 👋 Welcome to the Ultimate Movie Bot! 🎬\n\nI can now remember your choices permanently!\n\nChoose your preferred language below. 👇"
    await update.message.reply_text(welcome_message, reply_markup=get_main_menu_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == 'show_more_langs': await query.edit_message_text(text="Here are some more popular languages:", reply_markup=get_more_languages_keyboard())
    elif data == 'back_to_main': await query.edit_message_text(text="Choose your preferred language or send me a title directly!", reply_markup=get_main_menu_keyboard())
    elif data.startswith('lang_'):
        lang_code = data.split('_')[1]
        context.user_data['language'] = lang_code
        lang_name = LANGUAGE_DATA.get(lang_code, {}).get('name', 'selected language')
        await query.edit_message_text(text=f"✅ Great! Your preferred language is now permanently set to *{lang_name}*.\n\nSend me any movie title to search!", parse_mode='Markdown')

# --- Indexing function (Unchanged from Version 15) ---
async def update_index(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.channel_post or str(update.channel_post.chat.id) != PRIVATE_CHANNEL_ID: return
    post = update.channel_post
    caption = post.caption if post.caption else post.text
    if not caption: return
    title_match = re.search(r'#Title\s+([^\n]+)', caption, re.IGNORECASE)
    lang_match = re.search(r'#Lang\s+([a-zA-Z]{2})', caption, re.IGNORECASE)
    if title_match and lang_match:
        title = title_match.group(1).strip().lower()
        lang = lang_match.group(1).strip().lower()
        index_key = f"{title}_{lang}"
        file_id, file_type = (None, None)
        if post.photo: file_id, file_type = post.photo[-1].file_id, "photo"
        elif post.video: file_id, file_type = post.video.file_id, "video"
        elif post.document: file_id, file_type = post.document.file_id, "document"
        elif post.text: file_type = "text"
        context.bot_data.setdefault('movie_index', {})[index_key] = {
            "file_id": file_id, "file_type": file_type, "original_caption": caption
        }
        logger.info(f"Persistently Indexed: Key='{index_key}', Type='{file_type}'")
        try:
            await context.bot.add_reaction(chat_id=PRIVATE_CHANNEL_ID, message_id=post.message_id, reaction="👍")
        except Exception as e:
            logger.warning(f"Could not react to message: {e}")

# --- NEW: Advanced button and caption parser for private posts ---
def parse_private_post(original_caption: str) -> (str, InlineKeyboardMarkup | None):
    """Parses a caption for markdown links, creates buttons, and returns a clean caption."""
    # Regex to find markdown links: [text](url)
    markdown_link_regex = r'\[([^\]]+)\]\((https?://[^\s\)]+)\)'
    
    buttons = []
    # Find all button definitions in the caption
    matches = re.findall(markdown_link_regex, original_caption)
    for text, url in matches:
        buttons.append([InlineKeyboardButton(text.strip(), url=url.strip())])

    # Clean the caption: remove indexing tags and markdown link definitions
    cleaned_caption = re.sub(markdown_link_regex, '', original_caption) # Remove the button links
    final_caption_lines = []
    for line in cleaned_caption.split('\n'):
        if '#Title' not in line and '#Lang' not in line:
            final_caption_lines.append(line)
    
    final_caption = '\n'.join(final_caption_lines).strip()
    
    return final_caption, InlineKeyboardMarkup(buttons) if buttons else None

# --- Main search function ---
async def search_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.message.text.lower().strip()
    user_id = update.effective_user.id
    user_lang_code = context.user_data.get('language')

    # --- Step 1: Try TMDB ---
    region = LANGUAGE_DATA.get(user_lang_code, {}).get('region') if user_lang_code else None
    tmdb_data = await search_tmdb(query, region=region, lang_code=user_lang_code)
    if tmdb_data:
        caption = (f"🎬 *{tmdb_data['title']}*\n\n"
                   f"⭐ *TMDB Rating:* {tmdb_data['rating']}\n"
                   f"🎭 *Genre:* {tmdb_data['genre']}\n"
                   f"🌐 *Language:* {tmdb_data['language']}\n"
                   f"🕒 *Runtime:* {tmdb_data['runtime']}\n"
                   f"📅 *Release Date:* {tmdb_data['release_date']}")
        reply_markup = None
        if tmdb_data.get('button_url'):
            keyboard = [[InlineKeyboardButton(f"More Info on {tmdb_data['source']}", url=tmdb_data['button_url'])]]
            reply_markup = InlineKeyboardMarkup(keyboard)
        if tmdb_data.get('poster_url'): await update.message.reply_photo(photo=tmdb_data['poster_url'], caption=caption, parse_mode='Markdown', reply_markup=reply_markup)
        else: await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=reply_markup)
        return

    # --- Step 2: Search persistent private index with new parser ---
    if user_lang_code:
        index_key = f"{query}_{user_lang_code}"
        movie_index = context.bot_data.get('movie_index', {})
        movie_data_from_index = movie_index.get(index_key)
        if movie_data_from_index:
            file_id, file_type, original_caption = movie_data_from_index.get("file_id"), movie_data_from_index.get("file_type"), movie_data_from_index.get("original_caption", "")
            
            # Use the new advanced parser to get clean caption and buttons
            final_caption, reply_markup = parse_private_post(original_caption)

            logger.info(f"Found in persistent index! Re-sending '{index_key}' with auto-buttons.")
            try:
                if file_type == "photo": await context.bot.send_photo(chat_id=user_id, photo=file_id, caption=final_caption, parse_mode='Markdown', reply_markup=reply_markup)
                elif file_type == "video": await context.bot.send_video(chat_id=user_id, video=file_id, caption=final_caption, parse_mode='Markdown', reply_markup=reply_markup)
                elif file_type == "document": await context.bot.send_document(chat_id=user_id, document=file_id, caption=final_caption, parse_mode='Markdown', reply_markup=reply_markup)
                else: await context.bot.send_message(chat_id=user_id, text=final_caption, parse_mode='Markdown', reply_markup=reply_markup)
                return
            except Exception as e:
                logger.error(f"Failed to re-send message from persistent index: {e}")
                await update.message.reply_text("I found the movie in my library, but couldn't send it.")
                return

    # --- Step 3: If all fails ---
    await update.message.reply_text("Movie not found in TMDB or my private library for the selected language.")

# --- search_tmdb (Unchanged) ---
async def search_tmdb(query: str, region: str | None = None, lang_code: str | None = None) -> dict | None:
    try:
        headers = {"accept": "application/json", "Authorization": f"Bearer {TMDB_API_KEY}"}
        search_url = f"https://api.themoviedb.org/3/search/movie?query={query}&include_adult=false&language=en-US&page=1"
        if region: search_url += f"®ion={region}"
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()
        search_data = response.json()
        if not search_data.get("results"): return None
        found_movie_id = None
        if lang_code:
            for movie in search_data["results"]:
                if movie.get('original_language') == lang_code:
                    found_movie_id = movie['id']; break
        else: found_movie_id = search_data["results"][0]["id"]
        if not found_movie_id: return None
        details_url = f"https://api.themoviedb.org/3/movie/{found_movie_id}?language=en-US"
        details_response = requests.get(details_url, headers=headers)
        details_response.raise_for_status()
        data = details_response.json()
        return {"source": "TMDB", "title": data.get("title", "N/A"), "rating": f"{data.get('vote_average', 0):.1f} / 10", "genre": ", ".join([g['name'] for g in data.get("genres", [])]), "language": data.get("spoken_languages")[0]['english_name'] if data.get("spoken_languages") else "N/A", "runtime": f"{data.get('runtime', 0) // 60}h {data.get('runtime', 0) % 60}m" if data.get('runtime') else "N/A", "release_date": data.get("release_date", "N/A"), "poster_url": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get('poster_path') else None, "button_url": f"https://www.themoviedb.org/movie/{found_movie_id}"}
    except Exception as e:
        logger.error(f"TMDB search failed: {e}")
        return None

# --- Error Handler & Main function with persistence (Unchanged) ---
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning('Update "%s" caused error "%s"', update, context.error)
def main() -> None:
    if not all([TELEGRAM_TOKEN, TMDB_API_KEY, PRIVATE_CHANNEL_ID]):
        logger.error("One or more required environment variables are missing!")
        return
    persistence = PicklePersistence(filepath="bot_persistence.pkl")
    application = (Application.builder().token(TELEGRAM_TOKEN).persistence(persistence).build())
    if 'movie_index' not in application.bot_data:
        application.bot_data['movie_index'] = {}
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, update_index))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_media))
    application.add_error_handler(error_handler)
    PORT = int(os.environ.get('PORT', 8443))
    APP_NAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if not APP_NAME:
        logger.error("RENDER_EXTERNAL_HOSTNAME environment variable not set!")
        return
    application.run_webhook(listen="0.0.0.0", port=PORT, url_path=TELEGRAM_TOKEN, webhook_url=f"https://{APP_NAME}/{TELEGRAM_TOKEN}")

if __name__ == '__main__':
    main()
