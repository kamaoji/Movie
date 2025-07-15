# bot.py (Version 3.1: Fixed MarkdownV2 parsing error)

import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden

# --- Configuration ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OMDB_API_KEY = os.environ.get("OMDB_API_KEY")
UPDATES_CHANNEL = os.environ.get("UPDATES_CHANNEL")
WELCOME_IMAGE_FILE_ID = os.environ.get("WELCOME_IMAGE_FILE_ID")

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- Force Subscribe Middleware ---
async def check_user_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not UPDATES_CHANNEL: return True
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=UPDATES_CHANNEL, user_id=user_id)
        if member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
            return True
        else:
            return False
    except (BadRequest, Forbidden) as e:
        logger.error(f"Error checking membership for user {user_id} in channel {UPDATES_CHANNEL}: {e}")
        return True

async def force_subscribe_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, command_handler):
    is_member = await check_user_membership(update, context)
    if is_member:
        await command_handler(update, context)
    else:
        channel_link = f"https://t.me/{UPDATES_CHANNEL.lstrip('@')}"
        keyboard = [
            [InlineKeyboardButton("📢 JOIN UPDATES CHANNEL 📢", url=channel_link)],
            [InlineKeyboardButton("🔄 Try Again 🔄", callback_data="check_join")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        # We use a simpler parse mode here to avoid errors
        await update.message.reply_text(
            "❗**JOIN THIS CHANNEL TO USE THE BOT**❗\n\n"
            "Please join our updates channel and then click 'Try Again'.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )

# --- Bot Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await force_subscribe_handler(update, context, start_action)

async def start_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    effective_user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("🔍 SEARCH MOVIES OR SERIES 🔍", callback_data="search_prompt")],
        [InlineKeyboardButton("📤 SHARE NOW 📤", switch_inline_query="Check out this awesome movie bot!")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_message = f"Hey 👋 {effective_user.first_name}\\!" # Escaping the ! here too, just in case.
    await update.message.reply_photo(
        photo=WELCOME_IMAGE_FILE_ID,
        caption=welcome_message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await force_subscribe_handler(update, context, search_action)

async def search_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    movie_title = update.message.text
    api_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&s={movie_title}"
    try:
        response = requests.get(api_url)
        data = response.json()
        if data.get("Response") == "True":
            results = data.get("Search", [])
            context.user_data['search_results'] = results
            context.user_data['search_query'] = movie_title
            await generate_search_page(update, context, page_number=0)
        else:
            await update.message.reply_text("😞 No movies found with that title. Please check the spelling.")
    except Exception as e:
        logger.error(f"Error in search_action: {e}")
        await update.message.reply_text("An error occurred while searching. Please try again.")

async def generate_search_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page_number: int):
    results = context.user_data.get('search_results', [])
    query = context.user_data.get('search_query', 'your search').replace('-', '\\-').replace('.', '\\.') # Escape query
    items_per_page = 5
    start_index = page_number * items_per_page
    end_index = start_index + items_per_page
    page_items = results[start_index:end_index]
    total_pages = (len(results) + items_per_page - 1) // items_per_page

    text = f"Found *{len(results)}* results for: *{query}*\n\n"
    for item in page_items:
        title = item.get('Title', '').replace('-', '\\-').replace('(', '\\(').replace(')', '\\)')
        year = item.get('Year', '')
        item_type = item.get('Type', '').capitalize()
        text += f"🎬 *{title}* \\({year}\\) \\- [{item_type}]\n"

    keyboard = []
    row = []
    if page_number > 0:
        row.append(InlineKeyboardButton("◀️ Previous", callback_data=f"page_{page_number-1}"))
    row.append(InlineKeyboardButton(f"Page {page_number+1}/{total_pages}", callback_data="noop"))
    if end_index < len(results):
        row.append(InlineKeyboardButton("Next ▶️", callback_data=f"page_{page_number+1}"))
    keyboard.append(row)
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        effective_message = update.callback_query.message if update.callback_query else update.message
        await effective_message.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    except BadRequest: # If editing fails (e.g., message is the same)
        if update.callback_query: await update.callback_query.answer() # Still acknowledge
    except Exception as e: # Catch other edit errors
        logger.warning(f"Could not edit message, sending new one. Error: {e}")
        await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data == "search_prompt":
        # THE FIX IS HERE: Escaped the "!" characters with "\\!"
        prompt_text = (
            "📖 SEND MOVIE OR SERIES NAME AND\n"
            "YEAR AS PER GOOGLE SPELLING\\.\\.\\!\\! 🤏\n\n"
            "⚠️ *Example For Movie* 🤏\n`Jailer`\n`Jailer 2023`\n\n"
            "⚠️ *Example For WEBSERIES* 👇\n`Stranger Things`\n`Stranger Things S02 E04`\n\n"
            "⚠️ *DON'T ADD EMOJIS AND SYMBOLS IN MOVIE NAME, USE LETTERS ONLY\\.\\.\\!\\!* ❌"
        )
        await query.message.reply_text(prompt_text, parse_mode=ParseMode.MARKDOWN_V2)
    elif query.data.startswith("page_"):
        page_number = int(query.data.split("_")[1])
        await generate_search_page(update, context, page_number)
    elif query.data == "check_join":
        is_member = await check_user_membership(update, context)
        if is_member:
            await query.message.delete()
            await start_action(query, context)
        else:
            await query.answer("You still haven't joined the channel. Please join first.", show_alert=True)
    elif query.data == "noop":
        return

def main() -> None:
    # Pre-run checks
    if not all([TELEGRAM_TOKEN, OMDB_API_KEY, UPDATES_CHANNEL, WELCOME_IMAGE_FILE_ID]):
        logger.error("FATAL: One or more environment variables are missing!")
        return
    if "PASTE_YOUR_FILE_ID_HERE" in WELCOME_IMAGE_FILE_ID:
        logger.error("FATAL: WELCOME_IMAGE_FILE_ID is not set correctly!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    PORT = int(os.environ.get('PORT', 8443))
    WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL')
    if WEBHOOK_URL:
        application.run_webhook(
            listen="0.0.0.0", port=PORT, url_path=TELEGRAM_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}"
        )
    else:
        application.run_polling()

if __name__ == '__main__':
    main()
