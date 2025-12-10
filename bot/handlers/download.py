"""
Download command handler - Main workflow
"""

import asyncio
import os
from pathlib import Path
from typing import Optional

from telegram import Update, Document
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from bot.utils.config import Config
from bot.utils.helpers import is_valid_mega_link, format_size, sanitize_filename
from bot.utils.progress import ProgressTracker, format_time
from bot.mega.downloader import MegaDownloader
from database.db import Database

# Global instances
progress_tracker = ProgressTracker(update_interval=3.0)
active_downloads: dict[int, bool] = {}  # user_id: is_active


async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /download command"""
    user_id = update.effective_user.id
    
    # Check if already downloading
    if active_downloads.get(user_id, False):
        await update.message.reply_text(
            "⚠️ You already have an active download.\n"
            "Use /status to check progress or /cancel to stop it."
        )
        return
    
    # Get MEGA link from command
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide a MEGA folder link.\n\n"
            "Usage: `/download https://mega.nz/folder/XXXXX#YYYYY`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    mega_link = context.args[0]
    
    # Validate link
    if not is_valid_mega_link(mega_link):
        await update.message.reply_text(
            "❌ Invalid MEGA folder link format.\n\n"
            "Supported formats:\n"
            "• `https://mega.nz/folder/ID#KEY`\n"
            "• `https://mega.nz/#F!ID!KEY`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Start download process
    await process_mega_folder(update, context, mega_link, user_id)


async def process_mega_folder(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE,
    mega_link: str,
    user_id: int
):
    """Process MEGA folder download"""
    db = Database()
    downloader = MegaDownloader()
    
    status_message = await update.message.reply_text(
        "🔄 Connecting to MEGA...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        active_downloads[user_id] = True
        
        # Check for existing session to resume
        session = await db.get_session(user_id)
        
        if session and session['folder_link'] == mega_link:
            start_index = session['current_index']
            files = await db.get_session_files(session['id'])
            await status_message.edit_text(
                f"🔄 Resuming from file {start_index + 1}/{len(files)}..."
            )
        else:
            # New download - fetch folder contents
            await status_message.edit_text("📂 Fetching folder contents...")
            
            try:
                files = await downloader.get_folder_files(mega_link)
            except Exception as e:
                await status_message.edit_text(f"❌ Failed to fetch folder: {str(e)}")
                return
            
            if not files:
                await status_message.edit_text("📭 Folder is empty or inaccessible.")
                return
            
            # Create new session
            session_id = await db.create_session(user_id, mega_link, files)
            session = {'id': session_id, 'current_index': 0}
            start_index = 0
            
            await status_message.edit_text(
                f"📁 Found **{len(files)}** files\n"
                f"📦 Total size: **{format_size(sum(f['size'] for f in files))}**\n\n"
                f"Starting download...",
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Process files one by one
        total_files = len(files)
        
        for index in range(start_index, total_files):
            # Check if cancelled
            if not active_downloads.get(user_id, False):
                await status_message.edit_text("❌ Download cancelled.")
                break
            
            file_info = files[index]
            filename = sanitize_filename(file_info['name'])
            file_size = file_info['size']
            file_handle = file_info.get('handle', file_info.get('h'))
            
            # Skip files too large for Telegram
            if file_size > Config.MAX_FILE_SIZE:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ Skipping `{filename}` - Too large ({format_size(file_size)} > 2GB)",
                    parse_mode=ParseMode.MARKDOWN
                )
                await db.update_session_index(session['id'], index + 1)
                continue
            
            # Update status
            progress_msg = await context.bot.send_message(
                chat_id=user_id,
                text=f"📥 **Downloading [{index + 1}/{total_files}]**\n"
                     f"📁 `{filename}`\n"
                     f"📦 Size: {format_size(file_size)}\n"
                     f"⏳ Starting...",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Create progress session
            progress_tracker.create_session(user_id, filename, file_size)
            
            try:
                # Download file with progress
                download_path = Config.STORAGE_PATH / filename
                
                async def progress_callback(current: int):
                    if await progress_tracker.update(user_id, current):
                        try:
                            data = progress_tracker.get_progress(user_id)
                            await progress_msg.edit_text(
                                f"📥 **Downloading [{index + 1}/{total_files}]**\n"
                                f"📁 `{filename}`\n"
                                f"{'█' * int(data.percentage // 5)}{'░' * (20 - int(data.percentage // 5))} {data.percentage:.1f}%\n"
                                f"📊 {format_size(data.current)} / {format_size(data.total)}\n"
                                f"⚡ {format_size(data.speed)}/s | ⏱️ {format_time(data.eta)}",
                                parse_mode=ParseMode.MARKDOWN
                            )
                        except Exception:
                            pass  # Ignore edit errors
                
                await downloader.download_file(
                    mega_link,
                    file_handle,
                    download_path,
                    progress_callback
                )
                
                # Verify download
                if not download_path.exists():
                    raise FileNotFoundError(f"Download failed: {filename}")
                
                actual_size = download_path.stat().st_size
                if actual_size != file_size:
                    raise ValueError(f"Size mismatch: expected {file_size}, got {actual_size}")
                
                # Update progress for upload
                progress_tracker.set_status(user_id, "uploading")
                await progress_msg.edit_text(
                    f"📤 **Uploading [{index + 1}/{total_files}]**\n"
                    f"📁 `{filename}`\n"
                    f"📦 Size: {format_size(file_size)}\n"
                    f"⏳ Uploading to Telegram...",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Upload to Telegram
                with open(download_path, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=user_id,
                        document=f,
                        filename=filename,
                        caption=f"📁 {filename}\n📦 {format_size(file_size)}"
                    )
                
                # Delete local file immediately
                download_path.unlink(missing_ok=True)
                
                # Update database
                await db.update_session_index(session['id'], index + 1)
                
                # Update progress message
                await progress_msg.edit_text(
                    f"✅ **Completed [{index + 1}/{total_files}]**\n"
                    f"📁 `{filename}`",
                    parse_mode=ParseMode.MARKDOWN
                )
                
            except Exception as e:
                # Clean up on error
                download_path.unlink(missing_ok=True)
                
                error_msg = str(e)
                if "quota" in error_msg.lower():
                    await progress_msg.edit_text(
                        f"⚠️ **MEGA Quota Exceeded**\n"
                        f"📁 `{filename}`\n\n"
                        f"Waiting {Config.RETRY_DELAY}s before retry...\n"
                        f"Use /cancel to stop.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    # Wait and retry
                    await asyncio.sleep(Config.RETRY_DELAY)
                    
                    if active_downloads.get(user_id, False):
                        # Retry same file
                        continue
                else:
                    await progress_msg.edit_text(
                        f"❌ **Failed [{index + 1}/{total_files}]**\n"
                        f"📁 `{filename}`\n"
                        f"Error: {error_msg}",
                        parse_mode=ParseMode.MARKDOWN
                    )
            
            finally:
                progress_tracker.clear(user_id)
                
                # Small delay between files
                await asyncio.sleep(1)
        
        # All files processed
        if active_downloads.get(user_id, False):
            await db.complete_session(session['id'])
            await status_message.edit_text(
                f"🎉 **Download Complete!**\n"
                f"📁 Processed {total_files} files from MEGA folder.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    except Exception as e:
        await status_message.edit_text(
            f"❌ **Error:** {str(e)}",
            parse_mode=ParseMode.MARKDOWN
        )
    
    finally:
        active_downloads[user_id] = False
        progress_tracker.clear(user_id)
        await downloader.close()
        await db.close()


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command"""
    user_id = update.effective_user.id
    
    if active_downloads.get(user_id, False):
        active_downloads[user_id] = False
        await update.message.reply_text(
            "🛑 Cancelling download...\n"
            "The current file will be stopped and cleaned up."
        )
    else:
        await update.message.reply_text(
            "ℹ️ No active download to cancel."
        )


# Create handlers
download_handler = CommandHandler("download", download_command)
cancel_handler = CommandHandler("cancel", cancel_command)
