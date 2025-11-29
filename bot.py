import os
import random
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler
)
from dotenv import load_dotenv

from database import Database

load_dotenv()

# Initialize database
db = Database()

# Bot token from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables")

def round_bytes(amount: float) -> float:
    """Round bytes to 2 decimal places"""
    decimal_amount = Decimal(str(amount))
    rounded = decimal_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return float(rounded)

async def reward_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reward users for sending messages"""
    if not update.message or not update.message.chat:
        return
    
    message = update.message
    user = message.from_user
    chat_id = message.chat.id
    message_id = message.message_id
    
    # Skip if already rewarded
    if db.has_rewarded_message(message_id, chat_id):
        return
    
    # Skip private chats (only work in groups/channels)
    if message.chat.type == 'private':
        return
    
    if not user:
        return
    
    user_id = user.id
    reward = 0.0
    
    # Check if message has media
    has_media = bool(
        message.photo or message.video or message.audio or 
        message.document or message.voice or message.video_note or
        message.sticker or message.animation
    )
    
    # Check if it's a reply
    is_reply = message.reply_to_message is not None
    
    # Calculate reward (priority: media > reply > regular)
    # Regular message (not a reply): 1 byte
    # Reply (not media): 2 bytes
    # Media (with or without reply): 3 bytes
    if has_media:
        reward = 3.0
    elif is_reply:
        reward = 2.0
    else:
        # Not responding to someone directly - only 1 byte
        reward = 1.0
    
    # Add reward
    new_balance = db.add_bytes(user_id, chat_id, reward)
    db.mark_message_rewarded(message_id, chat_id)
    
    # Optional: Log reward (can be removed for production)
    print(f"Rewarded {user_id} in {chat_id}: +{reward} bytes (new balance: {new_balance})")

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new members joining"""
    if not update.message or not update.message.new_chat_members:
        return
    
    message = update.message
    chat_id = message.chat.id
    
    for new_member in message.new_chat_members:
        # Skip if bot itself
        if new_member.is_bot:
            continue
        
        user_id = new_member.id
        
        # Try to find inviter (if message has a link or we can track it)
        inviter_id = None
        if message.from_user and message.from_user.id != user_id:
            inviter_id = message.from_user.id
        
        # Record new member
        db.record_new_member(user_id, chat_id, inviter_id)
        
        # Reward inviter if found
        if inviter_id:
            reward = 25.0
            new_balance = db.add_bytes(inviter_id, chat_id, reward)
            await message.reply_text(
                f"🎉 Welcome {new_member.first_name}! "
                f"Inviter received {reward} bytes!"
            )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_text(
        "👋 Welcome to StanleyTG!\n\n"
        "I reward you with Bytes for participating:\n"
        "• 1 Byte per message\n"
        "• 3 Bytes for messages with media\n"
        "• 2 Bytes for replying to messages\n"
        "• 25 Bytes for inviting new members\n\n"
        "Commands:\n"
        "/balance - Check your balance\n"
        "/send @user amount - Send bytes to a user\n"
        "/flip amount - Coin flip (50/50, min 10, max 1000)\n"
        "/rain amount count - Rain bytes to users\n"
        "/help - Show this help"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await start(update, context)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /balance command"""
    if not update.message or not update.message.from_user:
        return
    
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    
    balance = db.get_balance(user_id, chat_id)
    await update.message.reply_text(f"💰 Your balance: {balance:.2f} Bytes")

async def send_bytes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /send command"""
    if not update.message or not update.message.from_user:
        return
    
    if update.message.chat.type == 'private':
        await update.message.reply_text("❌ This command only works in groups or channels!")
        return
    
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    
    try:
        recipient_id = None
        amount = None
        
        # Check if it's a reply (format: /send amount)
        if update.message.reply_to_message and update.message.reply_to_message.from_user:
            if not context.args or len(context.args) < 1:
                await update.message.reply_text(
                    "❌ Usage: Reply to a message and use /send amount\n"
                    "Example: /send 10.5"
                )
                return
            recipient_id = update.message.reply_to_message.from_user.id
            amount = float(context.args[0])
        # Check if it's username format (format: /send @username amount)
        elif context.args and len(context.args) >= 2:
            recipient_str = context.args[0]
            amount = float(context.args[1])
            
            # Try to get user from mentions
            if recipient_str.startswith('@'):
                # Check message entities for mentions
                if update.message.entities:
                    for entity in update.message.entities:
                        if entity.type == "mention":
                            # Try to get user from entity
                            if hasattr(entity, 'user') and entity.user:
                                recipient_id = entity.user.id
                                break
                            # Otherwise, try to resolve username via chat members
                            else:
                                username = recipient_str[1:]  # Remove @
                                try:
                                    # Try to get chat member by username
                                    chat_member = await context.bot.get_chat_member(chat_id, username)
                                    if chat_member and chat_member.user:
                                        recipient_id = chat_member.user.id
                                        break
                                except:
                                    pass
                
                # If not found, suggest using reply method
                if not recipient_id:
                    await update.message.reply_text(
                        "❌ Could not find user. Please reply to their message and use: /send amount"
                    )
                    return
            else:
                try:
                    recipient_id = int(recipient_str)
                except ValueError:
                    await update.message.reply_text("❌ Invalid recipient format!")
                    return
        else:
            await update.message.reply_text(
                "❌ Usage:\n"
                "• Reply to a message: /send amount\n"
                "• Mention user: /send @username amount\n"
                "Example: /send @user 10.5"
            )
            return
        
        amount = round_bytes(amount)
        
        if amount <= 0:
            await update.message.reply_text("❌ Amount must be positive!")
            return
        
        if not recipient_id:
            await update.message.reply_text("❌ Could not identify recipient!")
            return
        
        if recipient_id == user_id:
            await update.message.reply_text("❌ You can't send bytes to yourself!")
            return
        
        # Check balance
        sender_balance = db.get_balance(user_id, chat_id)
        if sender_balance < amount:
            await update.message.reply_text(
                f"❌ Insufficient balance! You have {sender_balance:.2f} Bytes"
            )
            return
        
        # Transfer bytes
        if db.transfer_bytes(user_id, recipient_id, chat_id, amount):
            recipient_balance = db.get_balance(recipient_id, chat_id)
            await update.message.reply_text(
                f"✅ Sent {amount:.2f} Bytes!\n"
                f"Recipient's new balance: {recipient_balance:.2f} Bytes"
            )
        else:
            await update.message.reply_text("❌ Transfer failed!")
    
    except ValueError:
        await update.message.reply_text("❌ Invalid amount format!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def flip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /flip command"""
    if not update.message or not update.message.from_user:
        return
    
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ Usage: /flip amount\n"
            "Example: /flip 50\n"
            "Minimum: 10, Maximum: 1000"
        )
        return
    
    try:
        amount = float(context.args[0])
        amount = round_bytes(amount)
        
        if amount < 10:
            await update.message.reply_text("❌ Minimum flip amount is 10 Bytes!")
            return
        
        if amount > 1000:
            await update.message.reply_text("❌ Maximum flip amount is 1000 Bytes!")
            return
        
        # Check balance
        balance = db.get_balance(user_id, chat_id)
        if balance < amount:
            await update.message.reply_text(
                f"❌ Insufficient balance! You have {balance:.2f} Bytes"
            )
            return
        
        # Deduct amount
        if not db.subtract_bytes(user_id, chat_id, amount):
            await update.message.reply_text("❌ Failed to deduct bytes!")
            return
        
        # 50/50 flip
        user_wins = random.choice([True, False])
        
        if user_wins:
            # User wins, but 1% rake to bot
            rake = round_bytes(amount * 0.01)
            winnings = round_bytes(amount - rake)
            total_return = round_bytes(amount + winnings)
            
            # Add winnings back (original amount + winnings - rake)
            db.add_bytes(user_id, chat_id, total_return)
            
            new_balance = db.get_balance(user_id, chat_id)
            await update.message.reply_text(
                f"🎉 You won! +{winnings:.2f} Bytes (1% rake: {rake:.2f} Bytes)\n"
                f"💰 New balance: {new_balance:.2f} Bytes"
            )
        else:
            # User loses
            new_balance = db.get_balance(user_id, chat_id)
            await update.message.reply_text(
                f"😢 You lost {amount:.2f} Bytes\n"
                f"💰 New balance: {new_balance:.2f} Bytes"
            )
    
    except ValueError:
        await update.message.reply_text("❌ Invalid amount format!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def rain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /rain command"""
    if not update.message or not update.message.from_user:
        return
    
    if update.message.chat.type == 'private':
        await update.message.reply_text("❌ This command only works in groups or channels!")
        return
    
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❌ Usage: /rain amount count\n"
            "Example: /rain 10 5 (gives 10 bytes to 5 users, 50 total)"
        )
        return
    
    try:
        amount_per_user = float(context.args[0])
        count = int(context.args[1])
        
        amount_per_user = round_bytes(amount_per_user)
        
        if amount_per_user <= 0:
            await update.message.reply_text("❌ Amount per user must be positive!")
            return
        
        if count <= 0:
            await update.message.reply_text("❌ Count must be positive!")
            return
        
        total_amount = round_bytes(amount_per_user * count)
        
        # Check balance
        balance = db.get_balance(user_id, chat_id)
        if balance < total_amount:
            await update.message.reply_text(
                f"❌ Insufficient balance! You have {balance:.2f} Bytes, need {total_amount:.2f} Bytes"
            )
            return
        
        # Get random users
        recipients = db.get_random_users(chat_id, count, exclude_user_id=user_id)
        
        if len(recipients) < count:
            await update.message.reply_text(
                f"❌ Not enough active users! Found {len(recipients)}, need {count}"
            )
            return
        
        # Deduct total amount
        if not db.subtract_bytes(user_id, chat_id, total_amount):
            await update.message.reply_text("❌ Failed to deduct bytes!")
            return
        
        # Distribute to recipients
        rain_results = []
        for recipient_id in recipients:
            db.add_bytes(recipient_id, chat_id, amount_per_user)
            rain_results.append(recipient_id)
        
        new_balance = db.get_balance(user_id, chat_id)
        await update.message.reply_text(
            f"🌧️ Rain complete! Distributed {amount_per_user:.2f} Bytes to {count} users "
            f"(Total: {total_amount:.2f} Bytes)\n"
            f"💰 Your new balance: {new_balance:.2f} Bytes"
        )
    
    except ValueError:
        await update.message.reply_text("❌ Invalid format! Usage: /rain amount count")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

def main():
    """Start the bot"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("send", send_bytes))
    application.add_handler(CommandHandler("flip", flip_command))
    application.add_handler(CommandHandler("rain", rain_command))
    
    # Message handlers - catch all non-command messages (we check for media in the handler)
    # Use a filter that catches all messages except commands
    application.add_handler(MessageHandler(~filters.COMMAND, reward_message))
    
    # New member handler
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    
    print("StanleyTG bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

