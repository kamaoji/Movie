# bot.py (Version 17 - Robust Indexing with File ID Persistence)

import os
import logging
import requests
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- Configuration ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
PRIVATE_CHANNEL_ID = os.environ.get("PRIVATE_CHANNEL_ID")

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- In-Memory Index (Unchanged Structure, but now persists file_id better) ---
movie_index = {} 

# --- Language and Button Data (Unchanged) ---
LANGUAGE_DATA = {
    'en': {'name': 'English', 'region': 'US'}, 'hi': {'name': 'Hindi', 'region': 'IN'},
    'ta': {'name': 'Tamil', 'region': 'IN'}, 'te': {'name': 'Telugu', 'region': 'IN'},
    'es': {'name': 'Spanish', 'region': 'ES'}, 'fr': {'name': 'French', 'region': 'FR'},
}

# --- Button Keyboard Helpers (Unchanged) ---
def get_main_menu_keyboard():
    keyboard = [[InlineKeyboardButton("🇮🇳 Hindi", callback_data='lang_hi'), InlineKeyboardButton("🇬🇧 English", callback_data='lang_en')], [InlineKeyboardButton("More Languages 🌍", callback_data='show_more_langs')]]
    return InlineKeyboardMarkup(keyboard)

def get_more_languages_keyboard():
    keyboard = [[InlineKeyboardButton("Tamil", callback_data='lang_ta'), InlineKeyboardButton("Telugu", callback_data='lang_te')], [InlineKeyboardButton("Spanish", callback_data='lang_es'), InlineKeyboardButton("French", callback_data='lang_fr')], [InlineKeyboardButton("« Back", callback_data='back_to_main')]]
    return InlineKeyboardMarkup(keyboard)

# --- Start and Button Handlers (Unchanged) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome_message = f"Hey {user.first_name}! 👋 Welcome to the Ultimate Movie Bot! 🎬\n\nI can now search my own private library for you!\n\nChoose your preferred language below to get tailored results! 👇"
    await update.message.reply_text(welcome_message, reply_markup=get_main_menu_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == 'show_more_langs':
        await query.edit_message_text(text="Here are some more popular languages:", reply_markup=get_more_languages_keyboard())
    elif data == 'back_to_main':
        await query.edit_message_text(text="Choose your preferred language or send me a title directly!", reply_markup=get_main_menu_keyboard())
    elif data.startswith('lang_'):
        lang_code = data.split('_')[1]
        context.user_data['language'] = lang_code
        lang_name = LANGUAGE_DATA.get(lang_code, {}).get('name', 'selected language')
        await query.edit_message_text(text=f"✅ Great! Your preferred language is set to *{lang_name}*.\n\nNow, send me any movie title to search!", parse_mode='Markdown')

# --- MODIFIED: Indexing function now handles new posts AND edits ---
async def update_index(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Determine if it's a new post or an edited post
    # The 'update' object will have either 'channel_post' or 'edited_channel_post'
    channel_post_obj = update.channel_post if update.channel_post else update.edited_channel_post

    if not channel_post_obj or str(channel_post_obj.chat.id) != PRIVATE_CHANNEL_ID:
        return # Not from our target channel or not a post

    caption = channel_post_obj.caption
    if not caption: # Caption is mandatory for indexing
        return

    title_match = re.search(r'#Title\s+([^\n]+)', caption, re.IGNORECASE)
    lang_match = re.search(r'#Lang\s+([a-zA-Z]{2})', caption, re.IGNORECASE)
    
    if title_match and lang_match:
        title = title_match.group(1).strip().lower()
        lang = lang_match.group(1).strip().lower()
        message_id = channel_post_obj.message_id 
        index_key = f"{title}_{lang}"

        # Retrieve existing data if the movie is already indexed (for edited posts)
        existing_data = movie_index.get(index_key, {})

        # Try to get file_id and type from the *current* update object
        # This will be present for new posts, but might be None for edited posts
        current_file_id = None
        current_file_type = None
        if channel_post_obj.photo:
            current_file_id = channel_post_obj.photo[-1].file_id
            current_file_type = "photo"
        elif channel_post_obj.video:
            current_file_id = channel_post_obj.video.file_id
            current_file_type = "video"
        elif channel_post_obj.document: 
            current_file_id = channel_post_obj.document.file_id
            current_file_type = "document"
        
        # DETERMINE FINAL file_id and file_type to store:
        # Prioritize 'current_file_id' (from a new post or an edit that included media),
        # otherwise use 'existing_data.get("file_id")' (from a previous index operation)
        final_file_id = current_file_id if current_file_id else existing_data.get("file_id")
        final_file_type = current_file_type if current_file_type else existing_data.get("file_type")

        # --- Extract button data (unchanged logic) ---
        extracted_buttons = []
        for line in caption.split('\n'):
            if line.strip().lower().startswith('#button'):
                matches = re.findall(r'\[(.*?)\]\((.*?)\)', line)
                for text, url in matches:
                    if text and url:
                        extracted_buttons.append({"text": text.strip(), "url": url.strip()})

        movie_index[index_key] = {
            "file_id": final_file_id,          # Store the (preserved or new) file_id
            "file_type": final_file_type,      # Store the (preserved or new) file_type
            "original_caption": caption,       # Store the entire original caption
            "message_id": message_id,          # Message ID
            "buttons": extracted_buttons       # Stored custom buttons
        }
        logger.info(f"Successfully Indexed (or Updated): Key='{index_key}', Type='{final_file_type}', Buttons: {len(extracted_buttons)}, Message ID='{message_id}'")
        try:
            await context.bot.add_reaction(chat_id=PRIVATE_CHANNEL_ID, message_id=message_id, reaction="👍")
        except Exception as e:
            logger.warning(f"Could not react to message (check permissions): {e}")

# --- Main search function (Unchanged from Version 15) ---
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

        if tmdb_data.get('poster_url'):
            await update.message.reply_photo(photo=tmdb_data['poster_url'], caption=caption, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=reply_markup)
        return

    # --- Step 2: Search private index (Unchanged, now relies on updated movie_index) ---
    if user_lang_code:
        index_key = f"{query}_{user_lang_code}"
        movie_data_from_index = movie_index.get(index_key)

        if movie_data_from_index:
            file_id = movie_data_from_index.get("file_id")
            file_type = movie_data_from_index.get("file_type")
            original_caption = movie_data_from_index.get("original_caption", "")
            
            cleaned_caption_lines = []
            for line in original_caption.split('\n'):
                if '#Title' in line or '#Lang' in line or '#Button' in line:
                    continue
                cleaned_caption_lines.append(line)
            cleaned_caption = '\n'.join(cleaned_caption_lines).strip()

            reply_markup = None
            stored_buttons = movie_data_from_index.get("buttons", [])
            if stored_buttons:
                keyboard = []
                for btn_data in stored_buttons:
                    keyboard.append([InlineKeyboardButton(btn_data['text'], url=btn_data['url'])])
                reply_markup = InlineKeyboardMarkup(keyboard)

            logger.info(f"Found in private index! Re-sending '{index_key}'.")
            try:
                if file_id and file_type == "photo":
                    await context.bot.send_photo(chat_id=user_id, photo=file_id, caption=cleaned_caption, reply_markup=reply_markup)
                elif file_id and file_type == "video":
                    await context.bot.send_video(chat_id=user_id, video=file_id, caption=cleaned_caption, reply_markup=reply_markup)
                elif file_id and file_type == "document":
                     await context.bot.send_document(chat_id=user_id, document=file_id, caption=cleaned_caption, reply_markup=reply_markup)
                else: 
                    await context.bot.send_message(chat_id=user_id, text=cleaned_caption, reply_markup=reply_markup)
                return 
            except Exception as e:
                logger.error(f"Failed to re-send message from private index: {e}")
                # Specifically check for 'file_id is empty' in logs to confirm this fix addresses it.
                await update.message.reply_text("I found the movie in my library, but couldn't send it. There might be an issue with the post content or my permissions.")
                return

    # --- Step 3: If all fails ---
    await update.message.reply_text("Movie not found in TMDB or my private library for the selected language.")

# --- search_tmdb function (Unchanged) ---
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
        else:
            found_movie_id = search_data["results"][0]["id"]
        if not found_movie_id: return None
        details_url = f"https://api.themoviedb.org/3/movie/{found_movie_id}?language=en-US"
        details_response = requests.get(details_url, headers=headers)
        details_response.raise_for_status()
        data = details_response.json()
        return {"source": "TMDB", "title": data.get("title", "N/A"), "rating": f"{data.get('vote_average', 0):.1f} / 10", "genre": ", ".join([g['name'] for g in data.get("genres", [])]), "language": data.get("spoken_languages")[0]['english_name'] if data.get("spoken_languages") else "N/A", "runtime": f"{data.get('runtime', 0) // 60}h {data.get('runtime', 0) % 60}m" if data.get('runtime') else "N/A", "release_date": data.get("release_date", "N/A"), "poster_url": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get('poster_path') else None, "button_url": f"https://www.themoviedb.org/movie/{found_movie_id}"}
    except Exception as e:
        logger.error(f"TMDB search failed: {e}")
        return None

# --- Error Handler & Main function (MODIFIED: Add EDITED_CHANNEL_POST handler) ---
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main() -> None:
    if not all([TELEGRAM_TOKEN, TMDB_API_KEY, PRIVATE_CHANNEL_ID]):
        logger.error("One or more required environment variables are missing!")
        return
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Listen to BOTH new channel posts AND edited channel posts for indexing
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST | filters.UpdateType.EDITED_CHANNEL_POST, update_index))
    
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
