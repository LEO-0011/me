"""
Status command handler
"""

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from bot.handlers.download import progress_tracker, active_downloads
from bot.utils.helpers import format_size
from database.db import Database


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    user_id = update.effective_user.id
    db = Database()
    
    try:
        # Check if download is active
        if not active_downloads.get(user_id, False):
            # Check for pending session
            session = await db.get_session(user_id)
            
            if session and session['status'] != 'completed':
                files = await db.get_session_files(session['id'])
                current = session['current_index']
                total = len(files)
                
                await update.message.reply_text(
                    f"⏸️ **Paused Download Detected**\n\n"
                    f"📂 Folder: `{session['folder_link'][:50]}...`\n"
                    f"📊 Progress: {current}/{total} files\n"
                    f"📌 Status: {session['status']}\n\n"
                    f"Use `/download {session['folder_link']}` to resume.",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text(
                    "ℹ️ No active or pending downloads.\n"
                    "Use /download to start a new download."
                )
            return
        
        # Get current progress
        progress = progress_tracker.get_progress(user_id)
        session = await db.get_session(user_id)
        
        if not progress or not session:
            await update.message.reply_text("ℹ️ Initializing download...")
            return
        
        files = await db.get_session_files(session['id'])
        current_index = session['current_index']
        total_files = len(files)
        
        # Calculate overall progress
        completed_size = sum(f['size'] for f in files[:current_index])
        total_size = sum(f['size'] for f in files)
        
        # Build progress bar
        bar_length = 20
        filled = int(bar_length * progress.percentage / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        status_text = (
            f"📊 **Download Status**\n\n"
            f"**Current File [{current_index + 1}/{total_files}]:**\n"
            f"📁 `{progress.filename}`\n"
            f"[{bar}] {progress.percentage:.1f}%\n"
            f"📦 {format_size(progress.current)} / {format_size(progress.total)}\n"
            f"⚡ Speed: {format_size(progress.speed)}/s\n"
            f"📌 Status: {progress.status}\n\n"
            f"**Overall Progress:**\n"
            f"📂 Files: {current_index}/{total_files}\n"
            f"📦 Data: {format_size(completed_size)} / {format_size(total_size)}"
        )
        
        await update.message.reply_text(
            status_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    finally:
        await db.close()


# Create handler
status_handler = CommandHandler("status", status_command)
