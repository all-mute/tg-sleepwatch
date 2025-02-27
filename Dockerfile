FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Установка дополнительных зависимостей напрямую
RUN pip install "python-telegram-bot[job-queue]" --upgrade
RUN pip install "APScheduler>=3.6.3" --upgrade

COPY . .

RUN mkdir -p data

CMD ["python", "bot.py"]