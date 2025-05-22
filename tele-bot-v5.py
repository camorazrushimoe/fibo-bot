import os
import logging
import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    JobQueue,
    CallbackQueryHandler
)
import re

# --- Attempt to import eng_to_ipa ---
try:
    import eng_to_ipa
    ENG_TO_IPA_AVAILABLE = True
    # Initial log before main logger is configured
    logging.getLogger(__name__).info("eng_to_ipa library found and imported successfully.")
except ImportError:
    ENG_TO_IPA_AVAILABLE = False
    logging.getLogger(__name__).warning("eng_to_ipa library not found. Phonetic clues will be basic. Run 'pip install eng_to_ipa'")

# --- Attempt to import and use 'translate' library ---
try:
    from translate import Translator
    # from translate.exceptions import TranslationError # Optional for specific error handling
    TRANSLATOR_AVAILABLE = True
    logging.getLogger(__name__).info("'translate' library found and imported successfully.")
except ImportError:
    TRANSLATOR_AVAILABLE = False
    logging.getLogger(__name__).warning("'translate' library not found. Translation feature will be disabled. Run 'pip install translate'")


# --- Configuration ---
BOT_TOKEN = "PUT YOUR TOKEN HERE" # REPLACE THIS with your actual Bot Token

# Configure main logger (will reconfigure if basicConfig was called by initial checks)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    force=True # Force reconfig if initial basicConfig was called
)
logger = logging.getLogger(__name__) # Main logger for the script

if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    logger.critical("FATAL: Bot token is not set in the script! Please replace 'YOUR_BOT_TOKEN_HERE'.")
    exit("Bot token not configured.")

REMINDER_INTERVALS_SECONDS = [
    60,         # 1 minute
    1440 * 60,  # 1 day
    2880 * 60,  # 2 days
    5760 * 60,  # 4 days
    11520 * 60, # 8 days
    17280 * 60, # 12 days
    23040 * 60, # 16 days
    28800 * 60, # 20 days
    37440 * 60, # 26 days
    48960 * 60, # 34 days
    69120 * 60, # 48 days
    86440 * 60, # 60 days
    115200 * 60,# 80 days
    144000 * 60 # 100 days
]

# Callback data prefixes
CALLBACK_DELETE_REQUEST = "del_req:"
CALLBACK_DELETE_CONFIRM = "del_conf:"
CALLBACK_DELETE_CANCEL = "del_can:"
CALLBACK_CLUE_REQUEST = "clue_req:"

LEARNING_DICT_BUTTON_TEXT = "📚 Learning Dictionary"
REPLY_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(LEARNING_DICT_BUTTON_TEXT)]],
    resize_keyboard=True,
    input_field_placeholder="Enter word/phrase or select an option..."
)


# --- Helper Functions ---
def get_clue_and_translations(word: str) -> str:
    """
    Provides a phonetic clue (preferably IPA) and translations using the 'translate' library.
    """
    word_cleaned = word.strip().lower()
    if not word_cleaned:
        return "N/A (empty word)"

    # --- Phonetic Clue Part ---
    phonetic_clue_str = "Phonetic Clue: Not available."
    if ENG_TO_IPA_AVAILABLE:
        try:
            # Check for non-alphabetic characters that eng_to_ipa might struggle with
            if not re.fullmatch(r"[a-zA-Z']+", word_cleaned): # Allows letters and apostrophes
                logger.info(f"Word '{word_cleaned}' contains non-standard characters for IPA. Using basic clue.")
                vowels_ph = "aeiou"
                num_vowels_ph = sum(1 for char_ph in word_cleaned if char_ph in vowels_ph)
                first_l_ph = word_cleaned[0] if word_cleaned else '?'
                last_l_ph = word_cleaned[-1] if word_cleaned else '?'
                phonetic_clue_str = f"Basic: Starts '{first_l_ph}', ends '{last_l_ph}'. Vowels: {num_vowels_ph}."
            else:
                ipa_transcription = eng_to_ipa.convert(word_cleaned)
                if ipa_transcription == word_cleaned or '*' in ipa_transcription:
                    logger.info(f"eng_to_ipa could not find specific IPA for '{word_cleaned}'. Using basic clue.")
                    vowels_ph2 = "aeiou"
                    num_vowels_ph2 = sum(1 for char_ph2 in word_cleaned if char_ph2 in vowels_ph2)
                    first_l_ph2 = word_cleaned[0] if word_cleaned else '?'
                    last_l_ph2 = word_cleaned[-1] if word_cleaned else '?'
                    phonetic_clue_str = f"Basic: Starts '{first_l_ph2}', ends '{last_l_ph2}'. Vowels: {num_vowels_ph2}."
                else:
                    phonetic_clue_str = f"IPA: /{ipa_transcription}/"
        except Exception as e_ipa:
            logger.error(f"Error getting IPA for '{word_cleaned}': {e_ipa}")
            phonetic_clue_str = "Phonetic Clue: Error generating."
    else: # Basic clue if eng_to_ipa not available
        vowels_basic = "aeiou"
        num_vowels_basic = sum(1 for char_basic in word_cleaned if char_basic in vowels_basic)
        first_l_basic = word_cleaned[0] if word_cleaned else '?'
        last_l_basic = word_cleaned[-1] if word_cleaned else '?'
        phonetic_clue_str = f"Basic: Starts '{first_l_basic}', ends '{last_l_basic}'. Vowels: {num_vowels_basic}."

    # --- Translation Part ---
    translations_str = "\n\nTranslations:\n"
    if TRANSLATOR_AVAILABLE:
        target_languages = {
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'ru': 'Russian',
            # 'it': 'Italian', # Example: Add more as needed
            # 'pt': 'Portuguese'
        }
        translations_found = False
        any_errors = False
        for lang_code, lang_name in target_languages.items():
            try:
                # It's good practice to re-initialize Translator for each call
                # or if you expect many calls, handle potential state issues.
                # from_lang='en' helps guide the translator.
                translator = Translator(to_lang=lang_code, from_lang='en')
                translation_result = translator.translate(word_cleaned) # word_cleaned is the single word for translation

                if translation_result and translation_result.lower() != word_cleaned: # Check if translation is different
                    # Unescape HTML entities like &apos;
                    import html
                    translation_result = html.unescape(translation_result)
                    translations_str += f"- {lang_name}: {translation_result}\n"
                    translations_found = True
                # else: # Optional: log if no distinct translation
                    # logger.info(f"No distinct translation or empty result for '{word_cleaned}' to {lang_name}")
            except Exception as e_trans:
                logger.error(f"Error translating '{word_cleaned}' to {lang_name} using 'translate' lib: {e_trans}", exc_info=False)
                translations_str += f"- {lang_name}: Error\n"
                any_errors = True
        
        if not translations_found and not any_errors:
             translations_str += "Could not retrieve distinct translations or word is similar in these languages."
        elif not translations_found and any_errors:
            translations_str += "Could not retrieve translations due to errors."


    else:
        translations_str = "\n\nTranslations: (Feature disabled - 'translate' library not installed/found)"

    return f"{phonetic_clue_str}{translations_str}"


# --- Telegram Bot Handlers ---
async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if not job or not job.data or 'message_text' not in job.data:
         logger.warning(f"Job {job.name if job else 'N/A'} is missing data or message_text.")
         return
    try:
        message_text = job.data['message_text']
        chat_id = job.chat_id
        buttons = []

        # Delete button
        callback_data_delete = f"{CALLBACK_DELETE_REQUEST}{message_text}"
        if len(callback_data_delete.encode('utf-8')) <= 64:
            buttons.append(InlineKeyboardButton("🗑️ Delete Word", callback_data=callback_data_delete))
        else:
            logger.warning(f"Callback data for delete request too long for word: '{message_text}'.")

        # Clue/Translate button
        word_for_clue = message_text.split(' ')[0] if ' ' in message_text else message_text # Use first word for phrases
        word_for_clue_cleaned = re.sub(r'[^\w\s\'-]', '', word_for_clue).strip() # Clean for callback

        if word_for_clue_cleaned: # Only add button if there's a word to process
            callback_data_clue = f"{CALLBACK_CLUE_REQUEST}{word_for_clue_cleaned}"
            if len(callback_data_clue.encode('utf-8')) <= 64:
                buttons.append(InlineKeyboardButton("💡 Clue/Translate", callback_data=callback_data_clue))
            else:
                logger.warning(f"Callback data for clue/translate too long for word: '{word_for_clue_cleaned}'.")
        else:
            logger.info(f"No suitable word for clue/translate from '{message_text}'. Skipping button.")

        keyboard = InlineKeyboardMarkup([buttons]) if buttons else None # Buttons in one row
        await context.bot.send_message(chat_id=chat_id, text=f"🔔 Reminder: {message_text}", reply_markup=keyboard)
        logger.info(f"Sent reminder '{message_text}' to chat_id {chat_id}")
    except Exception as e:
        logger.error(f"Error sending reminder for job {job.name if job else 'N/A'}: {e}", exc_info=True)
        # Try to notify user about the error without crashing the job queue processing
        try:
            if job and job.chat_id:
                 await context.bot.send_message(chat_id=job.chat_id, text="Sorry, an error occurred sending one of your reminders.")
        except Exception as e_notify:
            logger.error(f"Could not notify user {job.chat_id if job else 'N/A'} about failed reminder: {e_notify}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome_text = (
        rf"Hi {user.mention_html()}! Send me an English word or short phrase to learn. "
        "I'll use Spaced Repetition to help you remember it.\n\n"
        f"Use the '{LEARNING_DICT_BUTTON_TEXT}' button below to see your learning list."
    )
    await update.message.reply_html(welcome_text, reply_markup=REPLY_KEYBOARD)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Unlock Effortless English Vocabulary Growth!\n\n"
        "This bot uses **Spaced Repetition (SRS)** to help you learn and *remember* new English words/phrases. "
        "SRS schedules reminders at increasing intervals, optimizing memory retention.\n\n"
        "**How it works:**\n"
        "1. **Send a Word:** Type any new English word or short phrase.\n"
        "2. **Automatic Reminders:** I'll schedule reminders (e.g., 1 min, 1 day, 2 days...). \n"
        "3. **Recall & Reinforce:** Actively recall the meaning when you get a reminder.\n\n"
        "**Features:**\n"
        f"- **`{LEARNING_DICT_BUTTON_TEXT}`:** View words, reminders left, and next due time.\n"
        "- **Delete Words:** '🗑️ Delete Word' button on reminders.\n"
        "- **Clue & Translate:** Tap '💡 Clue/Translate' on a reminder for a phonetic hint (often IPA for the first word) and translations to popular languages.\n\n"
        "**Tips:** Add words promptly. Keep phrases short (2-5 words for best results).\n\n"
        "Happy learning! 🚀\n\n"
        "Other commands:\n"
        "/start - Show welcome message."
    )
    await update.message.reply_text(help_text, reply_markup=REPLY_KEYBOARD, parse_mode='Markdown')
    logger.info(f"Sent detailed help message to {update.effective_user.username}")


async def show_dictionary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not context.job_queue:
        logger.warning(f"JobQueue not found for chat {chat_id} during dictionary fetch.")
        await update.message.reply_text("Sorry, I cannot access the reminder schedule right now.", reply_markup=REPLY_KEYBOARD)
        return

    current_jobs = context.job_queue.jobs()
    now = datetime.datetime.now() # Get current time once

    active_word_jobs = {} # {word: [job1, job2,...]}
    for job in current_jobs:
        if job and job.chat_id == chat_id and job.data and 'message_text' in job.data and not job.removed:
            message_text = job.data['message_text']
            active_word_jobs.setdefault(message_text, []).append(job)

    if not active_word_jobs:
        response_text = "Your learning dictionary is currently empty. Send me a message to start learning!"
    else:
        response_text = "📚 Your Learning Dictionary:\n\n"
        for message_text in sorted(active_word_jobs.keys()): # Sort for consistent order
            jobs_for_word = active_word_jobs[message_text]
            reminders_left = len(jobs_for_word)
            
            # Find the earliest next_run_time among valid jobs for this word
            next_reminder_datetime_obj = min(
                (j.next_run_time for j in jobs_for_word if j.next_run_time), 
                default=None
            )
            
            next_reminder_info_str = "N/A"
            if next_reminder_datetime_obj:
                aware_now = now.astimezone(next_reminder_datetime_obj.tzinfo) # Make 'now' timezone-aware
                time_diff = next_reminder_datetime_obj - aware_now
                if time_diff.total_seconds() > 0: # Only if it's in the future
                    days = time_diff.total_seconds() / (60 * 60 * 24)
                    if days < (1/24): # Less than an hour
                        minutes = int(round(days * 24 * 60))
                        next_reminder_info_str = f"in ~{minutes} min"
                    elif days < 1: # Less than a day, show hours
                        hours = int(round(days * 24))
                        next_reminder_info_str = f"in ~{hours} hr(s)"
                    else: # Show days
                        next_reminder_info_str = f"in ~{int(round(days))} day(s)"
                else: # If somehow it's in the past but job not removed, or just ran
                    next_reminder_info_str = "Soon/Past"
            response_text += f"- {message_text} (Left: {reminders_left}, Next: {next_reminder_info_str})\n"
        response_text += "\nThese are the items you are currently learning."
    await update.message.reply_text(response_text, reply_markup=REPLY_KEYBOARD)
    logger.info(f"Displayed dictionary for chat_id {chat_id}. Items: {len(active_word_jobs)}")


async def schedule_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_message = update.message.text.strip()
    message_id = update.message.message_id

    if not user_message:
        logger.info(f"Received empty message from chat {chat_id}. Ignoring.")
        return

    logger.info(f"Attempting to schedule: '{user_message}' from {update.effective_user.username} in chat {chat_id}")

    if not context.job_queue:
        logger.warning(f"JobQueue not found for chat {chat_id}. Reminders cannot be scheduled.")
        await update.message.reply_text("Sorry, I cannot schedule reminders right now.", reply_markup=REPLY_KEYBOARD)
        return

    # Check for existing pending jobs for this exact message to prevent duplicates
    existing_jobs_count = sum(1 for job in context.job_queue.jobs() if job and job.chat_id == chat_id and job.data and job.data.get('message_text') == user_message and not job.removed)
    if existing_jobs_count > 0:
        logger.info(f"Message '{user_message}' already has {existing_jobs_count} pending reminders for chat {chat_id}.")
        await update.message.reply_text(f"ℹ️ '{user_message}' is already in your learning dictionary with {existing_jobs_count} reminders pending.", reply_markup=REPLY_KEYBOARD)
        return

    job_data = {'message_text': user_message, 'original_message_id': message_id}
    jobs_scheduled = 0
    first_interval_minutes = None

    for i, interval_seconds in enumerate(REMINDER_INTERVALS_SECONDS):
        safe_message_part = re.sub(r'\W+', '_', user_message)[:20] # Make message safe for name, truncate
        job_name = f"reminder_{chat_id}_{message_id}_{safe_message_part}_{i}" # Unique job name

        context.job_queue.run_once(
            send_reminder,
            when=datetime.timedelta(seconds=interval_seconds),
            chat_id=chat_id,
            data=job_data.copy(), # Use copy to avoid modification issues
            name=job_name
        )
        jobs_scheduled += 1
        if jobs_scheduled == 1:
             first_interval_minutes = int(interval_seconds / 60)
        logger.info(f"Scheduled job '{job_name}' for chat {chat_id} to run in {interval_seconds} seconds.")
    
    if jobs_scheduled > 0:
        first_reminder_text = f"First reminder in approximately {first_interval_minutes} minutes." if first_interval_minutes is not None else "First reminder scheduled."
        await update.message.reply_text(f"✅ Added '{user_message}' to your learning dictionary!\n{first_reminder_text} Total {jobs_scheduled} reminders scheduled.", reply_markup=REPLY_KEYBOARD)
    else: # Should not happen if REMINDER_INTERVALS_SECONDS is not empty
         logger.warning(f"No jobs were scheduled for '{user_message}' in chat {chat_id}, although scheduling was attempted.")
         await update.message.reply_text("Couldn't schedule any reminders for some reason. Please try again.", reply_markup=REPLY_KEYBOARD)


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer() # Acknowledge button press
    callback_data = query.data
    chat_id = query.message.chat_id
    message_id_of_button_message = query.message.message_id
    logger.info(f"Callback received from chat {chat_id}: {callback_data}")

    try:
        if callback_data.startswith(CALLBACK_DELETE_REQUEST):
            word_to_delete = callback_data[len(CALLBACK_DELETE_REQUEST):]
            logger.info(f"Deletion requested for '{word_to_delete}' in chat {chat_id}")
            confirm_callback = f"{CALLBACK_DELETE_CONFIRM}{word_to_delete}"
            cancel_callback = f"{CALLBACK_DELETE_CANCEL}{word_to_delete}"

            if len(confirm_callback.encode('utf-8')) > 64 or len(cancel_callback.encode('utf-8')) > 64:
                logger.error(f"Callback data too long for delete confirm/cancel buttons for word: '{word_to_delete}'.")
                await query.edit_message_text(f"{query.message.text}\n\n⚠️ Error: Word too long for confirmation buttons.", reply_markup=None)
                return
            
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Yes, Delete", callback_data=confirm_callback),
                InlineKeyboardButton("❌ No, Keep", callback_data=cancel_callback)
            ]])
            await query.edit_message_text(
                text=f"❓ Are you sure you want to remove \"{word_to_delete}\" from your learning dictionary?\n\n(Original reminder: {query.message.text})",
                reply_markup=keyboard
            )

        elif callback_data.startswith(CALLBACK_DELETE_CONFIRM):
            word_to_delete = callback_data[len(CALLBACK_DELETE_CONFIRM):]
            logger.info(f"Deletion confirmed for '{word_to_delete}' in chat {chat_id}")
            if not context.job_queue:
                logger.warning(f"JobQueue not found during delete confirmation for chat {chat_id}.")
                await query.edit_message_text("❌ Error: Could not access the schedule to delete.", reply_markup=None)
                return

            removed_count = 0
            # Iterate over a copy of jobs list if modifying (schedule_removal modifies it)
            for job in list(context.job_queue.jobs()): 
                if job and job.chat_id == chat_id and job.data and job.data.get('message_text') == word_to_delete and not job.removed:
                    try:
                        job.schedule_removal()
                        removed_count +=1
                        logger.info(f"Scheduled job '{job.name}' for removal (word: '{word_to_delete}')")
                    except Exception as e_remove:
                        logger.error(f"Error scheduling job {job.name} for removal: {e_remove}")
            
            if removed_count > 0:
                confirmation_text = f"✅ Removed \"{word_to_delete}\" ({removed_count} reminders cancelled) from your learning dictionary."
            else:
                confirmation_text = f"⚠️ No active reminders found for \"{word_to_delete}\", or an error occurred during removal."
            await query.edit_message_text(text=confirmation_text, reply_markup=None)

        elif callback_data.startswith(CALLBACK_DELETE_CANCEL):
            word_to_delete = callback_data[len(CALLBACK_DELETE_CANCEL):]
            logger.info(f"Deletion cancelled for '{word_to_delete}' in chat {chat_id}")
            original_reminder_text_match = re.search(r"\(Original reminder: (.*)\)", query.message.text, re.DOTALL)
            original_text = original_reminder_text_match.group(1).strip() if original_reminder_text_match else f"🔔 Reminder: {word_to_delete}"
            await query.edit_message_text(f"{original_text}\n\n❌ Deletion cancelled.", reply_markup=None)
        
        elif callback_data.startswith(CALLBACK_CLUE_REQUEST):
            word_for_clue_from_callback = callback_data[len(CALLBACK_CLUE_REQUEST):]
            logger.info(f"Clue/Translate requested for '{word_for_clue_from_callback}' in chat {chat_id}")
            
            clue_and_translation_text = get_clue_and_translations(word_for_clue_from_callback) 
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"💡 Info for \"{word_for_clue_from_callback}\":\n{clue_and_translation_text}",
                reply_to_message_id=message_id_of_button_message # Reply to the original reminder message
            )
        else:
            logger.warning(f"Unknown callback data pattern: {callback_data}")
            await query.edit_message_text("😕 Unknown button action.", reply_markup=None)
    except Exception as e_cb_handler:
        logger.error(f"Error in button_callback_handler for data '{callback_data}': {e_cb_handler}", exc_info=True)
        try:
             await query.edit_message_text("😕 Sorry, an error occurred processing this action.", reply_markup=None)
        except Exception as e_edit_fail:
            logger.error(f"Could not edit message {message_id_of_button_message} in chat {chat_id} to report callback error: {e_edit_fail}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)


# --- Main Bot Logic ---
def main() -> None:
    """Start the bot."""
    logger.info(f"Starting bot. Using token: {BOT_TOKEN[:8]}...{BOT_TOKEN[-4:] if len(BOT_TOKEN) > 12 else ''}")
    logger.info("Building application...")

    application = Application.builder().token(BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    # Handler for the "Learning Dictionary" button
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(f'^{re.escape(LEARNING_DICT_BUTTON_TEXT)}$'),
        show_dictionary_command
    ))

    # Handler for OTHER text messages (for scheduling reminders)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.Regex(f'^{re.escape(LEARNING_DICT_BUTTON_TEXT)}$'),
        schedule_reminders
    ))

    # Handler for Inline Keyboard Button Clicks
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    # Register the error handler (should generally be last or near last)
    application.add_error_handler(error_handler)

    logger.info("Bot polling started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES) # Ensure all update types are processed

    logger.info("Bot stopped.")


if __name__ == '__main__':
    # This initial basicConfig is for library import checks before main logger is set
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - Initial %(levelname)s - %(message)s')
    main()
