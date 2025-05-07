# Add near the top of your script
import os
import logging
import datetime # Already present, but crucial for Feature 1
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
import re # Needed for Regex filter

## CTRL + C to stop
## sudo systemctl restart telegram-bot.service


# --- Configuration ---

# --- MODIFICATION START: Define Token Directly ---
# IMPORTANT: Replace "YOUR_BOT_TOKEN_HERE" with your actual Telegram Bot Token
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    logging.critical("FATAL: Bot token is not set in the script! Please replace 'YOUR_BOT_TOKEN_HERE'.")
    exit("Bot token not configured.")
# --- MODIFICATION END ---


REMINDER_INTERVALS_SECONDS = [
    60,         # 1 minute
    1440 * 60,      # 1 day
    2880 * 60,      # 2 days
    5760 * 60,      # 4 days
    11520 * 60,     # 8 days
    17280 * 60,     # 12 days
    23040 * 60,     # 16 days
    28800 * 60,     # 20 days
    37440 * 60,     # 26 days
    48960 * 60,     # 34 days
    69120 * 60,     # 48 days
    86440 * 60,     # 60 days
    115200 * 60,    # 80 days
    144000 * 60     # 100 days
]

# Callback data prefixes for inline buttons
CALLBACK_DELETE_REQUEST = "del_req:"
CALLBACK_DELETE_CONFIRM = "del_conf:"
CALLBACK_DELETE_CANCEL = "del_can:"

# --- End Configuration ---

# --- Define the persistent keyboard ---
LEARNING_DICT_BUTTON_TEXT = "📚 Learning Dictionary"
REPLY_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(LEARNING_DICT_BUTTON_TEXT)]],
    resize_keyboard=True,
    input_field_placeholder="Enter word/phrase or select an option..."
)
# --- End Keyboard Definition ---


# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Callback function for the scheduled job ---
async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the reminder message back to the user with a delete option."""
    job = context.job
    if not job or not job.data or 'message_text' not in job.data:
         logger.warning(f"Job {job.name if job else 'N/A'} is missing data or message_text.")
         return

    try:
        message_text = job.data['message_text']
        chat_id = job.chat_id

        callback_data_delete = f"{CALLBACK_DELETE_REQUEST}{message_text}"
        keyboard = None
        if len(callback_data_delete.encode('utf-8')) <= 64:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🗑️ Delete Word", callback_data=callback_data_delete)
            ]])
        else:
            logger.warning(f"Callback data for delete request too long for word: '{message_text}'. Skipping delete button.")

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


# --- Bot Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and shows the persistent keyboard."""
    user = update.effective_user
    welcome_text = (
        rf"Hi {user.mention_html()}! Send me a message (word or short phrase) "
        "and I'll remind you about it using spaced repetition.\n\n"
        "Try to send 2-3 words per message for best results.\n\n"
        f"Use the '{LEARNING_DICT_BUTTON_TEXT}' button below to see what's scheduled."
    )
    await update.message.reply_html(
        welcome_text,
        reply_markup=REPLY_KEYBOARD
    )

# --- MODIFIED help_command for Feature 2 ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a more descriptive help message."""
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
        "- **Delete Words:** On any reminder message, you'll see a '🗑️ Delete Word' button. Use this if you've "
        "mastered a word or added it by mistake.\n\n"
        "**Tips for Best Results:**\n"
        "- Add words as soon as you encounter them.\n"
        "- Keep phrases short (2-5 words).\n"
        "- Regularly check your learning dictionary.\n\n"
        "Master vocabulary and boost your English fluency! Happy learning! 🚀\n\n"
        "Other commands:\n"
        "/start - Show welcome message."
    )
    await update.message.reply_text(help_text, reply_markup=REPLY_KEYBOARD, parse_mode='Markdown')
    logger.info(f"Sent detailed help message to {update.effective_user.username} in chat {update.effective_chat.id}")
# --- END MODIFIED help_command ---

# --- MODIFIED show_dictionary_command for Feature 1 ---
async def show_dictionary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Learning Dictionary' button press, showing reminders left and next due time."""
    chat_id = update.effective_chat.id

    if not context.job_queue:
        logger.warning(f"JobQueue not found in context for chat {chat_id} during dictionary fetch.")
        await update.message.reply_text(
            "Sorry, I cannot access the reminder schedule right now.",
            reply_markup=REPLY_KEYBOARD
        )
        return

    current_jobs = context.job_queue.jobs()
    now = datetime.datetime.now() # Get current time once

    # Group jobs by message_text
    active_word_jobs = {} # {word: [job1, job2,...]}
    for job in current_jobs:
        if job and job.chat_id == chat_id and job.data and 'message_text' in job.data and not job.removed:
            message_text = job.data['message_text']
            if message_text not in active_word_jobs:
                active_word_jobs[message_text] = []
            active_word_jobs[message_text].append(job)

    if not active_word_jobs:
        response_text = "Your learning dictionary is currently empty. Send me a message to start learning!"
    else:
        response_text = "📚 Your Learning Dictionary:\n\n"
        # Sort by message_text for consistent output
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
                # Make 'now' timezone-aware matching the job's timezone
                aware_now = now.astimezone(next_reminder_datetime_obj.tzinfo)
                time_diff = next_reminder_datetime_obj - aware_now

                if time_diff.total_seconds() > 0: # Only if it's in the future
                    days_until_next = time_diff.total_seconds() / (60 * 60 * 24)
                    if days_until_next < (1/24): # Less than an hour
                        minutes_until_next = days_until_next * 24 * 60
                        next_reminder_info_str = f"in ~{int(round(minutes_until_next))} min"
                    elif days_until_next < 1: # Less than a day, show hours
                        hours_until_next = days_until_next * 24
                        next_reminder_info_str = f"in ~{int(round(hours_until_next))} hr(s)"
                    else: # Show days
                        next_reminder_info_str = f"in ~{int(round(days_until_next))} day(s)"
                else: # If somehow it's in the past but job not removed, or just ran
                    next_reminder_info_str = "Soon/Past"
            
            response_text += f"- {message_text} (Reminders left: {reminders_left}, Next: {next_reminder_info_str})\n"
        response_text += "\nThese are the items you are currently learning."

    await update.message.reply_text(response_text, reply_markup=REPLY_KEYBOARD)
    logger.info(f"Displayed dictionary for chat_id {chat_id}. Items: {len(active_word_jobs)}")
# --- END MODIFIED show_dictionary_command ---


# --- Message Handler ---
async def schedule_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Schedules reminders for the user's message."""
    chat_id = update.effective_chat.id
    user_message = update.message.text.strip()
    message_id = update.message.message_id

    if not user_message:
        logger.info(f"Received empty message from chat {chat_id}. Ignoring.")
        return

    logger.info(f"Received message id {message_id} from {update.effective_user.username} in chat {chat_id} for scheduling: '{user_message}'")

    if not context.job_queue:
        logger.warning(f"JobQueue not found in context for chat {chat_id}. Reminders cannot be scheduled.")
        await update.message.reply_text(
            "Sorry, I cannot schedule reminders right now.",
            reply_markup=REPLY_KEYBOARD
        )
        return

    current_jobs = context.job_queue.jobs()
    existing_jobs_count = 0
    for job in current_jobs:
        if job and job.chat_id == chat_id and job.data and job.data.get('message_text') == user_message and not job.removed:
            existing_jobs_count += 1

    if existing_jobs_count > 0:
        logger.info(f"Message '{user_message}' already has {existing_jobs_count} pending reminders for chat {chat_id}.")
        await update.message.reply_text(
            f"ℹ️ '{user_message}' is already in your learning dictionary with {existing_jobs_count} reminders pending.",
            reply_markup=REPLY_KEYBOARD
        )
        return

    job_data = {'message_text': user_message, 'original_message_id': message_id}
    jobs_scheduled = 0
    first_interval_minutes = None

    for interval_seconds in REMINDER_INTERVALS_SECONDS:
        safe_message_part = re.sub(r'\W+', '_', user_message)[:20]
        job_name = f"reminder_{chat_id}_{message_id}_{safe_message_part}_{interval_seconds}s"

        context.job_queue.run_once(
            send_reminder,
            when=datetime.timedelta(seconds=interval_seconds),
            chat_id=chat_id,
            data=job_data.copy(),
            name=job_name
        )
        jobs_scheduled += 1
        if jobs_scheduled == 1:
             first_interval_minutes = int(interval_seconds / 60)
        logger.info(f"Scheduled job '{job_name}' for chat {chat_id} to run in {interval_seconds} seconds.")

    if jobs_scheduled > 0:
        first_reminder_text = f"First reminder in about {first_interval_minutes} minutes." if first_interval_minutes is not None else "First reminder scheduled."
        await update.message.reply_text(
            f"✅ Added '{user_message}' to your learning dictionary!\n"
            f"{first_reminder_text} "
            f"Total {jobs_scheduled} reminders scheduled.",
            reply_markup=REPLY_KEYBOARD
        )
    else:
         logger.warning(f"No jobs were scheduled for '{user_message}' in chat {chat_id}.")
         await update.message.reply_text(
             "Couldn't schedule any reminders. Please try again.",
             reply_markup=REPLY_KEYBOARD
        )

# --- Handler for Inline Button Callbacks ---
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inline keyboard button presses for deletion."""
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    logger.info(f"Received callback query from chat {chat_id} with data: {callback_data}")

    try:
        if callback_data.startswith(CALLBACK_DELETE_REQUEST):
            word_to_delete = callback_data[len(CALLBACK_DELETE_REQUEST):]
            logger.info(f"Deletion requested for word '{word_to_delete}' in chat {chat_id}")

            confirm_callback = f"{CALLBACK_DELETE_CONFIRM}{word_to_delete}"
            cancel_callback = f"{CALLBACK_DELETE_CANCEL}{word_to_delete}"

            if len(confirm_callback.encode('utf-8')) > 64 or len(cancel_callback.encode('utf-8')) > 64:
                 logger.error(f"Callback data for delete confirmation/cancel too long for word: '{word_to_delete}'.")
                 await query.edit_message_text(
                     text=f"{query.message.text}\n\n⚠️ Error: Cannot create confirmation buttons (word too long).",
                     reply_markup=None
                 )
                 return

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Yes, Delete", callback_data=confirm_callback),
                    InlineKeyboardButton("❌ No, Keep", callback_data=cancel_callback)
                ]
            ])

            await query.edit_message_text(
                text=f"❓ Are you sure you want to remove \"{word_to_delete}\" from your learning dictionary?\n\n(Original reminder: {query.message.text})",
                reply_markup=keyboard
            )

        elif callback_data.startswith(CALLBACK_DELETE_CONFIRM):
            word_to_delete = callback_data[len(CALLBACK_DELETE_CONFIRM):]
            logger.info(f"Deletion confirmed for word '{word_to_delete}' in chat {chat_id}")

            if not context.job_queue:
                logger.warning(f"JobQueue not found during delete confirmation for chat {chat_id}.")
                await query.edit_message_text(text="❌ Error: Could not access the schedule to delete.", reply_markup=None)
                return

            jobs_removed_count = 0
            current_jobs = context.job_queue.jobs()
            jobs_to_remove = []

            for job in current_jobs:
                if job and job.chat_id == chat_id and job.data and job.data.get('message_text') == word_to_delete and not job.removed:
                     jobs_to_remove.append(job)

            if not jobs_to_remove:
                 logger.info(f"No active jobs found for word '{word_to_delete}' in chat {chat_id} during confirmation.")
                 confirmation_text = f"⚠️ Could not find any active reminders for \"{word_to_delete}\"."
            else:
                for job in jobs_to_remove:
                    try:
                        job.schedule_removal()
                        jobs_removed_count += 1
                        logger.info(f"Scheduled job '{job.name}' for removal (word: '{word_to_delete}', chat: {chat_id})")
                    except Exception as e:
                         logger.error(f"Error scheduling job {job.name} for removal: {e}", exc_info=True)

                if jobs_removed_count > 0:
                    confirmation_text = f"✅ Removed \"{word_to_delete}\" ({jobs_removed_count} reminders cancelled) from your learning dictionary."
                else:
                    confirmation_text = f"❌ Error: Tried to remove {len(jobs_to_remove)} reminders for \"{word_to_delete}\", but failed. Check logs."

            await query.edit_message_text(text=confirmation_text, reply_markup=None)

        elif callback_data.startswith(CALLBACK_DELETE_CANCEL):
            word_to_delete = callback_data[len(CALLBACK_DELETE_CANCEL):]
            logger.info(f"Deletion cancelled for word '{word_to_delete}' in chat {chat_id}")

            original_reminder_text_match = re.search(r"\(Original reminder: (.*)\)", query.message.text, re.DOTALL)
            if original_reminder_text_match:
                original_text = original_reminder_text_match.group(1).strip()
            else:
                original_text = f"🔔 Reminder: {word_to_delete}"

            await query.edit_message_text(
                text=f"{original_text}\n\n❌ Deletion cancelled.",
                reply_markup=None
                )
        else:
            logger.warning(f"Received unknown callback data pattern: {callback_data}")
            await query.edit_message_text(text="😕 Unknown button action.", reply_markup=None)

    except Exception as e:
        logger.error(f"Error handling callback query data '{callback_data}' from chat {chat_id}: {e}", exc_info=True)
        try:
             await query.edit_message_text(text="😕 Sorry, an error occurred processing this action.", reply_markup=None)
        except Exception as inner_e:
            logger.error(f"Could not edit message {message_id} in chat {chat_id} to report callback error: {inner_e}")

# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)


# --- Main Bot Logic ---
def main() -> None:
    """Start the bot."""
    logger.info(f"Using bot token: {BOT_TOKEN[:8]}...{BOT_TOKEN[-4:]}")
    logger.info("Starting bot application build...")

    application = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command)) # help_command is now updated

    # Handler for the "Learning Dictionary" button
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(f'^{re.escape(LEARNING_DICT_BUTTON_TEXT)}$'),
        show_dictionary_command # show_dictionary_command is now updated
    ))

    # Handler for OTHER text messages (for scheduling reminders)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.Regex(f'^{re.escape(LEARNING_DICT_BUTTON_TEXT)}$'),
        schedule_reminders
    ))

    # Handler for Inline Keyboard Button Clicks
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    # Register the error handler
    application.add_error_handler(error_handler)

    logger.info("Bot polling started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

    logger.info("Bot stopped.")


if __name__ == '__main__':
    main()
