# StanleyTG Telegram Bot

A Telegram bot that rewards users with Bytes for participating in group chats and channels.

![StanleyTG Startup interface](stanleytg-2.png)

## Features

### Reward System
- **1 Byte** per regular chat message
- **3 Bytes** per message with media (photo, video, audio, document, etc.)
- **2 Bytes** for replying to someone else's message
- **25 Bytes** for inviting/joining new users

### Transfer System
- Users can send/receive bytes between users in the same group/channel
- Transfers are restricted to the same chat (no cross-group/channel transfers)

### Commands

#### `/start` or `/help`
Show bot information and available commands

#### `/balance`
Check your current Byte balance in the current chat

#### `/send @user amount` or `/send amount` (reply to message)
Send bytes to another user in the same chat
- Example: `/send @username 10.5`
- Or reply to a message and use: `/send 10.5`

#### `/flip amount`
50/50 coin flip game
- Minimum: 10 Bytes
- Maximum: 1000 Bytes
- If you win, you get your bet back plus winnings, minus 1% rake to the bot
- Example: `/flip 50`

![StanleyTG /flip command](stanley-tg.png)

#### `/rain amount count`
Distribute bytes to multiple random users
- Example: `/rain 10 5` gives 10 bytes to 5 users (50 total)
- Only distributes to active users with balances > 0

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Get a Telegram Bot Token:**
   - Message [@BotFather](https://t.me/botfather) on Telegram
   - Create a new bot with `/newbot`
   - Copy the bot token

3. **Configure environment:**
   ```bash
   cp env.example .env
   ```
   Edit `.env` and add your bot token:
   ```
   BOT_TOKEN=your_telegram_bot_token_here
   ```

4. **Run the bot:**
   ```bash
   python bot.py
   ```

## Database

The bot uses SQLite to store:
- User balances per chat (user_id, chat_id, balance)
- Message reward tracking (to prevent double-rewarding)
- New member tracking (for invite rewards)

The database file `stanley_bot.db` will be created automatically on first run.

## Notes

- Bytes are rounded to 2 decimal places
- Rewards are tracked per message to prevent spam/abuse
- The bot only works in groups and channels (not private chats)
- All balances are separate per group/channel

