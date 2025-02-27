import sqlite3
import os
import logging
from datetime import datetime, time, timedelta

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path):
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.connection = None
        self.init_db()

    def get_connection(self):
        if self.connection is None:
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row
        return self.connection

    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Create users table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            timezone TEXT,
            target_sleep_time TEXT,
            join_date TEXT,
            is_active BOOLEAN DEFAULT TRUE
        )
        ''')
        
        # Create sleep records table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS sleep_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            sleep_time TEXT,
            points INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        
        conn.commit()
        logger.info("Database initialized")

    def add_user(self, user_id, username, timezone, target_sleep_time):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, timezone, target_sleep_time, join_date, is_active)
        VALUES (?, ?, ?, ?, ?, TRUE)
        ''', (user_id, username, timezone, target_sleep_time, datetime.now().strftime('%Y-%m-%d')))
        
        conn.commit()
        logger.info(f"Added user {user_id} with timezone {timezone} and target sleep time {target_sleep_time}")
        return True

    def remove_user(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        UPDATE users SET is_active = FALSE WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        logger.info(f"Removed user {user_id}")
        return cursor.rowcount > 0

    def get_user(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM users WHERE user_id = ?
        ''', (user_id,))
        
        return cursor.fetchone()

    def get_active_users(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM users WHERE is_active = TRUE
        ''')
        
        return cursor.fetchall()

    def record_sleep_time(self, user_id, date, sleep_time, points):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if a record already exists for this date and user
        cursor.execute('''
        SELECT id FROM sleep_records WHERE user_id = ? AND date = ?
        ''', (user_id, date))
        
        existing_record = cursor.fetchone()
        
        if existing_record:
            # Update existing record
            cursor.execute('''
            UPDATE sleep_records SET sleep_time = ?, points = ? WHERE id = ?
            ''', (sleep_time, points, existing_record['id']))
        else:
            # Insert new record
            cursor.execute('''
            INSERT INTO sleep_records (user_id, date, sleep_time, points)
            VALUES (?, ?, ?, ?)
            ''', (user_id, date, sleep_time, points))
        
        conn.commit()
        logger.info(f"Recorded sleep time for user {user_id} on {date}: {sleep_time}, points: {points}")
        return True

    def get_user_points(self, user_id, days=30):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Calculate the date from days ago
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        cursor.execute('''
        SELECT date, points FROM sleep_records 
        WHERE user_id = ? AND date >= ?
        ORDER BY date ASC
        ''', (user_id, start_date))
        
        return cursor.fetchall()

    def get_leaderboard(self, days=30):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Calculate the date from days ago
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        cursor.execute('''
        SELECT u.user_id, u.username, SUM(s.points) as total_points
        FROM users u
        LEFT JOIN sleep_records s ON u.user_id = s.user_id AND s.date >= ?
        WHERE u.is_active = TRUE
        GROUP BY u.user_id
        ORDER BY total_points DESC
        ''', (start_date,))
        
        return cursor.fetchall()

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None

    def has_sleep_record(self, user_id, date):
        """Check if a user has a sleep record for a specific date."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM sleep_records WHERE user_id = ? AND date = ?",
            (user_id, date.strftime('%Y-%m-%d'))
        )
        count = cursor.fetchone()[0]
        return count > 0

    def get_last_sleep_record(self, user_id):
        """Get the last sleep record for a user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT date, sleep_time, points FROM sleep_records WHERE user_id = ? ORDER BY date DESC LIMIT 1",
            (user_id,)
        )
        record = cursor.fetchone()
        
        if record:
            return {
                'date': record[0],
                'sleep_time': record[1],
                'points': record[2]
            }
        return None
        
    def update_sleep_record(self, user_id, date, sleep_time, points):
        """Update an existing sleep record."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sleep_records SET sleep_time = ?, points = ? WHERE user_id = ? AND date = ?",
            (sleep_time, points, user_id, date)
        )
        conn.commit()
        return True

    def deactivate_user(self, user_id):
        """Deactivate a user (mark as not active)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET is_active = FALSE WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        logger.info(f"Deactivated user {user_id}")
        return cursor.rowcount > 0

    def add_or_update_user(self, user_id, username, timezone, target_sleep_time, is_active=True, first_name=None):
        """Add a new user or update an existing one."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            # Update existing user
            cursor.execute('''
            UPDATE users 
            SET username = ?, timezone = ?, target_sleep_time = ?, is_active = ?
            WHERE user_id = ?
            ''', (username, timezone, target_sleep_time, is_active, user_id))
        else:
            # Add new user
            cursor.execute('''
            INSERT INTO users (user_id, username, timezone, target_sleep_time, join_date, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, timezone, target_sleep_time, datetime.now().strftime('%Y-%m-%d'), is_active))
        
        conn.commit()
        logger.info(f"Added or updated user {user_id} with timezone {timezone}")
        return True