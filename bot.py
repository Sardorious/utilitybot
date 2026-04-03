import os
import asyncio
import logging
import uuid
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

from utils.archive import rar_to_zip
from utils.converter import word_to_pdf, pdf_to_word
from utils.image import compress_image

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Setup logging
logging.basicConfig(level=logging.INFO)

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
        "4️⃣ Rasm o'lchamini kichraytiraman (Rasm yuboring)\n\n"
        "Faylni yuboring va mos keladigan ishni bajarib beraman!"
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
    elif file_name.endswith('.jpg') or file_name.endswith('.png') or file_name.endswith('.jpeg'):
        task_name = "Image Compress"
        input_ext, output_ext = os.path.splitext(file_name)[1], "_compressed.jpg"
        func = lambda i, o: compress_image(i, o, 60)
    else:
        await wait_msg.edit_text("🤷‍♂️ Ushbu fayl turini qo'llab-quvvatlamayman. Iltimos, faqat qo'llab-quvvatlanadigan fayllarni (rar, docx, pdf, rasmlar) yuboring.")
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

async def main():
    print("Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
