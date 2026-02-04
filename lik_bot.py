import os
import logging
import tempfile
from pathlib import Path
from typing import Optional

import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pydub import AudioSegment
import requests

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.getenv('8431111353:AAFjJn1Pq7m4d6TWqCiQnlhVmJbEpHp1_4s')
if not TOKEN:
    raise ValueError("Не установлен TELEGRAM_BOT_TOKEN")

# Папка для временных файлов
TEMP_DIR = Path(tempfile.gettempdir()) / "youtube_audio_bot"
TEMP_DIR.mkdir(exist_ok=True)

class YouTubeAudioConverter:
    """Класс для конвертации YouTube видео в аудио"""
    
    @staticmethod
    def get_video_info(url: str) -> Optional[dict]:
        """Получение информации о видео"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', 'Без названия'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Неизвестно'),
                }
        except Exception as e:
            logger.error(f"Ошибка получения информации: {e}")
            return None
    
    @staticmethod
    def download_audio(url: str) -> Optional[Path]:
        """Скачивание аудио с YouTube"""
        try:
            # Опции для скачивания только аудио
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': str(TEMP_DIR / '%(title)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                audio_file = ydl.prepare_filename(info)
                
                # Преобразуем в mp3 если нужно
                if not audio_file.endswith('.mp3'):
                    audio_file = os.path.splitext(audio_file)[0] + '.mp3'
                
                return Path(audio_file)
                
        except Exception as e:
            logger.error(f"Ошибка скачивания: {e}")
            return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_text = (
        "👋 Привет! Я бот для конвертации YouTube видео в аудио.\n\n"
        "Просто отправь мне ссылку на YouTube видео, и я пришлю тебе аудиофайл.\n\n"
        "⚠️ Ограничения:\n"
        "- Максимальная длительность: 30 минут\n"
        "- Только публичные видео\n"
        "- Формат вывода: MP3"
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "📖 Как пользоваться ботом:\n\n"
        "1. Отправьте ссылку на YouTube видео\n"
        "2. Бот скачает и преобразует видео в аудио\n"
        "3. Вы получите MP3 файл\n\n"
        "Примеры ссылок:\n"
        "- https://www.youtube.com/watch?v=...\n"
        "- https://youtu.be/...\n"
        "- https://youtube.com/shorts/...\n\n"
        "Команды:\n"
        "/start - Начало работы\n"
        "/help - Эта справка"
    )
    await update.message.reply_text(help_text)

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик YouTube ссылок"""
    url = update.message.text.strip()
    
    # Проверка на валидную YouTube ссылку
    if not any(domain in url for domain in ['youtube.com', 'youtu.be']):
        await update.message.reply_text("❌ Пожалуйста, отправьте валидную ссылку на YouTube.")
        return
    
    # Отправляем сообщение о начале обработки
    processing_msg = await update.message.reply_text("⏳ Обрабатываю ссылку...")
    
    try:
        # Получаем информацию о видео
        video_info = YouTubeAudioConverter.get_video_info(url)
        
        if not video_info:
            await processing_msg.edit_text("❌ Не удалось получить информацию о видео. Проверьте ссылку.")
            return
        
        # Проверяем длительность (макс 30 минут)
        if video_info['duration'] > 1800:  # 30 минут в секундах
            await processing_msg.edit_text(
                "❌ Видео слишком длинное (более 30 минут).\n"
                "Пожалуйста, отправьте видео покороче."
            )
            return
        
        # Обновляем статус
        await processing_msg.edit_text(
            f"🎵 Название: {video_info['title']}\n"
            f"👤 Автор: {video_info['uploader']}\n"
            f"⏱ Длительность: {video_info['duration'] // 60} мин\n\n"
            "⬇️ Скачиваю аудио..."
        )
        
        # Скачиваем аудио
        audio_path = YouTubeAudioConverter.download_audio(url)
        
        if not audio_path or not audio_path.exists():
            await processing_msg.edit_text("❌ Не удалось скачать аудио. Попробуйте другую ссылку.")
            return
        
        # Отправляем аудиофайл
        await processing_msg.edit_text("📤 Отправляю аудиофайл...")
        
        with open(audio_path, 'rb') as audio_file:
            await update.message.reply_audio(
                audio=audio_file,
                title=video_info['title'][:64],  # Ограничение Telegram
                performer=video_info['uploader'][:64],
                caption=f"🎵 {video_info['title']}"
            )
        
        await processing_msg.edit_text("✅ Готово! Аудио отправлено.")
        
        # Удаляем временный файл
        try:
            audio_path.unlink()
        except:
            pass
            
    except Exception as e:
        logger.error(f"Ошибка обработки: {e}")
        try:
            await processing_msg.edit_text(f"❌ Произошла ошибка: {str(e)[:200]}")
        except:
            await update.message.reply_text("❌ Произошла неизвестная ошибка.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка при обработке обновления: {context.error}")
    
    try:
        await update.message.reply_text(
            "❌ Произошла ошибка при обработке запроса.\n"
            "Пожалуйста, попробуйте позже."
        )
    except:
        pass

def main():
    """Основная функция запуска бота"""
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_youtube_link
    ))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Бот запущен...")
    
    # Для Railway используем polling с обработкой shutdown
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()