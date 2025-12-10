#!/usr/bin/env python3
"""
MEGA to Telegram Bot - Main Entry Point

Downloads files from MEGA.nz folders and uploads them to Telegram users
one-by-one with resume support.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

from bot.utils.config import Config
from bot.handlers import (
    start_handler,
    help_handler,
    download_handler,
    cancel_handler,
    status_handler
)
from database.db import Database

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# Reduce noise from libraries
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ An unexpected error occurred. Please try again later."
        )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands"""
    await update.message.reply_text(
        "❓ Unknown command. Use /help to see available commands."
    )


async def handle_mega_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle direct MEGA link messages"""
    from bot.utils.helpers import is_valid_mega_link
    from bot.handlers.download import process_mega_folder
    
    message_text = update.message.text.strip()
    
    if is_valid_mega_link(message_text):
        user_id = update.effective_user.id
        await process_mega_folder(update, context, message_text, user_id)
    else:
        await update.message.reply_text(
            "ℹ️ Send me a MEGA folder link or use /download command.\n"
            "Use /help for more information."
        )


async def post_init(application: Application):
    """Post-initialization hook - check for sessions to resume"""
    logger.info("Checking for interrupted sessions...")
    
    db = Database()
    try:
        pending = await db.get_all_pending_sessions()
        
        if pending:
            logger.info(f"Found {len(pending)} interrupted session(s)")
            
            for session in pending:
                user_id = session['user_id']
                try:
                    await application.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "🔄 **Bot Restarted**\n\n"
                            "You have an interrupted download.\n"
                            f"Use `/download {session['folder_link']}` to resume."
                        ),
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.warning(f"Could not notify user {user_id}: {e}")
        
        # Cleanup old sessions
        await db.cleanup_old_sessions(days=7)
        
    finally:
        await db.close()


def main():
    """Main entry point"""
    # Validate configuration
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    logger.info("Starting MEGA to Telegram Bot...")
    logger.info(f"Storage path: {Config.STORAGE_PATH}")
    logger.info(f"Database path: {Config.DB_PATH}")
    logger.info(f"MEGA credentials: {'configured' if Config.has_mega_credentials() else 'anonymous mode'}")
    
    # Create application
    application = (
        Application.builder()
        .token(Config.BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    
    # Add handlers
    application.add_handler(start_handler)
    application.add_handler(help_handler)
    application.add_handler(download_handler)
    application.add_handler(cancel_handler)
    application.add_handler(status_handler)
    
    # Handle direct MEGA links
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_mega_link
    ))
    
    # Handle unknown commands
    application.add_handler(MessageHandler(
        filters.COMMAND,
        unknown_command
    ))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Run the bot
    logger.info("Bot is starting...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == '__main__':
    main()
