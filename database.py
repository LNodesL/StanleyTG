import sqlite3
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Tuple

class Database:
    def __init__(self, db_path: str = "stanley_bot.db"):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # User balances table: (user_id, chat_id, balance)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS balances (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                balance REAL NOT NULL DEFAULT 0.0,
                PRIMARY KEY (user_id, chat_id)
            )
        ''')
        
        # Track new members for invite rewards
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS new_members (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                inviter_id INTEGER,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chat_id)
            )
        ''')
        
        # Track message rewards to prevent double-rewarding
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_rewards (
                message_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                PRIMARY KEY (message_id, chat_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def round_bytes(self, amount: float) -> float:
        """Round bytes to 2 decimal places"""
        decimal_amount = Decimal(str(amount))
        rounded = decimal_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return float(rounded)
    
    def get_balance(self, user_id: int, chat_id: int) -> float:
        """Get user balance in a specific chat"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT balance FROM balances WHERE user_id = ? AND chat_id = ?',
            (user_id, chat_id)
        )
        result = cursor.fetchone()
        conn.close()
        return self.round_bytes(result[0] if result else 0.0)
    
    def add_bytes(self, user_id: int, chat_id: int, amount: float) -> float:
        """Add bytes to user balance, returns new balance"""
        amount = self.round_bytes(amount)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO balances (user_id, chat_id, balance)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET
            balance = balance + ?
        ''', (user_id, chat_id, amount, amount))
        conn.commit()
        new_balance = self.get_balance(user_id, chat_id)
        conn.close()
        return new_balance
    
    def subtract_bytes(self, user_id: int, chat_id: int, amount: float) -> bool:
        """Subtract bytes from user balance, returns True if successful"""
        amount = self.round_bytes(amount)
        current_balance = self.get_balance(user_id, chat_id)
        if current_balance < amount:
            return False
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE balances SET balance = balance - ?
            WHERE user_id = ? AND chat_id = ?
        ''', (amount, user_id, chat_id))
        conn.commit()
        conn.close()
        return True
    
    def transfer_bytes(self, from_user_id: int, to_user_id: int, chat_id: int, amount: float) -> bool:
        """Transfer bytes between users in the same chat"""
        amount = self.round_bytes(amount)
        if not self.subtract_bytes(from_user_id, chat_id, amount):
            return False
        self.add_bytes(to_user_id, chat_id, amount)
        return True
    
    def has_rewarded_message(self, message_id: int, chat_id: int) -> bool:
        """Check if message has already been rewarded"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT 1 FROM message_rewards WHERE message_id = ? AND chat_id = ?',
            (message_id, chat_id)
        )
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def mark_message_rewarded(self, message_id: int, chat_id: int):
        """Mark message as rewarded"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR IGNORE INTO message_rewards (message_id, chat_id) VALUES (?, ?)',
            (message_id, chat_id)
        )
        conn.commit()
        conn.close()
    
    def record_new_member(self, user_id: int, chat_id: int, inviter_id: Optional[int] = None):
        """Record a new member joining"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO new_members (user_id, chat_id, inviter_id)
            VALUES (?, ?, ?)
        ''', (user_id, chat_id, inviter_id))
        conn.commit()
        conn.close()
    
    def get_inviter(self, user_id: int, chat_id: int) -> Optional[int]:
        """Get the inviter for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT inviter_id FROM new_members WHERE user_id = ? AND chat_id = ?',
            (user_id, chat_id)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result and result[0] else None
    
    def get_random_users(self, chat_id: int, count: int, exclude_user_id: Optional[int] = None) -> List[Tuple[int, str]]:
        """Get random active users from a chat for rain"""
        conn = self.get_connection()
        cursor = conn.cursor()
        if exclude_user_id:
            cursor.execute('''
                SELECT DISTINCT user_id FROM balances
                WHERE chat_id = ? AND user_id != ? AND balance > 0
                ORDER BY RANDOM()
                LIMIT ?
            ''', (chat_id, exclude_user_id, count))
        else:
            cursor.execute('''
                SELECT DISTINCT user_id FROM balances
                WHERE chat_id = ? AND balance > 0
                ORDER BY RANDOM()
                LIMIT ?
            ''', (chat_id, count))
        results = cursor.fetchall()
        conn.close()
        return [row[0] for row in results]

