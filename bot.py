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
        if fp and os.path.exists(fp):
            try:
                os.remove(fp)
            except Exception as e:
                logging.error(f"Error removing file {fp}: {e}")

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
        "6️⃣ YouTube videodan audioni yuklab, tozalab beraman (YouTube havola yuboring)\n\n"
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
        wait_msg = await message.answer("⏳ YouTube havolasi qabul qilindi. Audio yuklab olinib tozalanishi boshlandi...\nBu jarayon video uzunligiga qarab bir necha daqiqa vaqt olishi mumkin.")
        
        output_path = generate_temp_path(".mp3")
        
        wait_msg = None
        try:
            if process_semaphore.locked():
                status_msg = await message.answer("⏳ Navbatda turibsiz... Hozirda boshqa vazifa bajarilmoqda.")

            async with process_semaphore:
                if 'status_msg' in locals(): await status_msg.delete()
                wait_msg = await message.answer("⏳ YouTube havolasi qabul qilindi. Audio yuklab olinib tozalanishi boshlandi...\nBu jarayon video uzunligiga qarab bir necha daqiqa vaqt olishi mumkin.")
                
                logging.info(f"Starting YouTube audio process for user {message.from_user.id}: {text}")
                
                progress_callback = get_progress_callback(
                    wait_msg, 
                    "YouTube audiosi qayta ishlanmoqda...",
                    {0: "⬇️ Yuklab olinmoqda...", 30: "⚙️ Tozalanmoqda...", 100: "✅ Tayyorlanmoqda..."}
                )

                # CPU va vaqt talab qiladigan jarayonni alohida thread'da ishga tushirish
                final_path = await asyncio.to_thread(process_video, text, output_path, "mp3", 0.6, progress_callback)
                
                if final_path and os.path.exists(final_path):
                    logging.info(f"YouTube success for user {message.from_user.id}")
                    await wait_msg.edit_text("✅ Audio mufavaqqiyatli tozalab tayyorlandi! Sizga yuborilmoqda...")
                    result_file = FSInputFile(final_path)
                    await message.reply_audio(result_file, caption="✅ Orqa fon shovqinlaridan tozalangan audio.")
                else:
                    logging.error(f"YouTube process failed for user {message.from_user.id}")
                    await wait_msg.edit_text("❌ Kechirasiz, audioni tozalashda xatolik yuz berdi.")
        
        except Exception as e:
            logging.error(f"Error handling youtube audio: {e}")
            if wait_msg: await wait_msg.edit_text("❌ Kechirasiz, audioni qayta ishlashda kutilmagan xatolik yuz berdi.")
            else: await message.answer("❌ Kechirasiz, kutilmagan xatolik yuz berdi.")
        finally:
            clean_up(output_path)

async def main():
    print("Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
