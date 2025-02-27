import os
import logging
import pytz
from datetime import datetime, time, timedelta
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler
from dotenv import load_dotenv

from database import Database
from utils import calculate_points, get_yesterday_date, create_plot_text, create_plot_image, format_leaderboard

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get token from environment variable
TOKEN = os.getenv('TELEGRAM_TOKEN')
DATABASE_PATH = os.getenv('DATABASE_PATH', 'data/sleepwatch.db')

# Initialize database
db = Database(DATABASE_PATH)

# Define conversation states
TIMEZONE, TARGET_SLEEP_TIME, SLEEP_TIME = range(3)

# Available timezones (common ones)
TIMEZONE_CHOICES = [
    ["UTC", "Europe/Moscow", "Europe/London"],
    ["US/Eastern", "US/Central", "US/Pacific"],
    ["Asia/Tokyo", "Asia/Singapore", "Australia/Sydney"]
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Hello {user.first_name}! Welcome to the Sleep Challenge Bot.\n\n"
        "This bot will help you track your sleep schedule and compete with friends.\n\n"
        "Use /join to join the challenge or /help to see all commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "🌙 *Sleep Challenge Bot Commands* 🌙\n\n"
        "/start - Start the bot\n"
        "/join - Join the sleep challenge\n"
        "/unjoin - Leave the sleep challenge\n"
        "/leaderboard - View the current rankings\n"
        "/plot - Show your sleep points as text graph\n"
        "/plot_png - Show your sleep points as image\n"
        "/help - Show this help message\n\n"
        "Every day at 12:00, I'll ask you what time you went to sleep yesterday. "
        "Based on that, you'll get points for sleeping on time!"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation to join the challenge."""
    # Check if user is already in the database
    user = update.effective_user
    existing_user = db.get_user(user.id)
    
    if existing_user and existing_user['is_active']:
        await update.message.reply_text(
            "You are already participating in the sleep challenge! "
            "If you want to update your settings, first use /unjoin and then /join again."
        )
        return ConversationHandler.END
    
    # Create keyboard with timezone options
    keyboard = []
    for row in TIMEZONE_CHOICES:
        keyboard.append([InlineKeyboardButton(tz, callback_data=tz) for tz in row])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Let's get started! First, please select your timezone:",
        reply_markup=reply_markup
    )
    
    return TIMEZONE

async def timezone_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle timezone selection."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    timezone = query.data
    
    # Store in context for later use
    context.user_data['timezone'] = timezone
    
    await query.edit_message_text(
        f"Great! Your timezone is set to {timezone}.\n\n"
        "Now, please tell me what time you aim to go to sleep each night.\n"
        "Send me the time in 24-hour format (HH:MM), e.g., 23:00 for 11 PM."
    )
    
    return TARGET_SLEEP_TIME

async def target_sleep_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the target sleep time."""
    time_text = update.message.text.strip()
    
    # Validate time format
    if not re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', time_text):
        await update.message.reply_text(
            "❌ Invalid time format. Please use the 24-hour format (HH:MM), e.g., 23:00 for 11 PM."
        )
        return TARGET_SLEEP_TIME
    
    # Store in context
    context.user_data['target_sleep_time'] = time_text
    
    # Add user to database
    user = update.effective_user
    timezone = context.user_data['timezone']
    target_time = context.user_data['target_sleep_time']
    
    db.add_user(user.id, user.username or user.first_name, timezone, target_time)
    
    await update.message.reply_text(
        f"✅ Perfect! You're now part of the sleep challenge.\n\n"
        f"Your settings:\n"
        f"• Timezone: {timezone}\n"
        f"• Target sleep time: {target_time}\n\n"
        f"I'll ask you about your sleep time at 12:00 PM each day. "
        f"Good luck with your sleep goals! 😴"
    )
    
    return ConversationHandler.END

async def unjoin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command to leave the sleep challenge."""
    user = update.effective_user
    success = db.remove_user(user.id)
    
    if success:
        await update.message.reply_text(
            "You have successfully left the sleep challenge. "
            "Your data will be kept, so if you join again, your history will still be there. "
            "Use /join if you want to rejoin anytime!"
        )
    else:
        await update.message.reply_text(
            "You are not currently participating in the sleep challenge. "
            "Use /join if you want to join!"
        )

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the leaderboard."""
    leaderboard_data = db.get_leaderboard()
    formatted_leaderboard = format_leaderboard(leaderboard_data)
    
    await update.message.reply_text(formatted_leaderboard)

async def plot_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user's points as a text plot."""
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    if not user_data or not user_data['is_active']:
        await update.message.reply_text(
            "You are not currently participating in the sleep challenge. "
            "Use /join to join first!"
        )
        return
    
    points_data = db.get_user_points(user.id)
    plot_text = create_plot_text(points_data)
    
    await update.message.reply_text(
        f"📊 *Sleep Points for {user.first_name}*\n\n"
        f"{plot_text}",
        parse_mode='Markdown'
    )

async def plot_png(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user's points as a PNG plot."""
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    if not user_data or not user_data['is_active']:
        await update.message.reply_text(
            "You are not currently participating in the sleep challenge. "
            "Use /join to join first!"
        )
        return
    
    points_data = db.get_user_points(user.id)
    plot_image = create_plot_image(points_data, user.first_name)
    
    await update.message.reply_photo(
        photo=plot_image,
        caption=f"📊 Sleep Points for {user.first_name} - Last 30 days"
    )

async def ask_sleep_time(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask all active users for their sleep time."""
    active_users = db.get_active_users()
    yesterday = get_yesterday_date()
    
    for user in active_users:
        try:
            await context.bot.send_message(
                user['user_id'],
                f"Hello! What time did you go to sleep yesterday ({yesterday})?\n\n"
                f"Please reply with the time in 24-hour format (HH:MM), e.g., 23:30 for 11:30 PM."
            )
            logger.info(f"Asked user {user['user_id']} for sleep time")
        except Exception as e:
            logger.error(f"Failed to ask user {user['user_id']} for sleep time: {e}")

async def handle_sleep_time_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user's response with their sleep time."""
    user = update.effective_user
    time_text = update.message.text.strip()
    
    # Check if user is in the challenge
    user_data = db.get_user(user.id)
    if not user_data or not user_data['is_active']:
        # Ignore message if user is not in the challenge
        return
    
    # Validate time format
    if not re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', time_text):
        await update.message.reply_text(
            "❌ Invalid time format. Please use the 24-hour format (HH:MM), e.g., 23:00 for 11 PM."
        )
        return
    
    # Calculate points
    target_time = user_data['target_sleep_time']
    points = calculate_points(target_time, time_text)
    
    # Record in database
    yesterday = get_yesterday_date()
    db.record_sleep_time(user.id, yesterday, time_text, points)
    
    # Determine message based on points
    if points >= 6:
        message = "🌟 Excellent! You went to sleep on time or earlier!"
    elif points >= 4:
        message = "👍 Good job! You were only a little bit late."
    elif points >= 1:
        message = "😕 You were quite late, but still got some points."
    elif points >= 0:
        message = "😴 You were very late last night."
    else:
        message = "😱 Oh no! You were extremely late and got negative points."
    
    await update.message.reply_text(
        f"{message}\n\n"
        f"Your target sleep time: {target_time}\n"
        f"Your actual sleep time: {time_text}\n"
        f"Points earned: {points}\n\n"
        f"Use /leaderboard to see the rankings or /plot to see your progress."
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel and end the conversation."""
    await update.message.reply_text(
        "Operation cancelled. Use /join to join the challenge or /help to see all commands."
    )
    return ConversationHandler.END

async def on_startup(dp):
    # Устанавливаем команды бота
    # Эта функция не будет работать, так как вы используете python-telegram-bot, а не aiogram
    # Удаляем или комментируем этот код
    pass

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Устанавливаем команды бота для выпадающего списка
    application.bot.set_my_commands([
        ("start", "Start the bot"),
        ("help", "Show available commands"),
        ("join", "Join the sleep challenge"),
        ("unjoin", "Leave the sleep challenge"),
        ("leaderboard", "View current rankings"),
        ("plot", "Show your sleep points as text graph"),
        ("plot_png", "Show your sleep points as image")
    ])

    # Add conversation handler for joining
    join_handler = ConversationHandler(
        entry_points=[CommandHandler('join', join)],
        states={
            TIMEZONE: [CallbackQueryHandler(timezone_selected)],
            TARGET_SLEEP_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, target_sleep_time)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Add command handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(join_handler)
    application.add_handler(CommandHandler('unjoin', unjoin))
    application.add_handler(CommandHandler('leaderboard', leaderboard))
    application.add_handler(CommandHandler('plot', plot_text))
    application.add_handler(CommandHandler('plot_png', plot_png))
    
    # Add a handler for sleep time responses
    application.add_handler(MessageHandler(
        filters.Regex(r'^([01]\d|2[0-3]):([0-5]\d)$') & ~filters.COMMAND, 
        handle_sleep_time_response
    ))
    
    # Set up the job to ask for sleep time every day at 12:00
    job_queue = application.job_queue
    job_queue.run_daily(
        ask_sleep_time,
        time=time(hour=12, minute=0),
        days=(0, 1, 2, 3, 4, 5, 6)  # All days of the week
    )
    
    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()  # Возвращаем оригинальный вызов