import os
import asyncio
import logging
import uuid
import re
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

from utils.archive import rar_to_zip
from utils.converter import word_to_pdf, pdf_to_word, md_to_pdf
from utils.image import compress_image
from utils.clean_audio import process_video
from utils.video import download_video, get_video_info
from utils.transcript import fetch_transcript, create_transcript_docx, get_video_id
from aiogram.utils.keyboard import InlineKeyboardBuilder

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

file_handler = logging.FileHandler('activity.log', encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Global semaphore to limit heavy processing to ONE at a time
process_semaphore = asyncio.Semaphore(1)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Temporary directory for processing
TEMP_DIR = "temp_files"
os.makedirs(TEMP_DIR, exist_ok=True)

def generate_temp_path(extension: str) -> str:
    return os.path.join(TEMP_DIR, f"{uuid.uuid4()}{extension}")

def clean_up(*filepaths):
    for fp in filepaths:
        if not fp: continue
        
        # Odatda filepaths ichki papka bo'ladi (TEMP_DIR)
        # Orphaned yoki yt-dlp ni .part fayllari qolib ketmasligi uchun 
        # asosi filename bilan boshlangan barcha xuddi shu nomli fayllarni o'chiramiz.
        dirname = os.path.dirname(fp)
        basename = os.path.splitext(os.path.basename(fp))[0]
        
        if os.path.exists(dirname):
            for filename in os.listdir(dirname):
                if filename.startswith(basename):
                    full_path = os.path.join(dirname, filename)
                    try:
                        os.remove(full_path)
                    except Exception as e:
                        logging.error(f"Error removing orphaned file {full_path}: {e}")

async def update_progress_ui(msg: types.Message, percent: int, title: str, status_map: dict):
    """Universal progress bar UI updater"""
    bar_length = 10
    percent = min(100, max(0, int(percent)))
    filled = percent // 10
    bar = "■" * filled + "□" * (bar_length - filled)
    
    # Find active status based on thresholds
    active_status = "Amal bajarilmoqda..."
    # Sort keys descending to find the highest threshold passed
    for threshold in sorted(status_map.keys(), reverse=True):
        if percent >= threshold:
            active_status = status_map[threshold]
            break
            
    new_text = (
        f"⏳ {title}\n\n"
        f"[{bar}] {percent}%\n"
        f"{active_status}\n\n"
        f"Iltimos, kuting..."
    )
    try:
        # Only update if text changed or it's a critical update
        if msg.text != new_text:
            await msg.edit_text(new_text)
    except Exception:
        pass

def get_progress_callback(msg: types.Message, title: str, status_map: dict):
    """Factory for thread-safe progress callbacks"""
    loop = asyncio.get_running_loop()
    # Use a dictionary to keep track of shared state
    state = {'last_percent': -10}
    
    def callback(percent: float):
        # Update every 10% or at exactly 100%
        if percent >= state['last_percent'] + 10 or percent >= 100:
            state['last_percent'] = int(percent // 10) * 10
            if percent >= 100: state['last_percent'] = 100
            
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(update_progress_ui(msg, state['last_percent'], title, status_map))
            )
    return callback

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Salom! Men yordamchi botman (Utility Bot). 🛠\n\n"
        "Men quyidagi ishlarni bajara olaman:\n"
        "1️⃣ RAR arxivni ZIP qilib beraman (.rar yuboring)\n"
        "2️⃣ Word hujjatini PDF qilib beraman (.docx yuboring)\n"
        "3️⃣ PDF hujjatini Word qilib beraman (.pdf yuboring)\n"
        "4️⃣ Rasm o'lchamini kichraytiraman (Rasm yuboring)\n"
        "5️⃣ Markdown hujjatini PDF qilib beraman (.md yuboring)\n"
        "6️⃣ YouTube havolasidan audio yuklash yoki matnga o'girish (Word).\n"
        "   🌐 Qo'llab-quvvatlanadigan tillar: O'zbek, Rus, Ingliz va Turk tillari.\n"
        "7️⃣ Instagram havoladan videoni yuklab beraman (Instagram havola yuboring)\n\n"
        "Fayl yoki havola yuboring va mos keladigan ishni bajarib beraman!"
    )

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    # Eng katta rasmni olish
    photo = message.photo[-1]
    input_path = generate_temp_path(".jpg")
    output_path = generate_temp_path("_compressed.jpg")
    
    wait_msg = None
    try:
        if process_semaphore.locked():
            status_msg = await message.answer("⏳ Navbatda turibsiz... Hozirda boshqa vazifa bajarilmoqda.")
        
        async with process_semaphore:
            if 'status_msg' in locals(): await status_msg.delete()
            wait_msg = await message.answer("⏳ Rasm qabul qilindi. Qayta ishlash boshlandi...")
            
            logging.info(f"Starting photo compression for user {message.from_user.id}")
            await bot.download(photo, destination=input_path)
            
            progress_callback = get_progress_callback(
                wait_msg,
                "Rasm siqilmoqda...",
                {0: "🖼️ Rasm yuklanmoqda...", 40: "🎨 Hajmi kichraytirilmoqda...", 100: "✅ Tayyorlanmoqda..."}
            )
            
            # Alohida thread'da siqish
            success = await asyncio.to_thread(compress_image, input_path, output_path, 60, progress_callback)
            
            if success:
                logging.info(f"Photo compression success for user {message.from_user.id}")
                await wait_msg.edit_text("✅ Rasm muvaffaqiyatli siqildi! Sizga yuborilmoqda...")
                result_file = FSInputFile(output_path)
                await message.reply_photo(result_file, caption="✅ Siqilgan rasm.")
            else:
                logging.error(f"Photo compression failed for user {message.from_user.id}")
                await wait_msg.edit_text("❌ Kechirasiz, rasmni qayta ishlashda xatolik yuz berdi.")
    except Exception as e:
        logging.error(f"Error handling photo: {e}")
        if wait_msg: await wait_msg.edit_text("❌ Kechirasiz, rasmni qayta ishlashda kutilmagan xatolik yuz berdi.")
        else: await message.answer("❌ Kechirasiz, kutilmagan xatolik yuz berdi.")
    finally:
        clean_up(input_path, output_path)
        if wait_msg:
            try: await wait_msg.delete()
            except: pass

@dp.message(F.document)
async def handle_document(message: types.Message):
    document = message.document
    file_name = document.file_name.lower()
    extension = os.path.splitext(file_name)[1]
    
    
    # Determine the task
    if extension == '.rar':
        task_name = "RAR to ZIP"
        output_ext = ".zip"
    elif extension in ['.docx', '.doc']:
        task_name = "Word to PDF"
        output_ext = ".pdf"
        extension = '.docx'
    elif extension == '.pdf':
        task_name = "PDF to Word"
        output_ext = ".docx"
    elif extension == '.md':
        task_name = "Markdown to PDF"
        output_ext = ".pdf"
    else:
        await message.answer("🤷‍♂️ Ushbu fayl turini qo'llab-quvvatlamayman. Iltimos, faqat qo'llab-quvvatlanadigan fayllarni (rar, docx, pdf, md, rasmlar) yuborig.")
        return
        
    input_path = generate_temp_path(extension)
    base_name = os.path.splitext(document.file_name)[0]
    output_path = os.path.join(TEMP_DIR, f"{base_name}{output_ext}")
    
    wait_msg = None
    try:
        if process_semaphore.locked():
            status_msg = await message.answer("⏳ Navbatda turibsiz... Hozirda boshqa vazifa bajarilmoqda.")

        async with process_semaphore:
            if 'status_msg' in locals(): await status_msg.delete()
            wait_msg = await message.answer(f"⏳ Fayl qabul qilindi. Jarayon bajarilmoqda: {task_name}...")
            
            logging.info(f"Starting {task_name} for user {message.from_user.id}: {document.file_name}")
            await bot.download(document, destination=input_path)
            
            if extension == '.docx':
                progress_callback = get_progress_callback(
                    wait_msg, "Hujjat o'tkazilmoqda...", 
                    {0: "📄 Word yuklanmoqda...", 40: "🔄 PDF'ga o'tkazilmoqda...", 100: "✅ Tayyorlanmoqda..."}
                )
                success = await asyncio.to_thread(word_to_pdf, input_path, output_path, progress_callback)
                caption = "📄 Word'dan PDF'ga o'tkazildi."
                
            elif extension == '.pdf':
                progress_callback = get_progress_callback(
                    wait_msg, "Hujjat OCR qilinmoqda...", 
                    {0: "📄 PDF yuklanmoqda...", 10: "🔍 Matn tanib olinmoqda (OCR)...", 100: "✅ Tayyorlanmoqda..."}
                )
                success = await asyncio.to_thread(pdf_to_word, input_path, output_path, progress_callback)
                caption = "📄 PDF'dan Word'ga (OCR) o'tkazildi."
                
            elif extension == '.md':
                progress_callback = get_progress_callback(
                    wait_msg, "Hujjat o'tkazilmoqda...", 
                    {0: "📝 Markdown yuklanmoqda...", 40: "📊 Diagrammalar chizilmoqda...", 90: "🔄 PDF'ga o'tkazilmoqda...", 100: "✅ Tayyorlanmoqda..."}
                )
                success = await asyncio.to_thread(md_to_pdf, input_path, output_path, progress_callback)
                caption = "📝 Markdown'dan PDF'ga o'tkazildi."
                
            elif extension == '.rar':
                progress_callback = get_progress_callback(
                    wait_msg, "Arxiv o'tkazilmoqda...", 
                    {0: "📦 RAR yuklanmoqda...", 20: "🔓 Ochilmoqda...", 50: "🤐 ZIP'ga siqilmoqda...", 100: "✅ Tayyorlanmoqda..."}
                )
                success = await asyncio.to_thread(rar_to_zip, input_path, output_path, progress_callback)
                caption = "📦 RAR'dan ZIP'ga o'tkazildi."
            
            if success:
                logging.info(f"{task_name} success for user {message.from_user.id}")
                await wait_msg.edit_text("✅ Jarayon muvaffaqiyatli yakunlandi! Fayl yuborilmoqda...")
                result_file = FSInputFile(output_path)
                await message.reply_document(result_file, caption=caption)
            else:
                logging.error(f"{task_name} failed for user {message.from_user.id}")
                await wait_msg.edit_text("❌ Kechirasiz, faylni qayta ishlashda xatolik yuz berdi. Bu fayl buzilgan yoki qo'llab-quvvatlanmaydigan xususiyatlarga ega bo'lishi mumkin.")
    
    except Exception as e:
        logging.error(f"Error handling task: {e}")
        if wait_msg: await wait_msg.edit_text(f"❌ Kutilmagan xatolik yuz berdi.")
        else: await message.answer(f"❌ Kutilmagan xatolik yuz berdi.")
    finally:
        clean_up(input_path, output_path)

@dp.message(F.text)
async def handle_text(message: types.Message):
    text = message.text
    
    # Check if youtube url
    if re.match(r'^(https?\:\/\/)?(www\.youtube\.com|youtu\.be)\/.+$', text):
        video_id = get_video_id(text)
        if not video_id:
            await message.answer("❌ YouTube videosi ID-sini aniqlab bo'lmadi.")
            return

        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="🎵 Audio yuklash", callback_data=f"yt_audio:{video_id}"),
            types.InlineKeyboardButton(text="📝 Matnga o'girish (Word)", callback_data=f"yt_text:{video_id}")
        )
        
        await message.answer(
            "🎬 YouTube videosi aniqlandi.\nNima qilishni xohlaysiz?",
            reply_markup=builder.as_markup()
        )
        return
            
            
    # Check if instagram url
    elif re.match(r'^(https?\:\/\/)?(www\.)?instagram\.com\/.+$', text):
        output_path = generate_temp_path(".mp4")
        wait_msg = None
        try:
            if process_semaphore.locked():
                status_msg = await message.answer("⏳ Navbatda turibsiz... Hozirda boshqa vazifa bajarilmoqda.")

            async with process_semaphore:
                if 'status_msg' in locals(): await status_msg.delete()
                wait_msg = await message.answer("⏳ Instagram havolasi qabul qilindi. Video yuklab olinmoqda...")
                
                logging.info(f"Starting Instagram video download for user {message.from_user.id}: {text}")
                
                progress_callback = get_progress_callback(
                    wait_msg, 
                    "Instagram videosi yuklanmoqda...",
                    {0: "⬇️ Yuklab olinmoqda...", 100: "✅ Tayyorlanmoqda..."}
                )

                final_path = await asyncio.to_thread(download_video, text, output_path, progress_callback)
                
                if final_path and os.path.exists(final_path):
                    logging.info(f"Instagram download success for user {message.from_user.id}")
                    await wait_msg.edit_text("✅ Video mufavaqqiyatli yuklandi! Sizga yuborilmoqda...")
                    
                    # Extract metadata for better Telegram player support
                    video_info = get_video_info(final_path)
                    
                    result_file = FSInputFile(final_path)
                    await message.reply_video(
                        result_file, 
                        caption="✅ Instagram videosi.",
                        width=video_info.get("width"),
                        height=video_info.get("height"),
                        duration=int(video_info.get("duration", 0)) if video_info.get("duration") else None
                    )
                else:
                    logging.error(f"Instagram download failed for user {message.from_user.id}")
                    await wait_msg.edit_text("❌ Kechirasiz, videoni yuklashda xatolik yuz berdi yoxud video yopiq profildan olingan.")
        
        except Exception as e:
            logging.error(f"Error handling instagram video: {e}")
            if wait_msg: await wait_msg.edit_text("❌ Kechirasiz, videoni qayta ishlashda kutilmagan xatolik yuz berdi.")
            else: await message.answer("❌ Kechirasiz, kutilmagan xatolik yuz berdi.")
        finally:
            clean_up(output_path)
    else:
        await message.answer("🤷‍♂️ Ushbu xabarni tushunmadim. Iltimos, YouTube yoki Instagram havolasi yuboring.")

@dp.callback_query(F.data.startswith("yt_"))
async def handle_youtube_callback(callback: types.CallbackQuery):
    data = callback.data.split(":")
    action = data[0]
    video_id = data[1]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    
    # Acknowledge callback to stop loading spinner
    await callback.answer()
    
    # Use the original message as base for progress updates
    message = callback.message
    
    if action == "yt_audio":
        output_path = generate_temp_path(".mp3")
        wait_msg = None
        try:
            if process_semaphore.locked():
                status_msg = await message.answer("⏳ Navbatda turibsiz... Hozirda boshqa vazifa bajarilmoqda.")

            async with process_semaphore:
                if 'status_msg' in locals(): await status_msg.delete()
                wait_msg = await message.answer("⏳ YouTube audio yuklanishi boshlandi...\nBu jarayon video uzunligiga qarab bir necha daqiqa vaqt olishi mumkin.")
                
                logging.info(f"Starting YouTube audio process for user {callback.from_user.id}: {video_url}")
                
                progress_callback = get_progress_callback(
                    wait_msg, 
                    "YouTube audiosi qayta ishlanmoqda...",
                    {0: "⬇️ Yuklab olinmoqda...", 30: "⚙️ Tozalanmoqda...", 100: "✅ Tayyorlanmoqda..."}
                )

                final_path = await asyncio.to_thread(process_video, video_url, output_path, "mp3", 0.6, progress_callback)
                
                if final_path and os.path.exists(final_path):
                    await wait_msg.edit_text("✅ Audio mufavaqqiyatli tayyorlandi! Sizga yuborilmoqda...")
                    result_file = FSInputFile(final_path)
                    await message.reply_audio(result_file, caption="✅ Orqa fon shovqinlaridan tozalangan audio.")
                else:
                    await wait_msg.edit_text("❌ Kechirasiz, audioni qayta ishlashda xatolik yuz berdi.")
        except Exception as e:
            logging.error(f"Error in yt_audio callback: {e}")
            await message.answer("❌ Kutilmagan xatolik yuz berdi.")
        finally:
            clean_up(output_path)
            if wait_msg:
                try: await wait_msg.delete()
                except: pass

    elif action == "yt_text":
        output_path = generate_temp_path(".docx")
        wait_msg = None
        try:
            if process_semaphore.locked():
                status_msg = await message.answer("⏳ Navbatda turibsiz... Hozirda boshqa vazifa bajarilmoqda.")

            async with process_semaphore:
                if 'status_msg' in locals(): await status_msg.delete()
                wait_msg = await message.answer("⏳ YouTube transkriptini tayyorlash boshlandi...\nAgar subtitrlar bo'lmasa, AI orqali matnga o'giriladi.")
                
                logging.info(f"Starting YouTube transcript for user {callback.from_user.id}: {video_url}")
                
                progress_callback = get_progress_callback(
                    wait_msg, 
                    "Matnga o'girilmoqda...",
                    {0: "🔍 Subtitrlar tekshirilmoqda...", 10: "🤖 AI transkripsiya (agar kerak bo'lsa)...", 100: "✅ Tayyorlanmoqda..."}
                )

                # Fetch transcript (with AI fallback)
                transcript_data, error = await asyncio.to_thread(fetch_transcript, video_url, TEMP_DIR, progress_callback)
                
                if transcript_data:
                    success = await asyncio.to_thread(create_transcript_docx, transcript_data, output_path)
                    if success:
                        await wait_msg.edit_text("✅ Transkript muvaffaqiyatli tayyorlandi! Yuborilmoqda...")
                        result_file = FSInputFile(output_path)
                        await message.reply_document(result_file, caption="📝 Video transkripti (Word).")
                    else:
                        await wait_msg.edit_text("❌ Word hujjatini yaratishda xatolik yuz berdi.")
                else:
                    await wait_msg.edit_text(f"❌ Transkriptni olib bo'lmadi: {error}")
        except Exception as e:
            logging.error(f"Error in yt_text callback: {e}")
            await message.answer("❌ Kutilmagan xatolik yuz berdi.")
        finally:
            clean_up(output_path)
            if wait_msg:
                try: await wait_msg.delete()
                except: pass

async def main():
    print("Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
