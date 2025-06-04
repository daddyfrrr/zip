
import os
import zipfile
import aiohttp
import tempfile
import logging
import re
import asyncio
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.utils.markdown import hcode, hbold, hlink
from aiogram.types import FSInputFile

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VERCEL_API_TOKEN = None

if not TELEGRAM_BOT_TOKEN:
    logging.error("TELEGRAM_BOT_TOKEN environment variable not set.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

# --- Helper Functions ---

async def get_hls_key(zipurl: str, vercel_api_token: str) -> str:
    headers = {
        "host": "boosteracademyapi.classx.co.in",
        "content-type": "application/json",
        "authorization": vercel_api_token
    }

    match = re.search(r'encrypted-([a-f0-9]+)', zipurl)
    if not match:
        LOGGER.error(f"Could not extract encryption ID from URL: {zipurl}")
        raise ValueError("Could not extract encryption ID from URL.")

    encryption_id = match.group(0)
    payload = {"id": encryption_id}
    api_url = "https://boosteracademyapi.classx.co.in/api/get_hls_key"

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json=payload, headers=headers) as response:
            response_text = await response.text()
            LOGGER.info(f"API Response Status: {response.status}, Response: {response_text[:500]}")
            response.raise_for_status()
            data = await response.json()

            key = data.get('key')
            if not key:
                raise KeyError("Key not found in API response.")
            LOGGER.info(f"HLS key fetched: {key[:10]}...")
            return key

async def download_file(url: str, path: str):
    LOGGER.info(f"Downloading {url}")
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            with open(path, 'wb') as f:
                while True:
                    chunk = await response.content.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
    LOGGER.info(f"Download complete: {url}")

def extract_zip(zip_path: str, extract_to: str):
    LOGGER.info(f"Extracting {zip_path}")
    os.makedirs(extract_to, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    LOGGER.info(f"Extracted to {extract_to}")

async def decrypt_files_placeholder(segment_files: list, hls_key: str):
    LOGGER.info(f"Simulating decryption for {len(segment_files)} files...")
    decrypted_files = []
    for filepath in segment_files:
        if filepath.endswith('.tsa'):
            decrypted = filepath.replace('.tsa', '.mp4')
            try:
                os.rename(filepath, decrypted)
                decrypted_files.append(decrypted)
            except OSError as e:
                LOGGER.warning(f"Failed to rename: {e}")
                decrypted_files.append(filepath)
        else:
            decrypted_files.append(filepath)
    return decrypted_files

async def process_final_output_placeholder(extracted_dir: str) -> str:
    output_path = os.path.join(extracted_dir, "simulated_output.mkv")
    with open(output_path, 'wb') as f:
        f.write(b"# Simulated MKV Header\nDummy video content\n")
    LOGGER.info(f"Created dummy MKV: {output_path}")
    return output_path

async def process_appx_zip_logic(zipurl: str) -> str | None:
    global VERCEL_API_TOKEN

    LOGGER.info(f"Starting processing for URL: {zipurl}")
    try:
        if not VERCEL_API_TOKEN:
            LOGGER.error("VERCEL_API_TOKEN not set.")
            return None

        hls_key = await get_hls_key(zipurl, VERCEL_API_TOKEN)

        with tempfile.TemporaryDirectory() as temp_dir:
            zip_file_path = os.path.join(temp_dir, "downloaded.zip")
            extracted_path = os.path.join(temp_dir, "extracted")
            os.makedirs(extracted_path, exist_ok=True)

            await download_file(zipurl, zip_file_path)
            extract_zip(zip_file_path, extracted_path)

            supported_extensions = ['.tsa']
            segment_files = []
            for root, _, files in os.walk(extracted_path):
                for file in files:
                    if any(file.endswith(ext) for ext in supported_extensions):
                        segment_files.append(os.path.join(root, file))

            if not segment_files:
                LOGGER.warning("No segment files found.")
            else:
                await decrypt_files_placeholder(segment_files, hls_key)

            output_mkv_path = await process_final_output_placeholder(extracted_path)
            return output_mkv_path

    except Exception as e:
        LOGGER.error(f"Error in processing: {str(e)}", exc_info=True)
        return None

# --- Telegram Bot Setup ---

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    await message.answer(
        f"Hello, {hbold(message.from_user.full_name)}\n"
        f"Set your API token using: {hcode('/set_api_token <your_token>')}\n"
        f"Then use: {hcode('/download <url>')}"
    )


@dp.message(Command("set_api_token"))
async def set_api_token_handler(message: types.Message, command: CommandObject) -> None:
    global VERCEL_API_TOKEN
    args = command.args
    if not args:
        await message.answer("Please provide your API token. Example: /set_api_token eyJhbGci...")
        return
    if len(args.split(".")) != 3:
        await message.answer("This doesn't look like a valid JWT token.")
        return
    VERCEL_API_TOKEN = args.strip()
    LOGGER.info(f"API token set by user {message.from_user.id}")
    await message.answer("✅ API token set successfully.")

@dp.message(Command("download"))
async def download_command_handler(message: types.Message, command: CommandObject) -> None:
    global VERCEL_API_TOKEN
    args = command.args
    if not args:
        await message.answer("Please provide a .zip URL. Example: /download <url>")
        return
    if not VERCEL_API_TOKEN:
        await message.answer("❌ API token not set. Use /set_api_token first.")
        return
    zip_url = args.strip()
    if not (zip_url.startswith("http://") or zip_url.startswith("https://")) or not zip_url.endswith(".zip"):
        await message.answer("Please provide a valid .zip URL.")
        return
    await message.answer(f"Processing URL: {hlink('Click to view', zip_url)}", parse_mode="HTML")
    output_mkv_path = await process_appx_zip_logic(zip_url)

    if output_mkv_path and os.path.exists(output_mkv_path):
        try:
            await message.answer_document(
                document=FSInputFile(output_mkv_path),
                caption=f"✅ Output generated: {os.path.basename(output_mkv_path)} (simulated)"
            )
        except Exception as e:
            LOGGER.error(f"Error sending file: {e}", exc_info=True)
            await message.answer(f"❌ File processed but could not be sent: {e}")
        finally:
            try:
                os.remove(output_mkv_path)
            except OSError as e:
                LOGGER.error(f"Cleanup error: {e}")
    else:
        await message.answer("❌ Failed to process the file. Check logs for more info.")

async def main() -> None:
    LOGGER.info("Bot starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
