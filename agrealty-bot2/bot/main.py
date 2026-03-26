"""Main entry point for the bot."""
import asyncio
import logging
import sys
from typing import Any, Awaitable, Callable, Dict
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, Update
from aiogram import BaseMiddleware
from bot.config import Config
from bot.handlers import start, menu, free_text, feedback, specialist, admin, prompt_admin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """Middleware for logging incoming messages."""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        """Log incoming message before processing."""
        if event.text:
            user_id = event.from_user.id
            username = event.from_user.username or "N/A"
            text = event.text
            logger.info(f"Incoming message - user_id: {user_id}, username: @{username}, text: {text}")
        
        return await handler(event, data)


async def main() -> None:
    """Main function to start the bot."""
    # Validate configuration
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    # Initialize bot and dispatcher
    bot = Bot(token=Config.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Register middleware
    dp.message.middleware(LoggingMiddleware())
    
    # Register routers
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(feedback.router)
    dp.include_router(specialist.router)
    dp.include_router(admin.router)
    dp.include_router(prompt_admin.router)
    dp.include_router(free_text.router)
    
    logger.info("Bot started")
    
    try:
        # Start polling
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error during polling: {e}")
    finally:
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")

