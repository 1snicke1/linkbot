import os
import logging
import tempfile
import asyncio
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pytube import YouTube
from pytube.exceptions import PytubeError
import re

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = '8431111353:AAFjJn1Pq7m4d6TWqCiQnlhVmJbEpHp1_4s'
if not TOKEN:
    raise ValueError("❌ Не установлен TELEGRAM_BOT_TOKEN. Установите переменную окружения.")

# Папка для временных файлов
TEMP_DIR = Path(tempfile.gettempdir()) / "youtube_audio_bot"
TEMP_DIR.mkdir(exist_ok=True)

class YouTubeAudioConverter:
    """Класс для работы с YouTube аудио"""
    
    @staticmethod
    async def get_video_info(url: str) -> Optional[dict]:
        """Получение информации о видео"""
        try:
            loop = asyncio.get_event_loop()
            
            # Используем YouTube объект для получения информации
            yt = await loop.run_in_executor(None, lambda: YouTube(url))
            
            # Получаем все доступные потоки
            streams = yt.streams.filter(only_audio=True)
            
            return {
                'title': yt.title or 'Без названия',
                'duration': yt.length or 0,
                'author': yt.author or 'Неизвестно',
                'views': yt.views or 0,
                'has_audio': len(streams) > 0,
                'streams_count': len(streams)
            }
        except Exception as e:
            logger.error(f"Ошибка получения информации: {e}")
            return None
    
    @staticmethod
    async def download_audio(url: str) -> Optional[Path]:
        """Скачивание аудио с YouTube"""
        try:
            loop = asyncio.get_event_loop()
            
            # Создаем объект YouTube
            yt = await loop.run_in_executor(None, lambda: YouTube(url))
            
            # Получаем аудиопотоки
            audio_streams = yt.streams.filter(only_audio=True)
            
            if not audio_streams:
                logger.error("Аудиопотоки не найдены")
                return None
            
            # Выбираем лучший аудиопоток
            # Сначала ищем mp4, затем webm
            best_stream = None
            for stream in audio_streams.order_by('abr').desc():
                if stream.mime_type == "audio/mp4":
                    best_stream = stream
                    break
            
            if not best_stream:
                best_stream = audio_streams.order_by('abr').desc().first()
            
            logger.info(f"Выбран поток: {best_stream.abr} kbps, {best_stream.mime_type}")
            
            # Очищаем имя файла от недопустимых символов
            clean_title = re.sub(r'[<>:"/\\|?*]', '', yt.title)[:100]
            filename = f"{clean_title}.mp4"
            filepath = TEMP_DIR / filename
            
            # Скачиваем файл
            logger.info(f"Скачивание: {clean_title}")
            await loop.run_in_executor(
                None, 
                lambda: best_stream.download(output_path=str(TEMP_DIR), filename=filename)
            )
            
            return filepath if filepath.exists() else None
                
        except PytubeError as e:
            logger.error(f"Ошибка pytube: {e}")
            return None
        except Exception as e:
            logger.error(f"Ошибка скачивания: {e}")
            return None
    
    @staticmethod
    def cleanup():
        """Очистка временных файлов"""
        try:
            for file in TEMP_DIR.glob("*"):
                if file.is_file():
                    file.unlink()
        except Exception as e:
            logger.error(f"Ошибка очистки: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_text = (
        "👋 Привет! Я бот для скачивания аудио с YouTube.\n\n"
        "📝 Просто отправьте мне ссылку на YouTube видео, и я отправлю вам аудиофайл.\n\n"
        "⚠️ Ограничения:\n"
        "• Максимальная длительность: 20 минут\n"
        "• Только публичные видео\n"
        "• Формат: MP4 (AAC audio)\n\n"
        "📱 Поддерживаемые ссылки:\n"
        "• https://youtube.com/watch?v=...\n"
        "• https://youtu.be/...\n"
        "• https://www.youtube.com/shorts/..."
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "📖 Как пользоваться ботом:\n\n"
        "1. Отправьте ссылку на YouTube видео\n"
        "2. Бот скачает аудиодорожку\n"
        "3. Вы получите аудиофайл в формате MP4\n\n"
        "📌 Примеры ссылок:\n"
        "• https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
        "• https://youtu.be/dQw4w9WgXcQ\n"
        "• https://www.youtube.com/shorts/kJQP7kiw5Fk\n\n"
        "⚙️ Команды:\n"
        "/start - Начало работы\n"
        "/help - Эта справка\n"
        "/clean - Очистка временных файлов (админ)\n\n"
        "📝 Примечание: Бот может не работать с видео, защищенными авторскими правами."
    )
    await update.message.reply_text(help_text)

async def clean_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистка временных файлов (админ команда)"""
    YouTubeAudioConverter.cleanup()
    await update.message.reply_text("✅ Временные файлы очищены!")

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик YouTube ссылок"""
    url = update.message.text.strip()
    
    # Проверка на валидную YouTube ссылку
    youtube_patterns = [
        r'(https?://)?(www\.)?youtube\.com/watch\?v=',
        r'(https?://)?youtu\.be/',
        r'(https?://)?(www\.)?youtube\.com/shorts/'
    ]
    
    if not any(re.search(pattern, url) for pattern in youtube_patterns):
        await update.message.reply_text(
            "❌ Пожалуйста, отправьте валидную ссылку на YouTube.\n\n"
            "📌 Примеры:\n"
            "• https://youtube.com/watch?v=VIDEO_ID\n"
            "• https://youtu.be/VIDEO_ID\n"
            "• https://youtube.com/shorts/VIDEO_ID"
        )
        return
    
    # Отправляем сообщение о начале обработки
    processing_msg = await update.message.reply_text("⏳ Обрабатываю ссылку...")
    
    try:
        # Получаем информацию о видео
        video_info = await YouTubeAudioConverter.get_video_info(url)
        
        if not video_info:
            await processing_msg.edit_text(
                "❌ Не удалось получить информацию о видео.\n"
                "Возможные причины:\n"
                "• Видео не существует\n"
                "• Видео приватное\n"
                "• Проблемы с доступом к YouTube"
            )
            return
        
        if not video_info['has_audio']:
            await processing_msg.edit_text("❌ У этого видео нет отдельной аудиодорожки.")
            return
        
        # Проверяем длительность (макс 20 минут)
        if video_info['duration'] > 1200:  # 20 минут в секундах
            await processing_msg.edit_text(
                f"❌ Видео слишком длинное ({video_info['duration'] // 60} минут).\n"
                "Максимальная длительность: 20 минут.\n"
                "Пожалуйста, отправьте видео покороче."
            )
            return
        
        # Обновляем статус
        await processing_msg.edit_text(
            f"🎵 Название: {video_info['title']}\n"
            f"👤 Автор: {video_info['author']}\n"
            f"⏱ Длительность: {video_info['duration'] // 60}:{video_info['duration'] % 60:02d}\n"
            f"📊 Найдено аудиопотоков: {video_info['streams_count']}\n\n"
            "⬇️ Скачиваю аудио..."
        )
        
        # Скачиваем аудио
        audio_path = await YouTubeAudioConverter.download_audio(url)
        
        if not audio_path or not audio_path.exists():
            await processing_msg.edit_text(
                "❌ Не удалось скачать аудио.\n"
                "Возможные причины:\n"
                "• Видео защищено авторскими правами\n"
                "• Ограничения по региону\n"
                "• Проблемы с сетью\n\n"
                "Попробуйте другую ссылку."
            )
            return
        
        # Проверяем размер файла (макс 50 МБ для Telegram)
        file_size = audio_path.stat().st_size
        if file_size > 50 * 1024 * 1024:  # 50 МБ
            await processing_msg.edit_text(
                f"❌ Файл слишком большой ({file_size / (1024*1024):.1f} МБ).\n"
                "Максимальный размер для Telegram: 50 МБ.\n"
                "Попробуйте более короткое видео."
            )
            audio_path.unlink(missing_ok=True)
            return
        
        # Отправляем аудиофайл
        await processing_msg.edit_text("📤 Отправляю аудиофайл...")
        
        with open(audio_path, 'rb') as audio_file:
            await update.message.reply_audio(
                audio=audio_file,
                title=video_info['title'][:64],  # Ограничение Telegram
                performer=video_info['author'][:64],
                duration=video_info['duration'],
                caption=f"🎵 {video_info['title']}\n👤 {video_info['author']}"
            )
        
        await processing_msg.edit_text("✅ Готово! Аудио отправлено.")
        
        # Удаляем временный файл
        try:
            audio_path.unlink()
        except Exception as e:
            logger.error(f"Ошибка удаления файла: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка обработки: {e}")
        try:
            await processing_msg.edit_text(
                f"❌ Произошла ошибка:\n{str(e)[:150]}\n\n"
                "Попробуйте еще раз или другую ссылку."
            )
        except:
            await update.message.reply_text("❌ Произошла неизвестная ошибка.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка при обработке обновления: {context.error}")
    
    if update and update.message:
        try:
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке запроса.\n"
                "Пожалуйста, попробуйте позже."
            )
        except:
            pass

def main():
    """Основная функция запуска бота"""
    try:
        # Создаем приложение
        application = Application.builder().token(TOKEN).build()
        
        # Регистрируем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("clean", clean_command))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            handle_youtube_link
        ))
        
        # Обработчик ошибок
        application.add_error_handler(error_handler)
        
        # Запускаем бота
        logger.info("🚀 Бот запускается...")
        logger.info(f"📁 Временная директория: {TEMP_DIR}")
        
        # Для Railway используем polling
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            close_loop=False
        )
        
    except Exception as e:
        logger.error(f"Фатальная ошибка при запуске бота: {e}")
        raise

if __name__ == '__main__':
    main()