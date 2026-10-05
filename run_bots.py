#!/usr/bin/env python3


import sys
import os
import asyncio
import subprocess
from concurrent.futures import ThreadPoolExecutor


def install_dependencies():
    """Устанавливает зависимости если их нет"""
    print("Checking dependencies...")
    
    try:
        import vkbottle
        import vk_api
        import aiohttp
        import asyncpg
        print("All dependencies OK!")
        return True
    except ImportError as e:
        missing = str(e.name) if hasattr(e, 'name') else 'unknown'
        print(f"Installing missing dependency: {missing}...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "vkbottle", "vk_api", "aiohttp", "asyncpg", "beautifulsoup4", "dateparser", "requests"
            ])
            print("Dependencies installed!")
            return True
        except Exception as pip_e:
            print(f"ERROR: {pip_e}")
            print(f"Install manually: pip install vkbottle vk_api aiohttp asyncpg beautifulsoup4 dateparser requests")
            return False


def run_bot(filepath: str):
    """Запускает один бот"""
    print(f"Starting: {filepath}")
    try:
        process = subprocess.run([sys.executable, filepath])
        if process.returncode != 0:
            print(f"Bot {filepath} finished with error: {process.returncode}")
        else:
            print(f"Bot {filepath} finished")
    except Exception as e:
        print(f"Error running {filepath}: {e}")


async def run_bots_concurrently():
    """Запускает оба бота одновременно"""
    
    # Проверяем зависимости
    if not install_dependencies():
        print("Cannot continue without dependencies. Exiting...")
        return
    
    print("=" * 60)
    print("STARTING BOTS")
    print("=" * 60)
    print("manager.py - manager bot")
    print("game.py - game bot")
    print("=" * 60)
    
    # Проверяем файлы
    required_files = ["manager.py", "game.py", "db.py"]
    missing_files = [f for f in required_files if not os.path.exists(f)]
    
    if missing_files:
        print(f"Missing files: {', '.join(missing_files)}")
        return
    
    # Инициализируем PostgreSQL пул
    print("Initializing PostgreSQL connection...")
    try:
        import db
        await db.init_pool()
        print("PostgreSQL connected successfully!")
    except Exception as e:
        print(f"ERROR: Failed to connect to PostgreSQL: {e}")
        return
    
    # Запускаем оба бота
    with ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(run_bot, "manager.py")
        future2 = executor.submit(run_bot, "game.py")
        
        try:
            done, pending = await asyncio.wait(
                [asyncio.wrap_future(future1), asyncio.wrap_future(future2)],
                return_when=asyncio.ALL_COMPLETED
            )
        except KeyboardInterrupt:
            print("\nStopping bots...")
            await db.close_pool()


def main():
    """Главная функция"""
    print("Bot Launcher v1.0")
    print("Press Ctrl+C to stop\n")
    
    try:
        asyncio.run(run_bots_concurrently())
    except KeyboardInterrupt:
        print("\nBots stopped")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
