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

file_handler = logging.FileHandler('errors.log', encoding='utf-8')
file_handler.setLevel(logging.ERROR)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

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
    wait_msg = await message.answer("⏳ Rasm qabul qilindi, hajmi kichraytirilmoqda...")
    
    photo = message.photo[-1] # eng katta sifatlisi
    input_path = generate_temp_path(".jpg")
    output_path = generate_temp_path("_compressed.jpg")
    
    try:
        await bot.download(photo, destination=input_path)
        
        # CPU blocking task inside thread
        success = await asyncio.to_thread(compress_image, input_path, output_path, 50)
        
        if success:
            compressed_file = FSInputFile(output_path)
            await message.reply_document(compressed_file, caption="✅ Rasm muvaffaqiyatli kichraytirildi.")
        else:
            await message.answer("❌ Kechirasiz, rasmni kichraytirishda xatolik yuz berdi.")
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {str(e)}")
    finally:
        clean_up(input_path, output_path)
        await wait_msg.delete()

@dp.message(F.document)
async def handle_document(message: types.Message):
    document = message.document
    file_name = document.file_name.lower()
    
    wait_msg = await message.answer("⏳ Fayl yuklab olinmoqda...")
    
    # Determine the task
    if file_name.endswith('.rar'):
        task_name = "RAR to ZIP"
        input_ext, output_ext = ".rar", ".zip"
        func = rar_to_zip
    elif file_name.endswith('.docx') or file_name.endswith('.doc'):
        task_name = "Word to PDF"
        input_ext, output_ext = ".docx", ".pdf"
        func = word_to_pdf
    elif file_name.endswith('.pdf'):
        task_name = "PDF to Word"
        input_ext, output_ext = ".pdf", ".docx"
        func = pdf_to_word
    elif file_name.endswith('.md'):
        task_name = "Markdown to PDF"
        input_ext, output_ext = ".md", ".pdf"
        func = md_to_pdf
    elif file_name.endswith('.jpg') or file_name.endswith('.png') or file_name.endswith('.jpeg'):
        task_name = "Image Compress"
        input_ext, output_ext = os.path.splitext(file_name)[1], "_compressed.jpg"
        func = lambda i, o: compress_image(i, o, 60)
    else:
        await wait_msg.edit_text("🤷‍♂️ Ushbu fayl turini qo'llab-quvvatlamayman. Iltimos, faqat qo'llab-quvvatlanadigan fayllarni (rar, docx, pdf, md, rasmlar) yuboring.")
        return
        
    await wait_msg.edit_text(f"⏳ Fayl qabul qilindi. Jarayon bajarilmoqda: {task_name}...")
    
    input_path = generate_temp_path(input_ext)
    
    if task_name == "Image Compress":
        output_path = generate_temp_path(output_ext)
    else:
        # Create output path matching original file name
        base_name = os.path.splitext(document.file_name)[0]
        output_path = os.path.join(TEMP_DIR, f"{base_name}{output_ext}")
        
    try:
        await bot.download(document, destination=input_path)
        
        # Execute long computation in separate thread to avoid blocking asyncio loop
        success = await asyncio.to_thread(func, input_path, output_path)
        
        if success:
            await wait_msg.edit_text("✅ Fayl tayyorlandi! Sizga yuborilmoqda...")
            result_file = FSInputFile(output_path)
            await message.reply_document(result_file)
        else:
            await wait_msg.edit_text("❌ Kechirasiz, faylni konvertatsiya qilishda xatolik yuz berdi. Bu fayl buzilgan yoki qo'llab-quvvatlanmaydigan xususiyatlarga ega bo'lishi mumkin.")
    
    except Exception as e:
        logging.error(f"Error handling task: {e}")
        await wait_msg.edit_text(f"❌ Kutilmagan xatolik yuz berdi.")
    finally:
        clean_up(input_path, output_path)

@dp.message(F.text)
async def handle_text(message: types.Message):
    text = message.text
    
    # Check if youtube url
    if re.match(r'^(https?\:\/\/)?(www\.youtube\.com|youtu\.be)\/.+$', text):
        wait_msg = await message.answer("⏳ YouTube havolasi qabul qilindi. Audio yuklab olinib tozalanishi boshlandi...\nBu jarayon video uzunligiga qarab bir necha daqiqa vaqt olishi mumkin.")
        
        output_path = generate_temp_path(".mp3")
        
        try:
            # CPU va vaqt talab qiladigan jarayonni alohida thread'da ishga tushirish
            final_path = await asyncio.to_thread(process_video, text, output_path, "mp3", 0.6)
            
            if final_path and os.path.exists(final_path):
                await wait_msg.edit_text("✅ Audio mufavaqqiyatli tozalab tayyorlandi! Sizga yuborilmoqda...")
                result_file = FSInputFile(final_path)
                await message.reply_audio(result_file, caption="✅ Orqa fon shovqinlaridan tozalangan audio.")
            else:
                await wait_msg.edit_text("❌ Kechirasiz, audioni tozalashda xatolik yuz berdi.")
        
        except Exception as e:
            logging.error(f"Error handling youtube audio: {e}")
            await wait_msg.edit_text(f"❌ Kutilmagan xatolik yuz berdi: {str(e)}")
        finally:
            clean_up(output_path)

async def main():
    print("Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
