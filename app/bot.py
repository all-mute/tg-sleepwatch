def main():
    # Явно указываем использование JobQueue при создании приложения
    application_builder = Application.builder().token(TOKEN)
    
    # Пытаемся импортировать и настроить JobQueue
    try:
        from telegram.ext import JobQueue
        application = application_builder.job_queue(JobQueue()).build()
        logging.info("JobQueue успешно инициализирована")
    except ImportError:
        logging.error("Не удалось импортировать JobQueue")
        application = application_builder.build()
    
    job_queue = application.job_queue
    
    if job_queue:
        try:
            job_queue.run_daily(
                # ... существующие параметры ...
            )
            logging.info("Ежедневная задача успешно запланирована")
        except Exception as e:
            logging.error(f"Ошибка при планировании задачи: {e}")
    else:
        logging.warning("JobQueue не настроена. Ежедневные задачи не будут выполняться.")
    
    # Остальной код... 

def help_command(update, context):
    # Исправление проблемы с форматированием Markdown
    try:
        help_text = """
*Команды бота:*
/start - Начать использование бота
/help - Показать эту справку
/join - Присоединиться к отслеживанию сна
/leave - Прекратить отслеживание сна
/sleep - Отметить время отхода ко сну
/wake - Отметить время пробуждения
/stats - Показать статистику сна
        """
        await update.message.reply_text(help_text, parse_mode='MarkdownV2')
    except Exception as e:
        # Если возникает ошибка с Markdown, отправляем без форматирования
        logging.error(f"Ошибка при отправке сообщения с Markdown: {e}")
        help_text_plain = """
Команды бота:
/start - Начать использование бота
/help - Показать эту справку
/join - Присоединиться к отслеживанию сна
/leave - Прекратить отслеживание сна
/sleep - Отметить время отхода ко сну
/wake - Отметить время пробуждения
/stats - Показать статистику сна
        """
        await update.message.reply_text(help_text_plain) 