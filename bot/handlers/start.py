"""
Start and help command handlers
"""

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    
    welcome_message = f"""
👋 **Welcome, {user.first_name}!**

I'm a MEGA.nz Folder Downloader Bot. I can download files from public MEGA folders and send them directly to you on Telegram.

🔹 **How I Work:**
1. Send me a MEGA folder link
2. I'll fetch all files in the folder
3. Download each file one-by-one
4. Upload directly to you
5. Delete from server immediately

🔹 **Commands:**
/download `<mega-folder-link>` - Start downloading
/status - Check current progress
/cancel - Cancel current operation
/help - Show help message

🔹 **Features:**
✅ File-by-file processing (minimal storage)
✅ Auto-resume if interrupted
✅ Real-time progress updates
✅ Handles large folders

⚠️ **Limits:**
• Files must be under 2GB (Telegram limit)
• Large folders may take time
• MEGA has bandwidth quotas

Send a MEGA folder link to get started!
"""
    
    await update.message.reply_text(
        welcome_message,
        parse_mode='Markdown'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
📖 **MEGA Folder Downloader - Help**

**Usage:**
`/download https://mega.nz/folder/XXXXX#YYYYY`

**Supported Link Formats:**
• `https://mega.nz/folder/ID#KEY`
• `https://mega.nz/#F!ID!KEY`

**Commands:**
• `/start` - Welcome message
• `/download <link>` - Start folder download
• `/status` - View current progress
• `/cancel` - Stop current download
• `/help` - This message

**How Resume Works:**
If the bot restarts during a download, it remembers:
- Which folder you were downloading
- Which file you were on
- Automatically continues from there

**Troubleshooting:**
• *"Quota exceeded"* - MEGA limits. Wait and retry.
• *"File too large"* - Telegram 2GB limit. File skipped.
• *"Invalid link"* - Check link format.

**Tips:**
• Large folders are processed file-by-file
• Each file is deleted after upload
• Use /status to monitor progress
"""
    
    await update.message.reply_text(
        help_text,
        parse_mode='Markdown'
    )


# Create handlers
start_handler = CommandHandler("start", start_command)
help_handler = CommandHandler("help", help_command)
