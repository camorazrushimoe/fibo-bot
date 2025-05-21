# Add near the top of your script
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

# --- NEW: Attempt to import eng_to_ipa ---
try:
    import eng_to_ipa
    ENG_TO_IPA_AVAILABLE = True
    logger_init = logging.getLogger(__name__) # Use a temporary logger if main one not set up
    logger_init.info("eng_to_ipa library found and imported successfully.")
except ImportError:
    ENG_TO_IPA_AVAILABLE = False
    logger_init = logging.getLogger(__name__)
    logger_init.warning("eng_to_ipa library not found. Phonetic clues will be very basic. Run 'pip install eng_to_ipa'")
# --- END NEW ---


## CTRL + C to stop
## sudo systemctl restart telegram-bot.service


# --- Configuration ---
BOT_TOKEN = "yout token here" # REPLACE THIS

if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    logging.critical("FATAL: Bot token is not set in the script! Please replace 'YOUR_BOT_TOKEN_HERE'.")
    exit("Bot token not configured.")

REMINDER_INTERVALS_SECONDS = [
    60, 1440 * 60, 2880 * 60, 5760 * 60, 11520 * 60, 17280 * 60,
    23040 * 60, 28800 * 60, 37440 * 60, 48960 * 60, 69120 * 60,
    86440 * 60, 115200 * 60, 144000 * 60
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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__) # Now the main logger is configured

# --- MODIFIED: Function for phonetic clue using eng_to_ipa ---
def get_phonetic_clue(word: str) -> str:
    """
    Provides a phonetic clue, preferably using eng_to_ipa.
    Falls back to simpler clues if the library is unavailable or conversion fails.
    """
    word_cleaned = word.strip().lower()
    if not word_cleaned:
        return "N/A (empty word)"
    
    # eng_to_ipa works best with single words.
    # If it's a phrase, you might process the first word or each word.
    # The callback_data for clue request already sends the first word if it's a phrase.
    # So, 'word_cleaned' here should generally be a single word.

    if ENG_TO_IPA_AVAILABLE:
        try:
            # Check if the word contains non-alphabetic characters (excluding apostrophe for contractions)
            # that eng_to_ipa might struggle with.
            # This regex allows letters and apostrophes.
            if not re.fullmatch(r"[a-zA-Z']+", word_cleaned):
                 logger.info(f"Word '{word_cleaned}' contains non-standard characters for IPA. Falling back.")
                 # Fall through to basic clue if it has numbers or special symbols
            else:
                ipa_transcription = eng_to_ipa.convert(word_cleaned)
                # eng_to_ipa returns the original word if it cannot find a transcription
                if ipa_transcription == word_cleaned or '*' in ipa_transcription: 
                    logger.info(f"eng_to_ipa could not find specific IPA for '{word_cleaned}'. Fallback.")
                else:
                    return f"IPA: /{ipa_transcription}/"
        except Exception as e:
            logger.error(f"Error getting IPA for '{word_cleaned}' using eng_to_ipa: {e}")
            # Fall through to basic clue on any exception during IPA conversion
    
    # Fallback simple clues if eng_to_ipa not available, failed, or word not suitable:
    logger.info(f"Providing basic clue for '{word_cleaned}'.")
    vowels = "aeiou"
    num_vowels = sum(1 for char in word_cleaned if char in vowels)
    first_letter = word_cleaned[0] if word_cleaned else '?'
    last_letter = word_cleaned[-1] if word_cleaned else '?'
    
    if ' ' in word_cleaned: # Should not happen often here due to pre-processing
        return f"This is a phrase. Try to pronounce each word. First word starts with '{word_cleaned.split()[0][0]}'."
    
    if num_vowels == 0 and len(word_cleaned) > 0:
        return f"Starts with '{first_letter}', ends with '{last_letter}'. No standard vowel letters detected."
    else:
        return f"Starts with '{first_letter}', ends with '{last_letter}'. It has {num_vowels} vowel letter(s)."
# --- END MODIFIED ---


async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the reminder message back to the user with delete and clue options."""
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
            logger.warning(f"Callback data for delete request too long for word: '{message_text}'. Skipping delete button.")

        # Clue button - get first word for clue if it's a phrase
        word_for_clue = message_text.split(' ')[0] if ' ' in message_text else message_text
        word_for_clue_cleaned = re.sub(r'[^\w\s\'-]', '', word_for_clue).strip() # Clean for callback data

        if word_for_clue_cleaned: # Only add clue button if there's a word to process
            callback_data_clue = f"{CALLBACK_CLUE_REQUEST}{word_for_clue_cleaned}"
            if len(callback_data_clue.encode('utf-8')) <= 64:
                buttons.append(InlineKeyboardButton("💡 Clue", callback_data=callback_data_clue))
            else:
                logger.warning(f"Callback data for clue request too long for word: '{word_for_clue_cleaned}'. Skipping clue button.")
        else:
            logger.info(f"No suitable word for clue from '{message_text}'. Skipping clue button.")


        keyboard = None
        if buttons:
            keyboard = InlineKeyboardMarkup([buttons])

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔔 Reminder: {message_text}",
            reply_markup=keyboard
        )
        logger.info(f"Sent reminder '{message_text}' to chat_id {chat_id}")

    except KeyError:
        logger.error(f"KeyError accessing data for job {job.name if job else 'N/A'}. Data: {job.data if job else 'N/A'}", exc_info=True)
    except Exception as e:
        logger.error(f"Error sending reminder for job {job.name if job else 'N/A'}: {e}", exc_info=True)
        try:
            if job and job.chat_id:
                 await context.bot.send_message(chat_id=job.chat_id, text="Sorry, I encountered an error sending one of your reminders.")
        except Exception:
            logger.error(f"Could not notify user {job.chat_id if job else 'N/A'} about the failed reminder.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome_text = (
        rf"Hi {user.mention_html()}! Send me a message (word or short phrase) "
        "and I'll remind you about it using spaced repetition.\n\n"
        "Try to send 2-3 words per message for best results.\n\n"
        f"Use the '{LEARNING_DICT_BUTTON_TEXT}' button below to see what's scheduled."
    )
    await update.message.reply_html(welcome_text, reply_markup=REPLY_KEYBOARD)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Unlock Effortless English Vocabulary Growth!\n\n"
        "This bot helps you learn and *remember* new English words and phrases using the powerful "
        "**Spaced Repetition System (SRS)**. SRS is a scientifically proven method that schedules "
        "reminders at increasing intervals, just when you're about to forget, making learning super efficient.\n\n"
        "**How it works:**\n"
        "1. **Send a Word:** Type any new English word or short phrase you want to learn and send it to me.\n"
        "2. **Automatic Reminders:** I'll schedule a series of reminders for that word. The first few will be soon, "
        "then the gaps get longer (e.g., 1 min, 1 day, 2 days, 4 days...). This is SRS in action!\n"
        "3. **Recall & Reinforce:** When you get a reminder, try to recall the word's meaning. This active recall "
        "strengthens your memory.\n\n"
        "**Features:**\n"
        f"- **`{LEARNING_DICT_BUTTON_TEXT}`:** Tap this button to see all words you're currently learning, "
        "how many reminders are left, and when the next one is due.\n"
        "- **Delete Words:** On any reminder message, you'll see a '🗑️ Delete Word' button.\n"
        "- **Get Clues:** Tap '💡 Clue' on a reminder for a phonetic hint (often IPA) about the word.\n\n"
        "**Tips for Best Results:**\n"
        "- Add words as soon as you encounter them.\n"
        "- Keep phrases short (2-5 words).\n\n"
        "Master vocabulary and boost your English fluency! 🚀\n\n"
        "Other commands:\n"
        "/start - Show welcome message."
    )
    await update.message.reply_text(help_text, reply_markup=REPLY_KEYBOARD, parse_mode='Markdown')
    logger.info(f"Sent detailed help message to {update.effective_user.username} in chat {update.effective_chat.id}")

async def show_dictionary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not context.job_queue:
        logger.warning(f"JobQueue not found for chat {chat_id} during dictionary fetch.")
        await update.message.reply_text("Sorry, I cannot access the schedule right now.", reply_markup=REPLY_KEYBOARD)
        return

    current_jobs = context.job_queue.jobs()
    now = datetime.datetime.now()
    active_word_jobs = {}
    for job in current_jobs:
        if job and job.chat_id == chat_id and job.data and 'message_text' in job.data and not job.removed:
            message_text = job.data['message_text']
            if message_text not in active_word_jobs:
                active_word_jobs[message_text] = []
            active_word_jobs[message_text].append(job)

    if not active_word_jobs:
        response_text = "Your learning dictionary is empty. Send a message to start!"
    else:
        response_text = "📚 Your Learning Dictionary:\n\n"
        for message_text in sorted(active_word_jobs.keys()):
            jobs_for_word = active_word_jobs[message_text]
            reminders_left = len(jobs_for_word)
            next_reminder_datetime_obj = None
            if jobs_for_word:
                valid_jobs_with_next_run = [j for j in jobs_for_word if j.next_run_time]
                if valid_jobs_with_next_run:
                    next_job = min(valid_jobs_with_next_run, key=lambda j: j.next_run_time)
                    next_reminder_datetime_obj = next_job.next_run_time

            next_reminder_info_str = "N/A"
            if next_reminder_datetime_obj:
                aware_now = now.astimezone(next_reminder_datetime_obj.tzinfo)
                time_diff = next_reminder_datetime_obj - aware_now
                if time_diff.total_seconds() > 0:
                    days_until_next = time_diff.total_seconds() / (60 * 60 * 24)
                    if days_until_next < (1/24):
                        minutes_until_next = days_until_next * 24 * 60
                        next_reminder_info_str = f"in ~{int(round(minutes_until_next))} min"
                    elif days_until_next < 1:
                        hours_until_next = days_until_next * 24
                        next_reminder_info_str = f"in ~{int(round(hours_until_next))} hr(s)"
                    else:
                        next_reminder_info_str = f"in ~{int(round(days_until_next))} day(s)"
                else:
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
        logger.info(f"Empty message from chat {chat_id}. Ignoring.")
        return
    logger.info(f"Scheduling: '{user_message}' from {update.effective_user.username} in chat {chat_id}")
    if not context.job_queue:
        logger.warning(f"JobQueue not found for chat {chat_id}.")
        await update.message.reply_text("Sorry, I cannot schedule reminders now.", reply_markup=REPLY_KEYBOARD)
        return

    current_jobs = context.job_queue.jobs()
    existing_jobs_count = sum(1 for job in current_jobs if job and job.chat_id == chat_id and job.data and job.data.get('message_text') == user_message and not job.removed)
    if existing_jobs_count > 0:
        await update.message.reply_text(f"ℹ️ '{user_message}' is already in your dictionary with {existing_jobs_count} reminders.", reply_markup=REPLY_KEYBOARD)
        return

    job_data = {'message_text': user_message, 'original_message_id': message_id}
    jobs_scheduled = 0
    first_interval_minutes = None
    for interval_seconds in REMINDER_INTERVALS_SECONDS:
        safe_message_part = re.sub(r'\W+', '_', user_message)[:20]
        job_name = f"reminder_{chat_id}_{message_id}_{safe_message_part}_{interval_seconds}s"
        context.job_queue.run_once(send_reminder, datetime.timedelta(seconds=interval_seconds), chat_id=chat_id, data=job_data.copy(), name=job_name)
        jobs_scheduled += 1
        if jobs_scheduled == 1: first_interval_minutes = int(interval_seconds / 60)
    if jobs_scheduled > 0:
        first_reminder_text = f"First reminder in ~{first_interval_minutes} min." if first_interval_minutes is not None else "First scheduled."
        await update.message.reply_text(f"✅ Added '{user_message}'!\n{first_reminder_text} Total {jobs_scheduled} reminders.", reply_markup=REPLY_KEYBOARD)
    else:
        await update.message.reply_text("Couldn't schedule reminders.", reply_markup=REPLY_KEYBOARD)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    chat_id = query.message.chat_id
    message_id = query.message.message_id # Message ID of the message with the button
    logger.info(f"Callback from chat {chat_id}: {callback_data}")

    try:
        if callback_data.startswith(CALLBACK_DELETE_REQUEST):
            word_to_delete = callback_data[len(CALLBACK_DELETE_REQUEST):]
            logger.info(f"Deletion requested for '{word_to_delete}' in chat {chat_id}")
            confirm_callback = f"{CALLBACK_DELETE_CONFIRM}{word_to_delete}"
            cancel_callback = f"{CALLBACK_DELETE_CANCEL}{word_to_delete}"
            if len(confirm_callback.encode('utf-8')) > 64 or len(cancel_callback.encode('utf-8')) > 64:
                logger.error(f"Callback data too long for delete confirm/cancel: '{word_to_delete}'.")
                await query.edit_message_text(f"{query.message.text}\n\n⚠️ Error: Word too long for confirm buttons.", reply_markup=None)
                return
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes, Delete", callback_data=confirm_callback), InlineKeyboardButton("❌ No, Keep", callback_data=cancel_callback)]])
            await query.edit_message_text(f"❓ Remove \"{word_to_delete}\"?\n\n(Original: {query.message.text})", reply_markup=keyboard)

        elif callback_data.startswith(CALLBACK_DELETE_CONFIRM):
            word_to_delete = callback_data[len(CALLBACK_DELETE_CONFIRM):]
            logger.info(f"Deletion confirmed for '{word_to_delete}' in chat {chat_id}")
            if not context.job_queue:
                logger.warning(f"JobQueue not found for delete confirm in chat {chat_id}.")
                await query.edit_message_text("❌ Error: Cannot access schedule.", reply_markup=None)
                return
            jobs_removed_count = 0
            jobs_to_remove = [job for job in context.job_queue.jobs() if job and job.chat_id == chat_id and job.data and job.data.get('message_text') == word_to_delete and not job.removed]
            if not jobs_to_remove:
                confirmation_text = f"⚠️ No active reminders for \"{word_to_delete}\"."
            else:
                for job in jobs_to_remove:
                    try:
                        job.schedule_removal()
                        jobs_removed_count += 1
                    except Exception as e:
                        logger.error(f"Error removing job {job.name}: {e}", exc_info=True)
                confirmation_text = f"✅ Removed \"{word_to_delete}\" ({jobs_removed_count} reminders cancelled)." if jobs_removed_count > 0 else f"❌ Error removing \"{word_to_delete}\"."
            await query.edit_message_text(text=confirmation_text, reply_markup=None)

        elif callback_data.startswith(CALLBACK_DELETE_CANCEL):
            word_to_delete = callback_data[len(CALLBACK_DELETE_CANCEL):]
            logger.info(f"Deletion cancelled for '{word_to_delete}' in chat {chat_id}")
            original_reminder_text_match = re.search(r"\(Original: (.*)\)", query.message.text, re.DOTALL)
            original_text = original_reminder_text_match.group(1).strip() if original_reminder_text_match else f"🔔 Reminder: {word_to_delete}"
            await query.edit_message_text(f"{original_text}\n\n❌ Deletion cancelled.", reply_markup=None)
        
        elif callback_data.startswith(CALLBACK_CLUE_REQUEST):
            word_for_clue_from_callback = callback_data[len(CALLBACK_CLUE_REQUEST):]
            logger.info(f"Clue requested for '{word_for_clue_from_callback}' in chat {chat_id}")
            
            clue_text = get_phonetic_clue(word_for_clue_from_callback) # Use the function with eng_to_ipa
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"💡 Clue for \"{word_for_clue_from_callback}\":\n{clue_text}",
                reply_to_message_id=message_id
            )
        else:
            logger.warning(f"Unknown callback data: {callback_data}")
            await query.edit_message_text("😕 Unknown action.", reply_markup=None)
    except Exception as e:
        logger.error(f"Error in button_callback_handler '{callback_data}': {e}", exc_info=True)
        try:
            await query.edit_message_text("😕 Error processing action.", reply_markup=None)
        except Exception as inner_e:
            logger.error(f"Could not edit message {message_id} to report callback error: {inner_e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)

def main() -> None:
    logger.info(f"Using bot token: {BOT_TOKEN[:8]}...{BOT_TOKEN[-4:]}")
    logger.info("Starting bot application build...")
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(f'^{re.escape(LEARNING_DICT_BUTTON_TEXT)}$'), show_dictionary_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(f'^{re.escape(LEARNING_DICT_BUTTON_TEXT)}$'), schedule_reminders))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    application.add_error_handler(error_handler)

    logger.info("Bot polling started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot stopped.")

if __name__ == '__main__':
    main()
