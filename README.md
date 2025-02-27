# Sleep Challenge Telegram Bot

A Telegram bot that helps users improve their sleep habits through friendly competition.

## Features

- 🌙 Daily sleep time tracking
- 🏆 Leaderboard to compare with friends
- 📊 Visual and text-based progress charts
- ⏰ Automatic daily reminders at 12:00
- 🌐 Timezone support

## How It Works

1. Users join the challenge by sending `/join` to the bot
2. They specify their timezone and target sleep time
3. Every day at 12:00, the bot asks users what time they went to sleep
4. Points are awarded based on punctuality:
   - 6 points for going to bed on time or earlier
   - Minus 1 point for each hour of delay
   - Negative points for very late nights

## Commands

- `/start` - Start the bot
- `/help` - Show available commands
- `/join` - Join the sleep challenge
- `/unjoin` - Leave the challenge
- `/leaderboard` - View rankings
- `/plot` - Show sleep points as text graph
- `/plot_png` - Show sleep points as image

## Setup and Running

### Prerequisites

- Docker and Docker Compose
- Telegram Bot Token (already configured in .env)

### Running the Bot

1. Clone this repository
2. Navigate to the project directory
3. Run the bot with Docker Compose:

```bash
docker-compose up -d
```

### Development Setup

If you want to run the bot without Docker for development:

1. Install requirements:
```bash
pip install -r requirements.txt
```

2. Run the bot:
```bash
python bot.py
```

## Technical Details

- Built with `python-telegram-bot` framework
- SQLite database for data storage
- Matplotlib for chart generation
- Docker-based deployment with automatic restarts
- Timezone handling with pytz