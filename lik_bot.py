import os
import logging
import subprocess
import asyncio
import re
from pathlib import Path
from typing import Optional, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
from pytube import YouTube, exceptions

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота (ЗАМЕНИТЕ НА СВОЙ!)
TOKEN = "8431111353:AAFjJn1Pq7m4d6TWqCiQnlhVmJbEpHp1_4s"

# Папки
TEMP_DIR = "temp_audio"
os.makedirs(TEMP_DIR, exist_ok=True)

# Поиск FFmpeg
def find_ffmpeg() -> Optional[str]:
    paths = [
        "ffmpeg", "/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg",
        "C:\\ffmpeg\\bin\\ffmpeg.exe", "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
        "C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe", "ffmpeg.exe"
    ]
    for path in paths:
        try:
            subprocess.run([path, "-version"], capture_output=True, check=True, timeout=2)
            logger.info(f"FFmpeg найден: {path}")
            return path
        except:
            continue
    return None

FFMPEG_PATH = find_ffmpeg()

# Проверка YouTube URL
def is_youtube_url(url: str) -> bool:
    patterns = [
        r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})',
        r'^https?://(?:www\.)?youtube\.com/watch\?v=[\w-]{11}',
        r'^https?://youtu\.be/[\w-]{11}'
    ]
    return any(re.match(pattern, url) for pattern in patterns)

# Скачивание и конвертация
async def download_youtube_audio(url: str, chat_id: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        yt = YouTube(url)
        title = yt.title
        duration = yt.length
        
        if duration > 7200:
            raise Exception("Видео слишком длинное (максимум 2 часа)")
        
        audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
        if not audio_stream:
            raise Exception("Аудио поток не найден")
        
        logger.info(f"Скачивание: {title}")
        download_path = audio_stream.download(
            output_path=TEMP_DIR,
            filename_prefix=f"{chat_id}_",
            skip_existing=False
        )
        
        mp3_path = os.path.splitext(download_path)[0] + ".mp3"
        
        if not FFMPEG_PATH:
            raise Exception("FFmpeg не найден. Установите FFmpeg и добавьте в PATH")
        
        cmd = [
            FFMPEG_PATH, '-i', download_path,
            '-acodec', 'libmp3lame', '-ab', '128k',
            '-ac', '2', '-ar', '44100', '-vn', '-y', mp3_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Ошибка конвертации: {stderr.decode()[:100]}")
        
        try:
            os.remove(download_path)
        except:
            pass
        
        return mp3_path, title
        
    except exceptions.PytubeError as e:
        raise Exception(f"Ошибка YouTube: {str(e)}")
    except Exception as e:
        raise Exception(f"Ошибка обработки: {str(e)}")

# Команда /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = """
🎵 *YouTube Audio Bot*

*Привет! Я конвертирую YouTube видео в аудио.*

📋 *Как использовать:*
1. Отправьте ссылку на YouTube видео
2. Я скачаю аудио и отправлю вам MP3 файл

⚠️ *Внимание:*
- Максимальная длительность: 2 часа
- Качество: 128kbps MP3
- Только для личного использования

Для помощи: /help
    """
    keyboard = [
        [InlineKeyboardButton("📖 Помощь", callback_data="help")],
        [InlineKeyboardButton("⚙️ Проверить FFmpeg", callback_data="check_ffmpeg")]
    ]
    await update.message.reply_text(
        welcome,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📖 *Справка*

*Основные команды:*
/start - Начало работы
/help - Эта справка
/ffmpeg - Проверить FFmpeg
/about - О боте

*Как конвертировать:*
1. Отправьте ссылку на YouTube
2. Ждите обработки
3. Получите MP3 файл

*Примеры ссылок:*
• https://www.youtube.com/watch?v=dQw4w9WgXcQ
• https://youtu.be/dQw4w9WgXcQ

*Если проблемы:*
1. Проверьте корректность ссылки
2. Убедитесь, что видео не длиннее 2 часов
3. Проверьте FFmpeg (/ffmpeg)
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

# Команда /ffmpeg
async def ffmpeg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if FFMPEG_PATH:
        try:
            result = subprocess.run(
                [FFMPEG_PATH, "-version"],
                capture_output=True, text=True, timeout=2
            )
            version = result.stdout.split('\n')[0].split(' ')[2] if result.stdout else "неизвестна"
            await update.message.reply_text(
                f"✅ FFmpeg установлен!\n📍 Путь: `{FFMPEG_PATH}`\n📦 Версия: `{version}`",
                parse_mode='Markdown'
            )
        except:
            await update.message.reply_text(
                f"✅ FFmpeg найден: `{FFMPEG_PATH}`",
                parse_mode='Markdown'
            )
    else:
        instructions = """
❌ FFmpeg не найден!

*Установка FFmpeg:*

*Windows:*
1. Скачайте с https://ffmpeg.org/download.html
2. Распакуйте в C:\\ffmpeg\\
3. Добавьте C:\\ffmpeg\\bin\\ в PATH
4. Перезапустите бота

*Ubuntu/Debian:*
```bash
sudo apt update
sudo apt install ffmpeg"""
