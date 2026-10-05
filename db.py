#!/usr/bin/env python3
"""
Модуль базы данных PostgreSQL для ботов greatmanager
Оптимизированная версия с быстрыми запросами и кэшированием
"""

import os
import asyncio
import asyncpg
from typing import Optional, Any, List, Dict
import time
import re

# URL базы данных
DB_URL = os.getenv("DATABASE_URL", "postgresql://bothost_db_b096a4e43148:7AWysaAMN5QxNlzUQemI7lNtL1DU9a0290HgFKxzCWA@node1.pghost.ru:15769/bothost_db_b096a4e43148")

# Глобальный пул соединений
_pool: Optional[asyncpg.Pool] = None

# Последний выполненный запрос (для совместимости с SQLite pattern)
_last_query: str = ""
_last_args: tuple = ()

# Кэш преобразованных запросов
_query_cache: Dict[str, str] = {}

# Кэш результатов запросов (query+args -> (result, timestamp))
_result_cache: Dict[str, tuple] = {}
RESULT_CACHE_TTL = 5  # секунды

# Кэш для часто запрашиваемых данных
_data_cache: Dict[str, tuple] = {}
DATA_CACHE_TTL = 3  # секунды


def _cache_key(query: str, args: tuple) -> str:
    """Создать ключ кэша для запроса"""
    return f"{query}::{args}"


def cache_get_result(query: str, args: tuple):
    """Получить результат из кэша"""
    key = _cache_key(query, args)
    if key in _result_cache:
        value, timestamp = _result_cache[key]
        if time.time() - timestamp < RESULT_CACHE_TTL:
            return value
        else:
            del _result_cache[key]
    return None


def cache_set_result(query: str, args: tuple, value):
    """Сохранить результат в кэш"""
    key = _cache_key(query, args)
    _result_cache[key] = (value, time.time())


def cache_get(key: str) -> Optional[Any]:
    """Получить из кэша"""
    if key in _data_cache:
        value, timestamp = _data_cache[key]
        if time.time() - timestamp < DATA_CACHE_TTL:
            return value
        else:
            del _data_cache[key]
    return None


def cache_set(key: str, value: Any):
    """Сохранить в кэш"""
    _data_cache[key] = (value, time.time())


def cache_delete(key: str):
    """Удалить из кэша"""
    if key in _data_cache:
        del _data_cache[key]


def _convert_query(query: str) -> str:
    """Быстрая конвертация SQLite синтаксиса в PostgreSQL с кэшированием"""
    if query in _query_cache:
        return _query_cache[query]
    
    # Заменяем INSERT OR IGNORE INTO
    if 'INSERT OR IGNORE INTO' in query.upper():
        query = re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO', 'INSERT INTO', query, flags=re.IGNORECASE)
        query = query.rstrip(')') + ' ON CONFLICT DO NOTHING)'
    
    # Заменяем PRAGMA table_info
    pragma_match = re.search(r'PRAGMA\s+table_info\((.+?)\)', query, re.IGNORECASE)
    if pragma_match:
        table_name = pragma_match.group(1).strip()
        query = f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table_name}'"
    
    # Заменяем ? на $1, $2, $3...
    if '?' in query:
        counter = [0]
        def replace_param(match):
            counter[0] += 1
            return f'${counter[0]}'
        query = re.sub(r'\?', replace_param, query)
    
    _query_cache[query] = query
    return query


async def init_pool():
    """Инициализация пула соединений PostgreSQL"""
    global _pool
    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(
                dsn=DB_URL,
                min_size=20,
                max_size=50,
                command_timeout=30,
                connection_class=asyncpg.Connection,
            )
            print(f"[DB] Подключено к PostgreSQL: {DB_URL.split('@')[1] if '@' in DB_URL else 'unknown'}")
            
            async with _pool.acquire() as conn:
                # Основные таблицы
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS chat_registry (
                        chat_id BIGINT PRIMARY KEY,
                        peer_id BIGINT,
                        owner_id BIGINT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                print("[DB] Таблица chat_registry создана/проверена")
                
                # Таблицы для админов и ролей
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS ruk (
                        user_id BIGINT PRIMARY KEY
                    )
                """)
                print("[DB] Таблица ruk создана/проверена")
                
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS global_managers (
                        user_id BIGINT PRIMARY KEY,
                        level INTEGER DEFAULT 1
                    )
                """)
                print("[DB] Таблица global_managers создана/проверена")
                
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS top_whitelist (
                        user_id BIGINT PRIMARY KEY
                    )
                """)
                print("[DB] Таблица top_whitelist создана/проверена")
                
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS usprom (
                        user_id BIGINT,
                        promo TEXT,
                        PRIMARY KEY (user_id, promo)
                    )
                """)
                print("[DB] Таблица usprom создана/проверена")
            
            return _pool
        except Exception as e:
            print(f"[DB] Ошибка подключения: {e}")
            raise
    return _pool


async def get_pool() -> asyncpg.Pool:
    """Получить пул соединений"""
    if _pool is None:
        return await init_pool()
    return _pool


async def close_pool():
    """Закрытие пула соединений"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        print("[DB] Подключение закрыто")


async def execute(query: str, *args):
    """Выполнить запрос без возврата данных (С ИНВАЛИДАЦИЕЙ КЭША)"""
    global _last_query, _last_args
    pool = await get_pool()
    query = _convert_query(query)
    _last_query = query
    _last_args = args if args else ()
    
    # Очищаем кэш при записи данных
    query_upper = query.upper().strip()
    if query_upper.startswith(('INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE')):
        _result_cache.clear()
    
    if args:
        # Если передан один аргумент-кортеж/список — используем его как параметры
        if len(args) == 1 and isinstance(args[0], (tuple, list)):
            await pool.execute(query, *args[0])
        else:
            await pool.execute(query, *args)
    else:
        await pool.execute(query)


async def fetchone(query: Optional[str] = None, *args) -> Optional[Any]:
    """Выполнить запрос и вернуть одну строку (БЕЗ КЭША - для complex records)"""
    global _last_query, _last_args
    pool = await get_pool()
    
    if query is None:
        query = _last_query
        args = _last_args
    else:
        query = _convert_query(query)
    
    if args:
        if len(args) == 1 and isinstance(args[0], (tuple, list)):
            return await pool.fetchrow(query, *args[0])
        else:
            return await pool.fetchrow(query, *args)
    else:
        return await pool.fetchrow(query)


async def fetchall(query: Optional[str] = None, *args) -> List:
    """Выполнить запрос и вернуть все строки (БЕЗ КЭША - для complex records)"""
    global _last_query, _last_args
    pool = await get_pool()
    
    if query is None:
        query = _last_query
        args = _last_args
    else:
        query = _convert_query(query)
    
    if args:
        if len(args) == 1 and isinstance(args[0], (tuple, list)):
            return await pool.fetch(query, *args[0])
        else:
            return await pool.fetch(query, *args)
    else:
        return await pool.fetch(query)


async def fetchval(query: Optional[str] = None, *args) -> Any:
    """Выполнить запрос и вернуть одно значение (С КЭШИРОВАНИЕМ)"""
    global _last_query, _last_args
    pool = await get_pool()
    
    if query is None:
        query = _last_query
        args = _last_args
    else:
        query = _convert_query(query)
    
    # Проверяем кэш
    cached = cache_get_result(query, args)
    if cached is not None:
        return cached
    
    # Выполняем запрос
    if args:
        if len(args) == 1 and isinstance(args[0], (tuple, list)):
            result = await pool.fetchval(query, *args[0])
        else:
            result = await pool.fetchval(query, *args)
    else:
        result = await pool.fetchval(query)
    
    # Сохраняем в кэш
    cache_set_result(query, args, result)
    return result


async def executemany(query: str, records: List):
    """Выполнить пакетную вставку"""
    pool = await get_pool()
    await pool.executemany(query, records)


def sanitize_table_name(table: str) -> str:
    """Безопасная санитизация имени таблицы"""
    sanitized = "".join(c for c in table if c.isalnum() or c == '_')
    return sanitized


def get_table_name(base: str, chat_id: int) -> str:
    """Получить имя таблицы для конкретного чата"""
    return f"{base}_{sanitize_table_name(str(chat_id))}"


async def table_exists(table_name: str) -> bool:
    """Проверить, существует ли таблица"""
    pool = await get_pool()
    return await pool.fetchval(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
        table_name
    )


async def create_mutes_table(chat_id: int):
    """Создать таблицу мутов для чата"""
    table = get_table_name("mutes", chat_id)
    await execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            user_id BIGINT,
            moder TEXT,
            reason TEXT,
            date DOUBLE PRECISION,
            date_string TEXT,
            time BIGINT,
            expire_time DOUBLE PRECISION DEFAULT 0
        )
    """)


async def create_bans_table(chat_id: int):
    """Создать таблицу банов для чата"""
    table = get_table_name("bans", chat_id)
    await execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            user_id BIGINT,
            moder BIGINT,
            reason TEXT,
            date DOUBLE PRECISION,
            date_string TEXT,
            ban_time INTEGER DEFAULT 0,
            ban_expire DOUBLE PRECISION DEFAULT 0,
            ban_duration_text TEXT DEFAULT 'навсегда'
        )
    """)


async def create_messages_table(chat_id: int):
    """Создать таблицу сообщений для чата"""
    table = get_table_name("messages", chat_id)
    await execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            user_id BIGINT,
            date DOUBLE PRECISION,
            date_string TEXT,
            message_id BIGINT,
            cmid BIGINT
        )
    """)


async def create_permissions_table(chat_id: int):
    """Создать таблицу прав для чата"""
    table = get_table_name("permissions", chat_id)
    await execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            user_id BIGINT,
            level BIGINT
        )
    """)


async def create_nicks_table(chat_id: int):
    """Создать таблицу ников для чата"""
    table = get_table_name("nicks", chat_id)
    await execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            user_id BIGINT,
            nick TEXT
        )
    """)


async def create_warns_table(chat_id: int):
    """Создать таблицы варнов для чата"""
    table_warns = get_table_name("warns", chat_id)
    table_history = get_table_name("warnhistory", chat_id)
    
    await execute(f"""
        CREATE TABLE IF NOT EXISTS {table_warns} (
            user_id BIGINT,
            count BIGINT,
            moder BIGINT,
            reason TEXT,
            date DOUBLE PRECISION,
            date_string TEXT
        )
    """)
    
    await execute(f"""
        CREATE TABLE IF NOT EXISTS {table_history} (
            user_id BIGINT,
            count BIGINT,
            moder BIGINT,
            reason TEXT,
            date DOUBLE PRECISION,
            date_string TEXT
        )
    """)


async def create_vigs_table(chat_id: int):
    """Создать таблицы vig для чата"""
    table_vig = get_table_name("vig", chat_id)
    table_history = get_table_name("vighistory", chat_id)
    
    await execute(f"""
        CREATE TABLE IF NOT EXISTS {table_vig} (
            user_id BIGINT,
            count BIGINT,
            moder BIGINT,
            reason TEXT,
            date DOUBLE PRECISION,
            date_string TEXT
        )
    """)
    
    await execute(f"""
        CREATE TABLE IF NOT EXISTS {table_history} (
            user_id BIGINT,
            count BIGINT,
            moder BIGINT,
            reason TEXT,
            date DOUBLE PRECISION,
            date_string TEXT
        )
    """)


async def create_punishments_table(chat_id: int):
    """Создать таблицу наказаний для чата"""
    table = get_table_name("punishments", chat_id)
    await execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            user_id BIGINT,
            date TEXT
        )
    """)


async def init_chat_tables(chat_id: int):
    """Инициализировать все таблицы для нового чата"""
    await create_mutes_table(chat_id)
    await create_bans_table(chat_id)
    await create_messages_table(chat_id)
    await create_permissions_table(chat_id)
    await create_nicks_table(chat_id)
    await create_warns_table(chat_id)
    await create_vigs_table(chat_id)
    await create_punishments_table(chat_id)
    print(f"[DB] Все таблицы созданы для чата {chat_id}")


async def register_chat(chat_id: int, peer_id: int, owner_id: int):
    """Зарегистрировать чат в системе"""
    await execute(
        "INSERT INTO chat_registry (chat_id, peer_id, owner_id) VALUES ($1, $2, $3) ON CONFLICT (chat_id) DO UPDATE SET peer_id = $2, owner_id = $3",
        chat_id, peer_id, owner_id
    )
    print(f"[DB] Чат {chat_id} зарегистрирован")
