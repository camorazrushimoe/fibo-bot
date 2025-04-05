# Add near the top of your script
import os

import logging
import datetime # Needed for time calculations if you want more complex logic later
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue

# --- Configuration ---
# IMPORTANT: Read token from environment variable
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN environment variable set!") # Or log and exit

REMINDER_INTERVALS_SECONDS = [
    5 * 60,      # 5 minutes
    15 * 60,     # 15 minutes
    30 * 60     # 30 minutes
]
# --- End Configuration ---

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Callback function for the scheduled job ---

async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the reminder message back to the user."""
    job = context.job
    try:
        message_text = job.data['message_text']
        chat_id = job.chat_id
        await context.bot.send_message(chat_id=chat_id, text=f"🔔 Reminder: {message_text}")
        logger.info(f"Sent reminder '{message_text}' to chat_id {chat_id}")
    except Exception as e:
        logger.error(f"Error sending reminder for job {job.name}: {e}", exc_info=True)
        # Optionally, try to inform the user about the failure if possible/sensible
        # try:
        #     await context.bot.send_message(chat_id=job.chat_id, text="Sorry, I encountered an error sending one of your reminders.")
        # except Exception:
        #     logger.error(f"Could not even notify user {job.chat_id} about the failed reminder.")


# --- Bot Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}! Send me a message and I'll remind you about it later.",
        rf"Note",
        rf"Try to sent me short messages.",
        rf"Try to sent me up to 2-3 words per message. If you will sent more, efficiency of learning might reduse.",
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message when the /help command is issued."""
    intervals_minutes = [int(s / 60) for s in REMINDER_INTERVALS_SECONDS]
    help_text = (
        "I can do the following:\n"
        "/start - Welcome message\n"
        "/help - Show this help message\n"
        "Just send me any text message, and I will remind you about it "
        "Note: "
        "Try to sent me short messages."
        "Try to sent me up to 2-3 words per message. If you will sent more, efficiency of learning might reduse."
        f"after {', '.join(map(str, intervals_minutes))} minutes."
    )
    await update.message.reply_text(help_text)

# --- Message Handler ---

async def schedule_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Schedules reminders for the user's message."""
    chat_id = update.effective_chat.id
    user_message = update.message.text
    logger.info(f"Received message from {update.effective_user.username} in chat {chat_id}: {user_message}")
    
    # --- Add this logging ---
    logger.info(f"Checking context.job_queue: {context.job_queue}")
    if hasattr(context, 'job_queue'):
        logger.info(f"Type of context.job_queue: {type(context.job_queue)}")
    else:
        logger.warning("context object does not even have job_queue attribute")
    # --- End added logging ---

    # --- Add this logging ---
    logger.info(f"Inside schedule_reminders. Type of context: {type(context)}")
    logger.info(f"Checking context.job_queue: {getattr(context, 'job_queue', 'Attribute not found')}")
    if hasattr(context, 'job_queue'):
        logger.info(f"Type of context.job_queue: {type(context.job_queue)}")
    # --- End added logging ---

    if not context.job_queue:
        logger.warning("JobQueue not found in context. Reminders cannot be scheduled.")
        await update.message.reply_text("Sorry, I cannot schedule reminders right now.")
        return

    # Data to pass to the job callback
    job_data = {'message_text': user_message}

    # Schedule a job for each interval
    jobs_scheduled = 0
    for interval in REMINDER_INTERVALS_SECONDS:
        # Create a unique name for the job (optional but good practice)
        job_name = f"reminder_{chat_id}_{update.message.message_id}_{interval}s"

        # Schedule the job
        context.job_queue.run_once(
            send_reminder,
            when=interval,
            chat_id=chat_id,
            data=job_data,
            name=job_name
        )
        jobs_scheduled += 1
        logger.info(f"Scheduled job '{job_name}' to run in {interval} seconds.")

    if jobs_scheduled > 0:
        intervals_minutes = [int(s / 60) for s in REMINDER_INTERVALS_SECONDS]
        await update.message.reply_text(
            f"Okay! I will remind you about '{user_message}' "
            f"after {', '.join(map(str, intervals_minutes))} minutes."
        )
    else:
        # Should ideally not happen if intervals are defined, but good to handle
         await update.message.reply_text("Couldn't schedule any reminders.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)


# --- Main Bot Logic ---

def main() -> None:
    """Start the bot."""
    logger.info("Starting bot...")

    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN":
        logger.error("FATAL: Bot token not configured. Please replace 'YOUR_BOT_TOKEN' in the script.")
        return

    # Create the Application instance. This automatically includes a JobQueue.
    application = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    # Register the message handler to schedule reminders
    # It will handle any text message that is not a command
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_reminders))

    # Register the error handler
    application.add_error_handler(error_handler)

    # Start the Bot using polling
    logger.info("Bot started successfully! Press Ctrl+C to stop.")
    application.run_polling()

    logger.info("Bot stopped.")


if __name__ == '__main__':
    main()
