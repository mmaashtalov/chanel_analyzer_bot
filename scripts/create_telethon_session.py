import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    phone = input("Номер телефона Telegram в международном формате: ").strip()
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start(phone=phone)
    print("\nTELEGRAM_STRING_SESSION=")
    print(client.session.save())
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
