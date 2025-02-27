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

# Настройка логирования
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

# Создаем директорию для логов, если она не существует
os.makedirs('logs', exist_ok=True)

# Настройка корневого логгера
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=LOG_LEVELS.get(LOG_LEVEL, logging.INFO)
)

# Создаем логгер для приложения
logger = logging.getLogger(__name__)

# Настройка обработчиков для разных уровней логирования
# Обработчик для info.logs
info_handler = logging.FileHandler('logs/info.logs')
info_handler.setLevel(logging.INFO)
info_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
info_handler.setFormatter(info_formatter)

# Обработчик для error.logs
error_handler = logging.FileHandler('logs/error.logs')
error_handler.setLevel(logging.ERROR)
error_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(exc_info)s')
error_handler.setFormatter(error_formatter)

# Обработчик для debug.logs
debug_handler = logging.FileHandler('logs/debug.logs')
debug_handler.setLevel(logging.DEBUG)
debug_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(pathname)s:%(lineno)d')
debug_handler.setFormatter(debug_formatter)

# Добавляем обработчики к логгеру
logger.addHandler(info_handler)
logger.addHandler(error_handler)
logger.addHandler(debug_handler)

# Get token from environment variable
TOKEN = os.getenv('TELEGRAM_TOKEN')
DATABASE_PATH = os.getenv('DATABASE_PATH', 'data/sleepwatch.db')

# Initialize database
db = Database(DATABASE_PATH)

# Define conversation states
TIMEZONE, TARGET_SLEEP_TIME, SLEEP_TIME, CHANGE_TIMEZONE = range(4)

# Available timezones (common ones)
TIMEZONE_CHOICES = [
    ["UTC", "Europe/Moscow", "Europe/London"],
    ["US/Eastern", "US/Central", "US/Pacific"],
    ["Asia/Tokyo", "Asia/Singapore", "Australia/Sydney"]
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) started the bot")
    await update.message.reply_text(
        f"👋 Hello {user.first_name}! Welcome to the Sleep Challenge Bot.\n\n"
        "This bot will help you track your sleep schedule and compete with friends.\n\n"
        "Use /join to join the challenge or /help to see all commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) requested help command")
    help_text = (
        "🌙 *Sleep Challenge Bot Commands* 🌙\n\n"
        "/start - Start the bot\n"
        "/join - Join the sleep challenge\n"
        "/unjoin - Leave the sleep challenge\n"
        "/leaderboard - View the current rankings\n"
        "/plot - Show your sleep points as text graph\n"
        "/plot_png - Show your sleep points as image\n"
        "/change_tz - Change your timezone\n"
        "/change_last_answer - Change your last sleep time report\n"
        "/help - Show this help message\n\n"
        "Every day at 12:00, I'll ask you what time you went to sleep yesterday. "
        "Based on that, you'll get points for sleeping on time!"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')
    logger.debug(f"Help message sent to user {user.id}")

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation to join the challenge."""
    # Check if user is already in the database
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) attempting to join the challenge")
    existing_user = db.get_user(user.id)
    
    if existing_user and existing_user['is_active']:
        logger.info(f"User {user.id} is already participating in the challenge")
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
        "Let's set up your sleep challenge! First, please select your timezone:",
        reply_markup=reply_markup
    )
    logger.debug(f"Timezone selection prompt sent to user {user.id}")
    
    return TIMEZONE

async def timezone_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the selected timezone."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    timezone = query.data
    
    logger.info(f"User {user.id} ({user.first_name}) selected timezone: {timezone}")
    
    # Validate timezone
    try:
        pytz.timezone(timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.error(f"Invalid timezone selected by user {user.id}: {timezone}")
        await query.edit_message_text(
            "❌ Invalid timezone. Please try again with /join."
        )
        return ConversationHandler.END
    
    # Store in context for later use
    context.user_data['timezone'] = timezone
    
    await query.edit_message_text(
        f"Great! Your timezone is set to {timezone}.\n\n"
        "Now, please tell me what time you aim to go to sleep each night.\n"
        "Send me the time in 24-hour format (HH:MM), e.g., 23:00 for 11 PM."
    )
    logger.debug(f"Target sleep time prompt sent to user {user.id}")
    
    return TARGET_SLEEP_TIME

async def target_sleep_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the target sleep time."""
    time_text = update.message.text.strip()
    user = update.effective_user
    
    logger.info(f"User {user.id} submitted target sleep time: {time_text}")
    
    # Validate time format
    if not re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', time_text):
        logger.warning(f"User {user.id} submitted invalid time format: {time_text}")
        await update.message.reply_text(
            "❌ Invalid time format. Please use the 24-hour format (HH:MM), e.g., 23:00 for 11 PM."
        )
        return TARGET_SLEEP_TIME
    
    # Parse time
    hours, minutes = map(int, time_text.split(':'))
    target_time = time(hours, minutes)
    
    # Store in context for later use
    context.user_data['target_sleep_time'] = target_time
    
    # Add or update user in database
    timezone = context.user_data['timezone']
    
    try:
        db.add_or_update_user(
            user_id=user.id,
            username=user.username or "",
            first_name=user.first_name or "",
            timezone=timezone,
            target_sleep_time=time_text,
            is_active=True
        )
        logger.info(f"User {user.id} successfully joined the challenge with timezone {timezone} and target sleep time {time_text}")
    except Exception as e:
        logger.error(f"Error adding user {user.id} to database: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ There was an error setting up your challenge. Please try again with /join."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        f"🎉 You've successfully joined the Sleep Challenge!\n\n"
        f"Your timezone: {timezone}\n"
        f"Your target sleep time: {time_text}\n\n"
        f"I'll ask you every day at 12:00 {timezone} what time you went to sleep yesterday. "
        f"Based on that, you'll get points for sleeping on time!"
        f"Type /help to see all commands."
    )
    
    return ConversationHandler.END

async def unjoin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove user from the challenge."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) attempting to leave the challenge")
    
    try:
        # Check if user is in the database
        existing_user = db.get_user(user.id)
        
        if not existing_user or not existing_user['is_active']:
            logger.info(f"User {user.id} tried to leave but is not participating in the challenge")
            await update.message.reply_text(
                "You are not currently participating in the sleep challenge. "
                "Use /join if you want to start."
            )
            return
        
        # Deactivate user
        db.deactivate_user(user.id)
        logger.info(f"User {user.id} successfully left the challenge")
        
        await update.message.reply_text(
            "You have successfully left the sleep challenge. "
            "Your data has been kept but you won't receive daily prompts anymore. "
            "Use /join if you want to rejoin later."
        )
    except Exception as e:
        logger.error(f"Error when user {user.id} tried to leave the challenge: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ There was an error processing your request. Please try again later."
        )

async def change_tz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation to change user's timezone."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) attempting to change timezone")
    
    # Check if user is in the database and active
    existing_user = db.get_user(user.id)
    
    if not existing_user or not existing_user['is_active']:
        logger.info(f"User {user.id} tried to change timezone but is not participating in the challenge")
        await update.message.reply_text(
            "Вы не участвуете в челлендже по сну. "
            "Используйте /join чтобы присоединиться сначала."
        )
        return ConversationHandler.END
    
    # Create keyboard with timezone options
    keyboard = []
    for row in TIMEZONE_CHOICES:
        keyboard.append([InlineKeyboardButton(tz, callback_data=tz) for tz in row])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    current_tz = existing_user['timezone']
    
    await update.message.reply_text(
        f"Ваша текущая таймзона: {current_tz}\n\n"
        "Пожалуйста, выберите новую таймзону:",
        reply_markup=reply_markup
    )
    logger.debug(f"Timezone change selection prompt sent to user {user.id}")
    
    return CHANGE_TIMEZONE

async def change_timezone_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the selected new timezone."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    new_timezone = query.data
    
    logger.info(f"User {user.id} ({user.first_name}) selected new timezone: {new_timezone}")
    
    # Validate timezone
    try:
        pytz.timezone(new_timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.error(f"Invalid timezone selected by user {user.id}: {new_timezone}")
        await query.edit_message_text(
            "❌ Недействительная таймзона. Пожалуйста, попробуйте снова с /change_tz."
        )
        return ConversationHandler.END
    
    try:
        # Get current user data to keep other settings
        user_data = db.get_user(user.id)
        
        # Update only timezone in database
        db.add_or_update_user(
            user_id=user.id,
            username=user.username or user_data['username'],
            first_name=user.first_name or user_data['first_name'],
            timezone=new_timezone,
            target_sleep_time=user_data['target_sleep_time'],
            is_active=True
        )
        
        await query.edit_message_text(
            f"✅ Ваша таймзона успешно изменена на {new_timezone}!"
        )
        logger.info(f"User {user.id} timezone updated to {new_timezone}")
    except Exception as e:
        logger.error(f"Error updating timezone for user {user.id}: {str(e)}", exc_info=True)
        await query.edit_message_text(
            "❌ Произошла ошибка при обновлении таймзоны. Пожалуйста, попробуйте позже."
        )
    
    return ConversationHandler.END

async def change_last_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows user to change their last sleep time response."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) attempting to change last sleep time")
    
    # Check if user is in the database and active
    user_data = db.get_user(user.id)
    if not user_data or not user_data['is_active']:
        logger.warning(f"User {user.id} tried to change last answer but is not participating in the challenge")
        await update.message.reply_text(
            "Вы не участвуете в челлендже по сну. "
            "Используйте /join чтобы присоединиться сначала."
        )
        return
    
    try:
        # Get user's timezone
        user_timezone = user_data['timezone']
        
        # Get user's local time
        user_tz = pytz.timezone(user_timezone)
        now_user_tz = datetime.now(pytz.UTC).astimezone(user_tz)
        
        # Get yesterday's date
        yesterday = get_yesterday_date(now_user_tz)
        
        # Check if user has a sleep record for yesterday
        if not db.has_sleep_record(user.id, yesterday):
            logger.info(f"User {user.id} has no sleep record for {yesterday.strftime('%Y-%m-%d')}")
            
            # Check if there's any record at all
            last_record = db.get_last_sleep_record(user.id)
            
            if not last_record:
                await update.message.reply_text(
                    "У вас еще нет записей о времени сна. Нечего изменять."
                )
                return
            
            record_date = datetime.strptime(last_record['date'], '%Y-%m-%d').date()
            
            await update.message.reply_text(
                f"Ваша последняя запись о времени сна была на {record_date.strftime('%Y-%m-%d')}.\n\n"
                f"Введите новое время в 24-часовом формате (ЧЧ:ММ), например, 23:30."
            )
            
            # Store the date in context for the handler to use
            context.user_data['change_date'] = last_record['date']
            return
        
        # User has a sleep record for yesterday
        await update.message.reply_text(
            f"У вас есть запись о времени сна за {yesterday.strftime('%Y-%m-%d')}.\n\n"
            f"Введите новое время в 24-часовом формате (ЧЧ:ММ), например, 23:30."
        )
        
        # Store the date in context for the handler to use
        context.user_data['change_date'] = yesterday.strftime('%Y-%m-%d')
    except Exception as e:
        logger.error(f"Error checking last sleep record for user {user.id}: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ Произошла ошибка при поиске вашей последней записи. Пожалуйста, попробуйте позже."
        )

async def handle_change_sleep_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the response to change sleep time request."""
    user = update.effective_user
    time_text = update.message.text.strip()
    
    logger.info(f"Received changed sleep time from user {user.id}: {time_text}")
    
    # Check if there's a date in context
    if 'change_date' not in context.user_data:
        logger.warning(f"User {user.id} tried to change sleep time without context date")
        await update.message.reply_text(
            "Пожалуйста, сначала используйте команду /change_last_answer"
        )
        return
    
    date_to_change = context.user_data['change_date']
    
    # Check if user is in the database
    user_data = db.get_user(user.id)
    if not user_data or not user_data['is_active']:
        logger.warning(f"User {user.id} tried to change sleep time but is not active")
        await update.message.reply_text(
            "Вы не участвуете в челлендже по сну. "
            "Используйте /join чтобы присоединиться сначала."
        )
        context.user_data.pop('change_date', None)
        return
    
    # Validate time format
    if not re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', time_text):
        logger.warning(f"User {user.id} submitted invalid time format: {time_text}")
        await update.message.reply_text(
            "❌ Неверный формат времени. Пожалуйста, используйте 24-часовой формат (ЧЧ:ММ), например, 23:30."
        )
        return
    
    try:
        # Parse the time
        hours, minutes = map(int, time_text.split(':'))
        sleep_time = time(hours, minutes)
        
        # Get target sleep time
        target_sleep_time = user_data['target_sleep_time']
        target_hours, target_minutes = map(int, target_sleep_time.split(':'))
        target_time = time(target_hours, target_minutes)
        
        # Calculate points
        points = calculate_points(sleep_time, target_time)
        
        # Update database
        db.update_sleep_record(user.id, date_to_change, time_text, points)
        
        # Respond to user
        if points >= 10:
            emoji = "🌟"
            message = "Отлично! Вы легли спать вовремя."
        elif points >= 7:
            emoji = "😊"
            message = "Хорошая работа! Вы легли спать близко к целевому времени."
        elif points >= 4:
            emoji = "😐"
            message = "Неплохо, но в следующий раз вы можете сделать лучше."
        else:
            emoji = "😴"
            message = "Вы легли спать далеко от целевого времени."
        
        await update.message.reply_text(
            f"{emoji} Ваше время сна за {date_to_change} успешно обновлено!\n\n"
            f"Новое время сна: {time_text}\n"
            f"Полученные баллы: {points}\n"
            f"{message}\n\n"
            f"Ваше целевое время сна: {target_sleep_time}."
        )
        
        # Clean up context
        context.user_data.pop('change_date', None)
        
        logger.info(f"Updated sleep time for user {user.id} for date {date_to_change}: {time_text}, points: {points}")
    except Exception as e:
        logger.error(f"Error updating sleep time for user {user.id}: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ Произошла ошибка при обновлении времени сна. Пожалуйста, попробуйте позже."
        )
        # Clean up context
        context.user_data.pop('change_date', None)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the current leaderboard."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) requested leaderboard")
    
    try:
        # Get leaderboard data
        leaderboard_data = db.get_leaderboard()
        
        if not leaderboard_data:
            logger.info("Leaderboard is empty - no users with sleep data")
            await update.message.reply_text(
                "No one has recorded any sleep data yet! "
                "The leaderboard will be available once users start logging their sleep times."
            )
            return
        
        # Format the leaderboard
        leaderboard_text = format_leaderboard(leaderboard_data)
        
        await update.message.reply_text(leaderboard_text, parse_mode='Markdown')
        logger.debug(f"Leaderboard sent to user {user.id}")
    except Exception as e:
        logger.error(f"Error generating leaderboard for user {user.id}: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ There was an error generating the leaderboard. Please try again later."
        )

async def plot_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user's points as a text plot."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) requested text plot")
    
    user_data = db.get_user(user.id)
    
    if not user_data or not user_data['is_active']:
        logger.warning(f"User {user.id} requested plot but is not participating in the challenge")
        await update.message.reply_text(
            "You are not currently participating in the sleep challenge. "
            "Use /join to join first!"
        )
        return
    
    try:
        points_data = db.get_user_points(user.id)
        
        if not points_data:
            logger.info(f"User {user.id} has no sleep data for plot")
            await update.message.reply_text(
                "You don't have any sleep data yet. Start logging your sleep times to see your progress!"
            )
            return
            
        plot_text = create_plot_text(points_data)
        
        await update.message.reply_text(
            f"📊 *Sleep Points for {user.first_name}*\n\n"
            f"{plot_text}",
            parse_mode='Markdown'
        )
        logger.debug(f"Text plot sent to user {user.id}")
    except Exception as e:
        logger.error(f"Error generating text plot for user {user.id}: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ There was an error generating your plot. Please try again later."
        )

async def plot_png(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user's points as a PNG plot."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) requested PNG plot")
    
    user_data = db.get_user(user.id)
    
    if not user_data or not user_data['is_active']:
        logger.warning(f"User {user.id} requested PNG plot but is not participating in the challenge")
        await update.message.reply_text(
            "You are not currently participating in the sleep challenge. "
            "Use /join to join first!"
        )
        return
    
    try:
        points_data = db.get_user_points(user.id)
        
        if not points_data:
            logger.info(f"User {user.id} has no sleep data for PNG plot")
            await update.message.reply_text(
                "You don't have any sleep data yet. Start logging your sleep times to see your progress!"
            )
            return
            
        plot_image = create_plot_image(points_data, user.first_name)
        
        await update.message.reply_photo(
            photo=plot_image,
            caption=f"📊 Sleep Points for {user.first_name} - Last 30 days"
        )
        logger.debug(f"PNG plot sent to user {user.id}")
    except Exception as e:
        logger.error(f"Error generating PNG plot for user {user.id}: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ There was an error generating your plot. Please try again later."
        )

async def ask_sleep_time(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask users what time they went to sleep yesterday."""
    logger.info("Starting daily sleep time prompt job")
    
    try:
        # Get current UTC time
        now_utc = datetime.now(pytz.UTC)
        
        # Get all active users
        active_users = db.get_active_users()
        logger.info(f"Found {len(active_users)} active users to prompt")
        
        for user in active_users:
            user_id = user['user_id']
            user_timezone = user['timezone']
            
            try:
                # Convert to user's timezone
                user_tz = pytz.timezone(user_timezone)
                now_user_tz = now_utc.astimezone(user_tz)
                
                # Only send if it's around 12:00 in the user's timezone (11:30-12:30)
                if 11 <= now_user_tz.hour <= 12:
                    yesterday = get_yesterday_date(now_user_tz)
                    
                    # Check if user already reported sleep time for yesterday
                    if not db.has_sleep_record(user_id, yesterday):
                        logger.info(f"Sending sleep time prompt to user {user_id} in timezone {user_timezone}")
                        
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"Good day! What time did you go to sleep yesterday ({yesterday.strftime('%Y-%m-%d')})?\n\n"
                                 f"Please reply with the time in 24-hour format (HH:MM), e.g., 23:30 for 11:30 PM."
                        )
                    else:
                        logger.debug(f"User {user_id} already reported sleep time for {yesterday.strftime('%Y-%m-%d')}")
                else:
                    logger.debug(f"Skipping user {user_id} as it's not 12:00 in their timezone (current hour: {now_user_tz.hour})")
            except Exception as e:
                logger.error(f"Error processing user {user_id} in ask_sleep_time: {str(e)}", exc_info=True)
    except Exception as e:
        logger.error(f"Error in ask_sleep_time job: {str(e)}", exc_info=True)

async def handle_sleep_time_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user's response about their sleep time."""
    user = update.effective_user
    time_text = update.message.text.strip()
    
    logger.info(f"Received sleep time response from user {user.id}: {time_text}")
    
    # Check if user is in the database
    user_data = db.get_user(user.id)
    if not user_data or not user_data['is_active']:
        logger.warning(f"Received sleep time from non-participating user {user.id}")
        await update.message.reply_text(
            "You are not currently participating in the sleep challenge. "
            "Use /join to join first!"
        )
        return
    
    # Validate time format
    if not re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', time_text):
        logger.warning(f"User {user.id} submitted invalid time format: {time_text}")
        await update.message.reply_text(
            "❌ Invalid time format. Please use the 24-hour format (HH:MM), e.g., 23:30 for 11:30 PM."
        )
        return
    
    try:
        # Get user's timezone
        user_timezone = user_data['timezone']
        target_sleep_time = user_data['target_sleep_time']
        
        # Parse the time
        hours, minutes = map(int, time_text.split(':'))
        sleep_time = time(hours, minutes)
        
        # Get yesterday's date in user's timezone
        user_tz = pytz.timezone(user_timezone)
        now_user_tz = datetime.now(pytz.UTC).astimezone(user_tz)
        yesterday = get_yesterday_date(now_user_tz)
        
        # Check if already reported
        if db.has_sleep_record(user.id, yesterday):
            logger.info(f"User {user.id} already reported sleep time for {yesterday.strftime('%Y-%m-%d')}, updating")
            await update.message.reply_text(
                f"You've already reported your sleep time for {yesterday.strftime('%Y-%m-%d')}. "
                f"I'll update your record with the new time: {time_text}."
            )
        
        # Calculate points
        target_hours, target_minutes = map(int, target_sleep_time.split(':'))
        target_time = time(target_hours, target_minutes)
        points = calculate_points(sleep_time, target_time)
        
        # Save to database
        db.add_sleep_record(user.id, yesterday, time_text, points)
        
        # Respond to user
        if points >= 10:
            emoji = "🌟"
            message = f"Excellent! You went to sleep right on time."
        elif points >= 7:
            emoji = "😊"
            message = f"Good job! You went to sleep close to your target time."
        elif points >= 4:
            emoji = "😐"
            message = f"Not bad, but you could do better next time."
        else:
            emoji = "😴"
            message = f"You were quite far from your target sleep time."
        
        await update.message.reply_text(
            f"{emoji} Thanks for logging your sleep time!\n\n"
            f"You went to sleep at {time_text} and earned {points} points.\n"
            f"{message}\n\n"
            f"Your target sleep time is {target_sleep_time}."
        )
        
        logger.info(f"Recorded sleep time for user {user.id}: {time_text}, points: {points}")
    except Exception as e:
        logger.error(f"Error processing sleep time for user {user.id}: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ There was an error processing your sleep time. Please try again later."
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel and end the conversation."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) cancelled the operation")
    
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
    logger.info("Starting the Sleep Challenge Bot")
    
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
        ("plot_png", "Show your sleep points as image"),
        ("change_tz", "Change your timezone"),
        ("change_last_answer", "Change your last sleep time report")
    ])

    # Add conversation handler for joining
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('join', join)],
        states={
            TIMEZONE: [CallbackQueryHandler(timezone_selected)],
            TARGET_SLEEP_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, target_sleep_time)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Add conversation handler for changing timezone
    change_tz_handler = ConversationHandler(
        entry_points=[CommandHandler('change_tz', change_tz)],
        states={
            CHANGE_TIMEZONE: [CallbackQueryHandler(change_timezone_selected)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Add command handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(conv_handler)
    application.add_handler(change_tz_handler)
    application.add_handler(CommandHandler('unjoin', unjoin))
    application.add_handler(CommandHandler('leaderboard', leaderboard))
    application.add_handler(CommandHandler('plot', plot_text))
    application.add_handler(CommandHandler('plot_png', plot_png))
    application.add_handler(CommandHandler('change_last_answer', change_last_answer))
    
    # Add a handler for sleep time responses
    application.add_handler(MessageHandler(
        filters.Regex(r'^([01]\d|2[0-3]):([0-5]\d)$') & ~filters.COMMAND, 
        lambda update, context: handle_change_sleep_time(update, context) 
        if 'change_date' in context.user_data 
        else handle_sleep_time_response(update, context)
    ))
    
    # Set up job queue for daily prompts
    job_queue = application.job_queue
    
    # Schedule the job to run at 12:00 in each timezone
    for hour in range(24):
        job_queue.run_daily(
            ask_sleep_time,
            time=time(hour, 0, 0),  # Run at each hour (00:00)
            name=f"daily_prompt_{hour}"
        )
    
    logger.info("Bot is ready to handle messages")
    
    # Start the Bot
    application.run_polling()
    
    logger.info("Bot has been stopped")

if __name__ == '__main__':
    main()  # Возвращаем оригинальный вызов