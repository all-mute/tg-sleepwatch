import matplotlib.pyplot as plt
import pandas as pd
import io
import pytz
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def calculate_points(target_time, actual_time):
    """
    Calculate points based on sleep time.
    Args:
        target_time: The targeted sleep time (HH:MM format)
        actual_time: The actual sleep time (HH:MM format)
    
    Returns:
        Points calculated. Max 6 points, -1 for each hour of delay.
    """
    try:
        # Parse times
        target_hour, target_minute = map(int, target_time.split(':'))
        actual_hour, actual_minute = map(int, actual_time.split(':'))
        
        # Convert to minutes past midnight
        target_minutes = target_hour * 60 + target_minute
        actual_minutes = actual_hour * 60 + actual_minute
        
        # If actual time is earlier, return max points
        if actual_minutes <= target_minutes:
            return 6
        
        # Calculate delay in hours (rounded up)
        delay_minutes = actual_minutes - target_minutes
        delay_hours = (delay_minutes + 59) // 60  # Round up to nearest hour
        
        # Calculate points (6 - delay, minimum is negative)
        return max(-6, 6 - delay_hours)
    except Exception as e:
        logger.error(f"Error calculating points: {e}")
        return 0

def get_yesterday_date(now_date=None, timezone=None):
    """
    Get yesterday's date in YYYY-MM-DD format.
    
    Args:
        now_date: Optional datetime object to calculate yesterday from.
                 If None, uses current datetime.
        timezone: Optional timezone (pytz timezone object).
                 If None, uses UTC.
    
    Returns:
        String representing yesterday's date in YYYY-MM-DD format
    """
    # Set default timezone to UTC if not provided
    if timezone is None:
        timezone = pytz.UTC
    
    # Get current datetime if not provided
    if now_date is None:
        now_date = datetime.now(timezone)
    elif now_date.tzinfo is None:
        # Make naive datetime timezone-aware
        now_date = timezone.localize(now_date)
    
    # Normalize to midnight to strip time component
    now_date = now_date.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Calculate yesterday
    yesterday = now_date - timedelta(days=1)
    return yesterday.strftime('%Y-%m-%d')

def create_plot_text(points_data):
    """
    Create a text representation of the plot.
    
    Args:
        points_data: List of (date, points) tuples
    
    Returns:
        String with text plot
    """
    if not points_data:
        return "No data available for plotting."
    
    # Convert to DataFrame for easier manipulation
    df = pd.DataFrame(points_data, columns=['date', 'points'])
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    
    # Create text plot
    result = "Points for the last 30 days:\n\n"
    result += "Date       | Points | Graph\n"
    result += "-----------+--------+-------------------\n"
    
    for _, row in df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        points = row['points'] if row['points'] is not None else 0
        
        # Create a simple text-based bar chart
        bar = '█' * min(max(0, points), 20)  # Limit to 20 chars max
        
        result += f"{date_str} | {points:6d} | {bar}\n"
    
    return result

def create_plot_image(points_data, username):
    """
    Create a PNG plot of the points over time.
    
    Args:
        points_data: List of (date, points) tuples
        username: Username for the plot title
    
    Returns:
        BytesIO object containing the PNG image
    """
    if not points_data:
        # Create empty plot with message if no data
        plt.figure(figsize=(10, 6))
        plt.text(0.5, 0.5, "No data available for plotting", 
                 horizontalalignment='center', verticalalignment='center',
                 transform=plt.gca().transAxes)
        plt.title(f"Sleep Points for {username}")
        plt.tight_layout()
        
        # Save to BytesIO
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf
    
    # Convert to DataFrame for plotting
    df = pd.DataFrame(points_data, columns=['date', 'points'])
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    
    # Create plot
    plt.figure(figsize=(10, 6))
    
    # Plot points
    plt.plot(df['date'], df['points'], 'o-', linewidth=2, markersize=8)
    
    # Add horizontal line at 6 points (maximum)
    plt.axhline(y=6, color='green', linestyle='--', alpha=0.5, label='Maximum (6 points)')
    
    # Add horizontal line at 0 points
    plt.axhline(y=0, color='red', linestyle='--', alpha=0.5, label='Minimum (0 points)')
    
    # Configure plot
    plt.title(f"Sleep Points for {username} - Last 30 Days")
    plt.xlabel("Date")
    plt.ylabel("Points")
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    # Format x-axis dates
    plt.gcf().autofmt_xdate()
    
    # Set y-axis limits with some padding
    min_points = min(0, df['points'].min()) - 1 if not df['points'].empty else -1
    max_points = max(6, df['points'].max()) + 1 if not df['points'].empty else 7
    plt.ylim(min_points, max_points)
    
    plt.tight_layout()
    
    # Save to BytesIO
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    
    return buf

def format_leaderboard(leaderboard_data):
    """
    Format the leaderboard data into a text message.
    
    Args:
        leaderboard_data: List of (user_id, username, total_points) tuples
    
    Returns:
        Formatted string
    """
    if not leaderboard_data:
        return "No participants in the challenge yet."
    
    result = "🏆 SLEEP CHALLENGE LEADERBOARD 🏆\n\n"
    result += "Rank | Username      | Total Points\n"
    result += "-----+---------------+-------------\n"
    
    for i, user in enumerate(leaderboard_data, 1):
        username = user['username'] or f"User {user['user_id']}"
        points = user['total_points'] if user['total_points'] is not None else 0
        
        # Add emoji for top 3
        prefix = ""
        if i == 1:
            prefix = "🥇 "
        elif i == 2:
            prefix = "🥈 "
        elif i == 3:
            prefix = "🥉 "
        else:
            prefix = f"{i}. "
        
        # Format as table row
        result += f"{prefix.ljust(4)}| {username.ljust(14)} | {points}\n"
    
    return result