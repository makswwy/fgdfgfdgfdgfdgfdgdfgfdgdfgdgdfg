#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
from vkbottle.exception_factory import VKAPIError
import os, re
import re
import time
import urllib
import vk_api
import random
from random import randint
import requests
import datetime
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, date, timezone
from vkbottle import API
from vkbottle.bot import Bot, Message, rules
from typing import Optional, Dict
from vkbottle import Keyboard, Callback, CtxStorage, KeyboardButtonColor, Text, GroupEventType, GroupTypes, User, \
    VKAPIError
import json
import db
import locale
import dateparser

MOSCOW_TZ = timezone(timedelta(hours=3))

def moscow_now():
    return datetime.now(MOSCOW_TZ).replace(tzinfo=None)

def moscow_fromtimestamp(timestamp):
    return datetime.fromtimestamp(timestamp, MOSCOW_TZ).replace(tzinfo=None)

# ID бота (сообщества)
BOT_ID = -232598001  # Замените на ID вашего бота
BALANCES_FILE = "balances.json"
ctx = CtxStorage()
active = 'active'
noactive = 'noactive'
MAX_LOGS = 25
photo1 = 'photo-232598001_457239059'
bot_enabled = True
chat_mode = "global"
enabled_chats = set()
all_chat_title = []
chat_titles_string = ''
with open("config2.json", "r") as js:
    open_file = json.load(js)
current_duel = {}
api = API(open_file['bot-token'])
api.api_version = "5.131"
bot = Bot(api=api)
proxies = {"https": "http://XsUkQ1:Sz2GQM@172.67.176.135:80"}
API_KEY = "AIzaSyBBmKPcNMFgATngODvGu-sJ5tLtGddKhOM"
MODEL = "gemini-2.0-flash"
URL = f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}'
REGVK_URL = "https://regvk.com/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
SUBS_FILE = "SUBS_FILE.json"

# Импортируем данные об игровой экономике из game.py
from game import HOUSES_DATA, CARS_DATA, BUSINESS_TYPES

def format_duration_text(duration_minutes: int) -> str:
    """
    Форматирует время в минутах в читаемый текст
    Примеры: 1 -> "1 минуту", 2 -> "2 минуты", 5 -> "5 минут"
    """
    if duration_minutes <= 0:
        return "навсегда"

    # Преобразуем минуты в соответствующие единицы
    years = duration_minutes // 525600
    months = (duration_minutes % 525600) // 43200
    days = (duration_minutes % 43200) // 1440
    hours = (duration_minutes % 1440) // 60
    minutes = duration_minutes % 60

    parts = []

    if years > 0:
        if years == 1:
            parts.append("1 год")
        elif 2 <= years <= 4:
            parts.append(f"{years} года")
        else:
            parts.append(f"{years} лет")

    if months > 0:
        if months == 1:
            parts.append("1 месяц")
        elif 2 <= months <= 4:
            parts.append(f"{months} месяца")
        else:
            parts.append(f"{months} месяцев")

    if days > 0:
        if days == 1:
            parts.append("1 день")
        elif 2 <= days <= 4:
            parts.append(f"{days} дня")
        else:
            parts.append(f"{days} дней")

    if hours > 0:
        if hours == 1:
            parts.append("1 час")
        elif 2 <= hours <= 4:
            parts.append(f"{hours} часа")
        else:
            parts.append(f"{hours} часов")

    if minutes > 0:
        if minutes == 1:
            parts.append("1 мин")
        elif 2 <= minutes <= 4:
            parts.append(f"{minutes} минуты")
        else:
            parts.append(f"{minutes} минут")

    if not parts:
        return "навсегда"

    if len(parts) == 1:
        return parts[0]
    else:
        return " ".join(parts[:2])  # Показываем максимум 2 единицы

def load_data(file):
    if os.path.exists(file):
        try:
            with open(file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

# ========== НОВЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С СООБЩЕСТВАМИ ==========

async def is_bot(user_id: int) -> bool:
    """Проверить, является ли пользователь ботом (сообществом)"""
    return user_id == BOT_ID or user_id < 0 and abs(user_id) == abs(BOT_ID)

async def get_group_name(group_id: int) -> str:
    """Получить название сообщества по его ID"""
    try:
        abs_id = abs(group_id)
        response = await bot.api.groups.get_by_id(group_ids=[abs_id])

        # Получаем название через атрибут groups
        if hasattr(response, 'groups'):
            groups_list = response.groups
            if groups_list and len(groups_list) > 0:
                group_name = groups_list[0].name
                print(f"DEBUG: Получено название сообщества {abs_id}: {group_name}")
                return group_name

        print(
            f"DEBUG: Не удалось получить название для сообщества {abs_id}, groups_list: {getattr(response, 'groups', None)}")
        return f"ID{abs_id}"
    except Exception as e:
        print(f"Ошибка получения названия сообщества {group_id}: {e}")
        return f"ID{abs(group_id)}"

async def get_user_or_group_name(user_id: int) -> str:
    """Универсальная функция получения имени (пользователь или сообщество)"""
    if user_id < 0:
        return await get_group_name(user_id)
    else:
        return await get_user_name(user_id)

async def get_user_or_group_mention(user_id: int, chat_id: int = None) -> str:
    """Универсальная функция получения упоминания (пользователь или сообщество)"""
    if user_id < 0:
        name = await get_group_name(user_id)
        return f"[club{abs(user_id)}|{name}]"
    else:
        # Проверяем, есть ли ник для этого пользователя в чате
        if chat_id and chat_id > 0:
            nick = await get_nick(user_id, chat_id)
            if nick:
                return f"[id{user_id}|{nick}]"
        # Если ника нет - получаем имя и фамилию через API
        user_name = await get_user_name(user_id)
        return f"[id{user_id}|{user_name}]"

def format_vk_link(user_id: int, name: str) -> str:
    """Форматирует ссылку на пользователя VK"""
    safe_name = str(name).replace("|", " ").replace("]", ")").replace("\n", " ").replace("\r", " ")
    if int(user_id) < 0:
        return f"[club{abs(user_id)}|{safe_name}]"
    else:
        return f"[id{user_id}|{safe_name}]"

async def get_chat_owner_display(chat_id: int) -> str:
    """Получить владельца чата с красивым отображением"""
    try:
        owner_id_result = await db.fetchone('SELECT owner_id FROM chats WHERE chat_id = $1', chat_id,)
        
        if not owner_id_result:
            return "Неизвестно"
        
        owner_id = owner_id_result[0]
        
        # Проверяем, владелец - сообщество (отрицательный ID)
        if owner_id < 0:
            # Получаем название сообщества
            try:
                group_info = await bot.api.groups.getById(group_ids=[abs(owner_id)])
                if group_info and len(group_info) > 0:
                    group_name = group_info[0].name
                    return f"[club{abs(owner_id)}|{group_name}]"
            except:
                pass
            return f"[club{abs(owner_id)}|Владелец беседы]"

        # Проверяем, есть ли ник у владельца в этом чате
        nick = await get_nick(owner_id, chat_id)
        
        # Если есть ник - используем его
        if nick:
            return f"[id{owner_id}|{nick}]"
        
        # Получаем имя пользователя
        owner_name = await get_user_name(owner_id)
        
        # Проверяем глобальную роль владельца
        global_role = await db.fetchone('SELECT level FROM global_managers WHERE user_id = $1', owner_id,)
        
        if global_role and global_role[0] >= 9:
            return f"[id{owner_id}|Владелец беседы (Global Manager)]"
        
        return f"[id{owner_id}|Владелец беседы]"
    except Exception as e:
        print(f"Ошибка в get_chat_owner_display: {e}")
        return "Неизвестно"

# ========== ОСТАЛЬНЫЕ ФУНКЦИИ ==========

async def getID(arg: str):
    arg_split = arg.split("|")
    if arg_split[0] == arg:
        try:
            if any(domain in arg for domain in ["vk.com/", "vk.me/", "vk.ru/"]):
                clean_arg = (
                    arg.replace("https://", "")
                    .replace("http://", "")
                    .replace("www.", "")
                )
                for domain in ["vk.com/", "vk.me/", "vk.ru/"]:
                    if domain in clean_arg:
                        clean_arg = clean_arg.split(domain)[1]
                        break
                scr_split = await bot.api.utils.resolve_screen_name(clean_arg)
                x = json.loads(scr_split.json())
                return int(x["object_id"])
        except:
            pass
        com_split = arg.split("vk.com/id")
        try:
            if com_split[1].isnumeric():
                return com_split[1]
            else:                return False
        except:
            for domain in ["vk.com/", "vk.me/", "vk.ru/"]:
                if domain in arg:
                    try:
                        screen_split = arg.split(domain)
                        scr_split = await bot.api.utils.resolve_screen_name(screen_split[1])
                        ut_split = str(scr_split).split(" ")
                        obj_split = ut_split[1].split("_id=")
                        if not obj_split[1].isnumeric():
                            return False
                        return obj_split[1]
                    except:
                        return False
    try:
        id_split = arg_split[0].split("id")
        return int(id_split[1])
    except:
        return False

async def is_user_muted(user_id=int, chat_id=int):
    """Быстрая проверка, есть ли у пользователя активный мут"""
    fetch = await db.fetchone(f"SELECT * FROM mutes_{chat_id} WHERE user_id = $1", (user_id,))

    if not fetch:
        return False

    mute_time = fetch[5]

    # Бессрочный мут
    if mute_time <= 0:
        return True

    # Проверяем время
    mute_start = fetch[3]
    current_time = time.time()
    expire_time = mute_start + (mute_time * 60)

    if current_time > expire_time:
        # Мут истек - удаляем
        await db.execute(f"DELETE FROM mutes_{chat_id} WHERE user_id = $1", (user_id,))
        pass
        await apply_system_mute(chat_id, user_id, unmute=True)
        return False

    return True

async def get_registration_date(user_id):
    try:
        locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    except locale.Error:
        print("Не удалось установить локаль ru_RU.UTF-8")
    try:
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar()) as session:
            async with session.get(REGVK_URL, headers={"User-Agent": USER_AGENT}) as initial_response:
                await initial_response.text()
            async with session.post(REGVK_URL, data={"link": user_id, "button": "Определить дату регистрации"},
                                    headers={"User-Agent": USER_AGENT}) as response:
                response.raise_for_status()
                html = await response.text()
            soup = BeautifulSoup(html, "html.parser")
            td_elements = soup.find_all('td')
            for td in td_elements:
                if "Дата регистрации:" in td.text:
                    date_string = re.sub(r"Дата регистрации:\s*", "", td.text).strip()
                    try:
                        date = dateparser.parse(date_string, languages=['ru'])
                        if date:
                            registration_date = date.date()
                            return registration_date
                        else:
                            print("Не удалось распарсить дату с помощью dateparser")
                    except ValueError as e:
                        print(f"Ошибка при парсинге даты: {e}")
                        return None
    except aiohttp.ClientError as e:
        print(f"Ошибка при запросе к сайту: {e}")
        return None
    except Exception as e:
        print(f"Неизвестная ошибка: {e}")
        return None

def get_string(words_list, start_index=0):
    result = " ".join(words_list[start_index:])
    return result if result else False

# Database connection via db.py (PostgreSQL)
# blacklist table created automatically by db.py

async def topsms(chat_id):
    try:
        # Получаем всех пользователей и считаем количество их сообщений
        query = f"SELECT user_id, COUNT(*) as msg_count FROM messages_{chat_id} GROUP BY user_id ORDER BY msg_count DESC LIMIT 10"
        top_users = await db.fetchall(query)

        if not top_users:
            return "В этой беседе пока нет сообщений!"

        result = '📊 Топ 10 самых активных пользователей в беседе:\n\n'
        for i, (user_id, msg_count) in enumerate(top_users):
            msg_count_formatted = f'{msg_count:,d}'.replace(',', '.')
            user_display = await get_user_or_group_mention(user_id)
            result += f'💬 Топ {i + 1}. {user_display} | {msg_count_formatted} сообщений\n'

        return result
    except Exception as e:
        print(f"Ошибка в topsms: {e}")
        return "Не удалось получить статистику сообщений"

async def check_chat(chat_id=int):
    result = await db.fetchone(f"SELECT * FROM chats WHERE chat_id = {chat_id}")
    if result == None:
        return False
    else:
        return True

async def chats_log(user_id=None, target_id=None, role=None, log=None):
    try:
        await db.execute(
            "INSERT INTO logchats (user_id, target_id, role, log) VALUES ($1, $2, $3, $4)",
            (user_id, target_id, role, log)
        )
        pass
    except Exception as e:
        print(f"")

async def new_chat(chat_id=int, peer_id=int, owner_id=int):
    await db.execute(f"INSERT INTO chats VALUES ($1, $2, $3, '', 0, 0, 0, 0, 0, 0, 0, 0);", (chat_id, peer_id, owner_id))
    await db.execute(f"CREATE TABLE IF NOT EXISTS permissions_{chat_id} (user_id BIGINT, level BIGINT);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS balance (user_id BIGINT, money BIGINT, blago BIGINT, bank BIGINT);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS staffbot (user_id BIGINT, level BIGINT);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS ruk (user_id BIGINT);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS logsrole (user BIGINT, role BIGINT, chat_id BIfGINT, date_string TEXT);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS economy (user_id INTEGER, target_id INTEGER, amount INTEGER, log TEXT);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS logchats (user_id INTEGER, target_id INTEGER, role INTEGER, log TEXT);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS rules (chat_id BIGINT, text Text);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS info (chat_id BIGINT, text Text);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS banschats (chat_id BIGINT);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS photosettings (chat_id BIGINT NOT NULL PRIMARY KEY,mode INT NOT NULL);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS usprom (user_id BIGINT, promo TEXT);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS vip (user_id BIGINT, date_string TEXT);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS nicks_{chat_id} (user_id BIGINT, nick TEXT);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS promo (promo TEXT, status TEXT, vip BIGINT, money BIGINT);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS banwords_{chat_id} (banword TEXT);")
    await db.execute(
        f"CREATE TABLE IF NOT EXISTS warns_{chat_id} (user_id BIGINT, count BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
    await db.execute(
        f"CREATE TABLE IF NOT EXISTS vig_{chat_id} (user_id BIGINT, count BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
    await db.execute(
        f"CREATE TABLE IF NOT EXISTS mutes_{chat_id} (user_id BIGINT, moder TEXT, reason TEXT, date BIGINT, date_string TEXT, time BIGINT);")
    await db.execute(
        f"CREATE TABLE IF NOT EXISTS bans_{chat_id} (user_id BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
    await db.execute(
        f"CREATE TABLE IF NOT EXISTS gbans (user_id BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
    await db.execute(
        f"CREATE TABLE IF NOT EXISTS messages_{chat_id} (user_id BIGINT, date BIGINT, date_string TEXT, message_id BIGINT, cmid BIGINT);")
    await db.execute(
        f'CREATE TABLE IF NOT EXISTS users (user_id BIGINT, last_bonus TIMESTAMP DEFAULT NULL);')
    await db.execute(
        f"CREATE TABLE IF NOT EXISTS warnhistory_{chat_id} (user_id BIGINT, count BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
    await db.execute(
        f"CREATE TABLE IF NOT EXISTS vighistory_{chat_id} (user_id BIGINT, count BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS punishments_{chat_id} (user_id BIGINT, date TEXT);")
    await db.execute("CREATE TABLE IF NOT EXISTS blacklist (user_id BIGINT PRIMARY KEY, moderator_id BIGINT, reason TEXT, datetime TEXT);")
    await db.execute(
        f"CREATE TABLE IF NOT EXISTS jobs (user_id BIGINT PRIMARY KEY, job_id INTEGER, skill INTEGER, last_work_time TEXT);")
    await db.execute(f"CREATE TABLE IF NOT EXISTS user_skills (user_id BIGINT PRIMARY KEY, skill INTEGER);")
    await db.execute("CREATE TABLE IF NOT EXISTS clans ("
                "clan_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name TEXT UNIQUE, "
                "tag TEXT UNIQUE, "
                "leader_id BIGINT, "
                "level INTEGER DEFAULT 1, "
                "exp INTEGER DEFAULT 0, "
                "bank BIGINT DEFAULT 0, "
                "members_count INTEGER DEFAULT 1, "
                "wins INTEGER DEFAULT 0, "
                "losses INTEGER DEFAULT 0, "
                "created_date TEXT)")

    await db.execute("CREATE TABLE IF NOT EXISTS clan_members ("
                "user_id BIGINT PRIMARY KEY, "
                "clan_id INTEGER, "
                "role TEXT DEFAULT 'member', "  # leader, deputy, member
                "joined_date TEXT, "
                "donated BIGINT DEFAULT 0, "
                "FOREIGN KEY(clan_id) REFERENCES clans(clan_id))")

    await db.execute("CREATE TABLE IF NOT EXISTS clan_wars ("
                "war_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "clan1_id INTEGER, "
                "clan2_id INTEGER, "
                "bet BIGINT, "
                "winner_id INTEGER DEFAULT NULL, "
                "status TEXT DEFAULT 'pending', "  # pending, active, finished
                "start_time TEXT, "
                "end_time TEXT, "
                "clan1_score INTEGER DEFAULT 0, "
                "clan2_score INTEGER DEFAULT 0, "
                "FOREIGN KEY(clan1_id) REFERENCES clans(clan_id), "
                "FOREIGN KEY(clan2_id) REFERENCES clans(clan_id))")

    await db.execute("CREATE TABLE IF NOT EXISTS clan_invites ("
                "invite_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "clan_id INTEGER, "
                "user_id BIGINT, "
                "inviter_id BIGINT, "
                "date TEXT, "
                "FOREIGN KEY(clan_id) REFERENCES clans(clan_id))")

    await db.execute("CREATE TABLE IF NOT EXISTS clan_battles ("
                "battle_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "war_id INTEGER, "
                "user1_id BIGINT, "
                "user2_id BIGINT, "
                "winner_id BIGINT DEFAULT NULL, "
                "bet BIGINT, "
                "status TEXT DEFAULT 'pending', "
                "FOREIGN KEY(war_id) REFERENCES clan_wars(war_id))")
    await db.execute(
        "CREATE TABLE IF NOT EXISTS jobs (user_id BIGINT PRIMARY KEY, job_id INTEGER, skill INTEGER DEFAULT 0, last_work_time TEXT)")
    await db.execute("CREATE TABLE IF NOT EXISTS business_types ("
                "biz_id INTEGER PRIMARY KEY, "
                "name TEXT, "
                "emoji TEXT, "
                "price BIGINT, "
                "min_profit BIGINT, "
                "max_profit BIGINT, "
                "description TEXT)")

    await db.execute("CREATE TABLE IF NOT EXISTS user_businesses ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "user_id BIGINT, "
                "biz_id INTEGER, "
                "purchase_date TEXT, "
                "last_collected TEXT, "
                "balance BIGINT DEFAULT 0, "
                "FOREIGN KEY(biz_id) REFERENCES business_types(biz_id), "
                "UNIQUE(user_id, biz_id))")

    pass

# Словарь для хранения замьюченных пользователей в памяти
muted_users_cache = {}  # Формат: {f"{chat_id}_{user_id}": {"expire_time": timestamp, "moder": id, "reason": reason}}

# Исправленная функция apply_system_mute - теперь НЕ кикает пользователя!
async def apply_system_mute(chat_id: int, user_id: int, duration_minutes: int = None, unmute: bool = False):
    """
    Наложить или снять системный мут через VK API
    Теперь НЕ кикает пользователя, а только возвращает статус
    """
    try:
        if unmute:
            # При снятии мута просто возвращаем успех
            # Пользователь может писать сообщения (они не будут удаляться)
            return {"success": True, "message": "Мут снят", "api_success": True}
        else:
            # При наложении мута НЕ кикаем пользователя!
            # Просто возвращаем успех - сообщения будет удалять обработчик
            time_text = "бессрочно" if not duration_minutes or duration_minutes <= 0 else f"на {duration_minutes} мин"
            return {"success": True, "message": f"Мут наложен {time_text}", "api_success": True}

    except Exception as e:
        print(f"Неизвестная ошибка в apply_system_mute: {e}")
        return {"success": False, "message": f"❌ Неизвестная ошибка: {e}"}

# Исправленная функция mute
async def mute(user_id=int, chat_id=int, moder=int, reason=str, mute_time=int):
    """
    Записать мут в базу данных
    mute_time: время в минутах (0 - бессрочно)
    """
    cd = str(moscow_now()).split('.')
    date_string = cd[0]
    current_timestamp = time.time()

    # Рассчитываем время окончания мута
    if mute_time > 0:
        expire_time = current_timestamp + (mute_time * 60)
    else:
        expire_time = 0  # 0 = бессрочно

    # Просто записываем в БД, НЕ кикаем пользователя
    mute_result = {"success": True, "message": "Мут наложен"}

    # Добавляем в кэш
    cache_key = f"{chat_id}_{user_id}"
    muted_users_cache[cache_key] = {
        "expire_time": expire_time,
        "moder": moder,
        "reason": reason,
        "date": current_timestamp
    }

    # Удаляем старую запись если есть
    try:
        await db.execute(f"DELETE FROM mutes_{chat_id} WHERE user_id = $1", (user_id,))
    except:
        pass

    # Создаем новую запись
    try:
        # Пробуем вставить с expire_time
        await db.execute(
            f"INSERT INTO mutes_{chat_id} (user_id, moder, reason, date, date_string, time, expire_time) VALUES ($1, $2, $3, $4, $5, $6, $7)",
            (user_id, moder, reason, current_timestamp, date_string, mute_time, expire_time)
        )
    except Exception:
        # Если нет колонки expire_time, вставляем без неё
        await db.execute(
            f"INSERT INTO mutes_{chat_id} (user_id, moder, reason, date, date_string, time) VALUES ($1, $2, $3, $4, $5, $6)",
            (user_id, moder, reason, current_timestamp, date_string, mute_time)
        )

    pass

    return {
        "success": True,
        "message": mute_result["message"],
        "moder_id": moder,
        "user_id": user_id,
        "chat_id": chat_id,
        "reason": reason,
        "duration": mute_time,
        "expire_time": expire_time
    }

# Функция для проверки мута (быстрая, с кэшем)
async def is_muted(user_id=int, chat_id=int):
    """Быстрая проверка, есть ли у пользователя активный мут"""
    cache_key = f"{chat_id}_{user_id}"

    # Игровой мут мафии хранится отдельно и управляется игровым ботом.
    try:
        await db.execute("CREATE TABLE IF NOT EXISTS mafia_mutes (chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, PRIMARY KEY (chat_id, user_id))")
        if await db.fetchone("SELECT 1 FROM mafia_mutes WHERE chat_id = $1 AND user_id = $2", (chat_id, user_id)):

            return True
    except Exception:
        pass

    # Проверяем в кэше
    if cache_key in muted_users_cache:
        mute_data = muted_users_cache[cache_key]

        # Проверяем, не истек ли мут
        if mute_data["expire_time"] > 0 and time.time() > mute_data["expire_time"]:
            # Мут истек - удаляем из кэша и БД
            del muted_users_cache[cache_key]
            await unmute(user_id, chat_id, auto=True)
            return False

        return True  # Мут активен

    # Если нет в кэше, проверяем в БД
    try:
        mute_data = await db.fetchone(f"SELECT * FROM mutes_{chat_id} WHERE user_id = $1", (user_id,))

        if mute_data:
            mute_time = mute_data[5]  # время в минутах
            current_time = mute_data[3]  # timestamp начала

            # Проверяем expire_time если есть
            try:
                expire_idx = 7
                if len(mute_data) > expire_idx and mute_data[expire_idx]:
                    expire_time = mute_data[expire_idx]
                else:
                    if mute_time > 0:
                        expire_time = current_time + (mute_time * 60)
                    else:
                        expire_time = 0
            except:
                if mute_time > 0:
                    expire_time = current_time + (mute_time * 60)
                else:
                    expire_time = 0

            # Проверяем, не истек ли мут
            if expire_time > 0 and time.time() > expire_time:
                await unmute(user_id, chat_id, auto=True)
                return False

            # Добавляем в кэш
            muted_users_cache[cache_key] = {
                "expire_time": expire_time,
                "moder": mute_data[1],
                "reason": mute_data[2],
                "date": current_time
            }
            return True
    except:
        pass

    return False

# Исправленная функция unmute
async def unmute(user_id=int, chat_id=int, auto=False):
    """
    Снять мут (удалить из БД)
    auto: True если автоматическое снятие
    """
    # Удаляем из кэша
    cache_key = f"{chat_id}_{user_id}"
    if cache_key in muted_users_cache:
        del muted_users_cache[cache_key]

    # Удаляем из БД
    try:
        await db.execute(f"DELETE FROM mutes_{chat_id} WHERE user_id = $1", (user_id,))
        pass
    except:
        pass

    return {"success": True, "auto": auto}

# Исправленная функция get_mute
async def get_mute(user_id=int, chat_id=int):
    """Получить информацию о муте из БД"""
    fetch = await db.fetchone(f"SELECT * FROM mutes_{chat_id} WHERE user_id = $1", (user_id,))

    if fetch == None:
        return False
    else:
        mute_time = fetch[5]
        mute_start = fetch[3]

        if mute_time > 0:
            expire_time = mute_start + (mute_time * 60)
        else:
            expire_time = 0

        return {
            'moder': fetch[1],
            'reason': fetch[2],
            'date': mute_start,
            'date_string': fetch[4],
            'time': mute_time,
            'expire_time': expire_time
        }

# Исправленная функция mutelist
async def mutelist(chat_id=int):
    fetch = await db.fetchall(f"SELECT * FROM mutes_{chat_id}")

    mutes = []
    if fetch == None or len(fetch) == 0:
        return False
    else:
        for i in fetch:
            mute_time = i[5]
            mute_start = i[3]

            if mute_time > 0:
                expire_time = mute_start + (mute_time * 60)
                if time.time() > expire_time:
                    # Мут истек - пропускаем
                    continue
                expire_datetime = moscow_fromtimestamp(expire_time)
                time_text = expire_datetime.strftime('%d.%m.%Y %H:%M')
            else:
                time_text = "навсегда"

            user_display = await get_user_or_group_mention(i[0])
            moder_display = await get_user_or_group_mention(i[1]) if i[1] != "Бот" and i[1] != "Bot" else "Бот"

            mutes.append(f"{user_display} | {i[2]} | {moder_display} | До: {time_text}")
    return mutes

# Функция для очистки истекших мутов
async def cleanup_mutes():
    """Периодически проверяет и удаляет истекшие муты"""
    while True:
        try:
            current_time = time.time()

            # Проверяем кэш
            to_delete = []
            for key, data in muted_users_cache.items():
                if data["expire_time"] > 0 and current_time > data["expire_time"]:
                    to_delete.append(key)
                    chat_id, user_id = map(int, key.split('_'))
                    await unmute(user_id, chat_id, auto=True)

            for key in to_delete:
                if key in muted_users_cache:
                    del muted_users_cache[key]

            # Проверяем БД
            try:
                tables = await db.fetchall("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'mutes_%'")

                for table in tables:
                    table_name = table[0]
                    chat_id = int(table_name.replace('mutes_', ''))

                    rows = await db.fetchall(f"SELECT user_id, date, time FROM {table_name}")

                    for row in rows:
                        user_id, mute_start, duration = row
                        if duration > 0:
                            expire_time = mute_start + (duration * 60)
                            if current_time > expire_time:
                                await unmute(user_id, chat_id, auto=True)
            except:
                pass

            # Проверяем каждые 30 секунд
            await asyncio.sleep(30)

        except Exception as e:
            print(f"Ошибка в cleanup_mutes: {e}")
            await asyncio.sleep(60)

# Функция для обновления таблиц мутов
async def update_mutes_tables():
    """Обновляет таблицы мутов, добавляя колонку expire_time"""
    try:
        tables = await db.fetchall("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'mutes_%'")

        for table in tables:
            table_name = table[0]

            # Проверяем наличие колонки expire_time
            columns = await db.fetchall(f"PRAGMA table_info({table_name})")

            column_names = [col[1] for col in columns]

            if 'expire_time' not in column_names:
                try:
                    await db.execute(f"ALTER TABLE {table_name} ADD COLUMN expire_time REAL")
                    pass
                    print(f"Добавлена колонка expire_time в {table_name}")
                except Exception as e:
                    print(f"Ошибка при обновлении {table_name}: {e}")
    except Exception as e:
        print(f"Ошибка в update_mutes_tables: {e}")

# Кэш для ролей пользователей (user_id, chat_id) -> role
_role_cache: Dict[tuple, tuple] = {}
_ROLE_CACHE_TTL = 10  # секунды


async def get_role_cached(user_id, chat_id):
    """Получить роль с кэшированием"""
    key = (user_id, chat_id)
    now = time.time()
    
    if key in _role_cache:
        role, timestamp = _role_cache[key]
        if now - timestamp < _ROLE_CACHE_TTL:
            return role
    
    role = await get_role_cached(user_id, chat_id)
    _role_cache[key] = (role, now)
    return role


async def get_role_cached(user_id=int, chat_id=int):
    user_id = int(user_id)
    chat_id = int(chat_id)

    # Таблица локальных прав может отсутствовать в новом/ещё не инициализированном чате.
    # Создаём её до любого SELECT, чтобы обработчик сообщения не падал.
    await db.execute(
        f"CREATE TABLE IF NOT EXISTS permissions_{chat_id} ("
        "user_id BIGINT, level BIGINT)"
    )
    pass

    # ПРОВЕРЯЕМ ГЛОБАЛЬНУЮ РОЛЬ ПЕРВОЙ И С ПРИОРИТЕТОМ
    fetch = await db.fetchone('SELECT level FROM global_managers WHERE user_id = $1', user_id,)
    if fetch and fetch[0] is not None and fetch[0] > 0:
        print(f"DEBUG get_role: user={user_id}, chat={chat_id} -> GLOBAL ROLE = {fetch[0]}")
        return fetch[0]

    # Если глобальной роли нет, проверяем локальную.
    chat_owner = await db.fetchone('SELECT owner_id FROM chats WHERE chat_id = $1', chat_id,)
    if chat_owner and chat_owner[0] == user_id:
        print(f"DEBUG get_role: user={user_id}, chat={chat_id} -> OWNER ROLE = 7")
        return 7

    fetch = await db.fetchone(
        f"SELECT level FROM permissions_{chat_id} WHERE user_id = $1",
        (user_id,),
    )
    if fetch is None or fetch[0] is None:
        print(f"DEBUG get_role: user={user_id}, chat={chat_id} -> NO ROLE = 0")
        return 0

    print(f"DEBUG get_role: user={user_id}, chat={chat_id} -> LOCAL ROLE = {fetch[0]}")
    return fetch[0]

async def ensure_column_exists(table_name, column_name, column_type="INTEGER"):
    columns = await db.fetchall(f"PRAGMA table_info({table_name})")

    column_names = [col[1] for col in columns]
    if column_name not in column_names:
        print(f"Колонка '{column_name}' не найдена в таблице '{table_name}'. Создаем...")
        try:
            await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            print(f"Колонка '{column_name}' успешно создана.")
            pass
        except sqlite3.OperationalError as e:
            print(f"Ошибка при создании колонки '{column_name}': {e}")
            database.rollback()
    else:
        print(f"Колонка '{column_name}' уже существует в таблице '{table_name}'. Ничего не делаем.")

async def ensure_column_delete(table_name=str):
    print(1, table_name)
    await db.execute(f"DELETE FROM promo WHERE promo = $1", (table_name,))
    print(f"Колонка '{table_name}' успешно удалена.")
    pass

async def get_warns(user_id=int, chat_id=int):
    fetch = await db.fetchone(f"SELECT count FROM warns_{chat_id} WHERE user_id = {user_id}")

    if fetch == None:
        return 0
    else:
        return fetch[0]

async def get_vig(user_id=int, chat_id=int):
    fetch = await db.fetchone(f"SELECT count FROM vig_{chat_id} WHERE user_id = {user_id}")

    if fetch == None:
        return 0
    else:
        return fetch[0]

async def get_user_name(user_id=int):
    try:
        info = await bot.api.users.get(user_id=[user_id], fields=['first_name', 'last_name', 'screen_name'])
        if not info:
            print(f"API вернул пустой список для user_id: {user_id}.")
            return f"ID{user_id}"
        first_name = info[0].first_name
        last_name = info[0].last_name
        display_name = f"{first_name} {last_name}"
        return display_name
    except Exception as e:
        print(f"Ошибка получения имени пользователя {user_id}: {e}")
        return f"ID{user_id}"

async def is_nick(user_id=int, chat_id=int):
    if await db.fetchone(f"SELECT nick FROM nicks_{chat_id} WHERE user_id = {user_id}") == None:
        return False
    else:
        return True

async def setnick(user_id=int, chat_id=int, new_nick=str):
    if await db.fetchone(f"SELECT nick FROM nicks_{chat_id} WHERE user_id = {user_id}") == None:
        await db.execute(f"INSERT INTO nicks_{chat_id} VALUES ($1, $2)", (user_id, new_nick))
        pass
    else:
        await db.execute(f"UPDATE nicks_{chat_id} SET nick = $1 WHERE user_id = $2", (new_nick, user_id))
        pass

async def rnick(user_id=int, chat_id=int):
    await db.execute(f"DELETE FROM nicks_{chat_id} WHERE user_id = {user_id}")
    pass

async def equals_roles(user_id_sender=int, user_id_two=int, chat_id=int):
    role_sender = await get_role_cached(user_id_sender, chat_id) or 0
    role_two = await get_role_cached(user_id_two, chat_id) or 0
    
    if role_sender > role_two:
        return 2
    elif role_sender == role_two:
        return 1
    else:
        return 0

async def get_acc(chat_id=int, nick=str):
    fetch = await db.fetchone(f"SELECT user_id FROM nicks_{chat_id} WHERE nick = '{nick}'")

    if fetch == None:
        return False
    else:
        return fetch[0]

async def get_nick(user_id=int, chat_id=int):
    fetch = await db.fetchone(f"SELECT nick FROM nicks_{chat_id} WHERE user_id = {user_id}")

    if fetch == None:
        return False
    else:
        return fetch[0]

async def nlist(chat_id=int, page=int):
    fetch = await db.fetchall(f"SELECT * FROM nicks_{chat_id}")

    nicks = []
    gi = 0
    with open("config2.json", "r") as json_file:
        openopen_file = json.load(json_file)
    max_nicks = open_file['nicks_max']
    for i in fetch:
        gi += 1
        if page * max_nicks >= gi > page * max_nicks - max_nicks:
            user_id = i[0]
            user_display = await get_user_or_group_mention(user_id)
            nick_data = i[1] if len(i) > 1 else "Нет данных"
            nicks.append(f'{gi}) {user_display} - {nick_data}')
    return nicks

async def nonick(chat_id=int, page=int):
    fetch = await db.fetchall(f"SELECT * FROM nicks_{chat_id}")

    nicks = []
    for i in fetch:
        nicks.append(i[0])
    gi = 0
    nonick = []
    with open("config2.json", "r") as json_file:
        open_file = json.load(json_file)
    max_nonick = open_file['nonick_max']
    users = await bot.api.messages.get_conversation_members(peer_id=2000000000 + chat_id)
    users = json.loads(users.json())
    for i in users["profiles"]:
        if not i['id'] in nicks:
            gi = gi + 1
            if page * max_nonick >= gi and page * max_nonick - max_nonick < gi:
                user_display = await get_user_or_group_mention(i['id'])
                nonick.append(f"{gi}) {user_display}")
    return nonick

async def warn(chat_id=int, user_id=int, moder=int, reason=str):
    actualy_warns = await get_warns(user_id, chat_id)
    date = time.time()
    cd = str(moscow_now()).split('.')
    date_string = cd[0]
    await db.execute(f"INSERT INTO warnhistory_{chat_id} VALUES ($1, {actualy_warns + 1}, $2, $3, {date}, '{date_string}')",
                (user_id, moder, reason))
    pass
    if actualy_warns < 1:
        await db.execute(f"INSERT INTO warns_{chat_id} VALUES ($1, 1, $2, $3, {date}, '{date_string}')",
                    (user_id, moder, reason))
        pass
        return 1
    else:
        await db.execute(
            f"UPDATE warns_{chat_id} SET user_id = $1, count = $2, moder = $3, reason = $4, date = {date}, date_string = '{date_string}' WHERE user_id = {user_id}",
            (user_id, actualy_warns + 1, moder, reason))
        pass
        return actualy_warns + 1

async def vigs(chat_id=int, user_id=int, moder=int, reason=str):
    actualy_warns = await get_vig(user_id, chat_id)
    date = time.time()
    cd = str(moscow_now()).split('.')
    date_string = cd[0]
    await db.execute(f"INSERT INTO vighistory_{chat_id} VALUES ($1, {actualy_warns + 1}, $2, $3, {date}, '{date_string}')",
                (user_id, moder, reason))
    pass
    if actualy_warns < 1:
        await db.execute(f"INSERT INTO vig_{chat_id} VALUES ($1, 1, $2, $3, {date}, '{date_string}')",
                    (user_id, moder, reason))
        pass
        return 1
    else:
        await db.execute(
            f"UPDATE vig_{chat_id} SET user_id = $1, count = $2, moder = $3, reason = $4, date = {date}, date_string = '{date_string}' WHERE user_id = {user_id}",
            (user_id, actualy_warns + 1, moder, reason))
        pass
        return actualy_warns + 1

async def clear_warns(chat_id=int, user_id=int):
    await db.execute(f"DELETE FROM warns_{chat_id} WHERE user_id = {user_id}")
    pass

async def unwarn(chat_id=int, user_id=int):
    warns = await get_warns(user_id, chat_id)
    if warns < 2:
        await clear_warns(chat_id, user_id)
    else:
        await db.execute(f"UPDATE warns_{chat_id} SET count = {warns - 1} WHERE user_id = {user_id}")
        pass
    return warns - 1

async def clear_vig(chat_id=int, user_id=int):
    await db.execute(f"DELETE FROM vig_{chat_id} WHERE user_id = {user_id}")
    pass

async def unvig(chat_id=int, user_id=int):
    warns = await get_vig(user_id, chat_id)
    if warns < 2:
        await clear_vig(chat_id, user_id)
    else:
        await db.execute(f"UPDATE vig_{chat_id} SET count = {warns - 1} WHERE user_id = {user_id}")
        pass
    return warns - 1

async def gvig(user_id=int, chat_id=int):
    fetch = await db.fetchone(f"SELECT * FROM vig_{chat_id} WHERE user_id = {user_id}")

    if fetch == None:
        return False
    else:
        return {
            'count': fetch[1],
            'moder': fetch[2],
            'reason': fetch[3],
            'time': fetch[5]
        }

async def vighistory(user_id=int, chat_id=int):
    fetch = await db.fetchall(f"SELECT * FROM vighistory_{chat_id} WHERE user_id = {user_id}")

    warnhistory_mass = []
    gi = 0
    if fetch == None:
        return False
    else:
        for i in fetch:
            gi = gi + 1
            moder_display = await get_user_or_group_mention(i[2])
            warnhistory_mass.append(f"{gi}) {moder_display} | {i[3]} | {i[5]}")
    return warnhistory_mass

async def viglist(chat_id=int):
    fetch = await db.fetchall(f"SELECT * FROM vig_{chat_id}")

    warns = []
    gi = 0
    for i in fetch:
        gi = gi + 1
        user_display = await get_user_or_group_mention(i[0])
        moder_display = await get_user_or_group_mention(i[2])
        warns.append(f"{gi}) {user_display} | {i[3]} | {moder_display} | {i[1]}/3 | {i[5]}")
    if fetch == None: return False
    return warns

async def gwarn(user_id=int, chat_id=int):
    fetch = await db.fetchone(f"SELECT * FROM warns_{chat_id} WHERE user_id = {user_id}")

    if fetch == None:
        return False
    else:
        return {
            'count': fetch[1],
            'moder': fetch[2],
            'reason': fetch[3],
            'time': fetch[5]
        }

async def warnhistory(user_id=int, chat_id=int):
    fetch = await db.fetchall(f"SELECT * FROM warnhistory_{chat_id} WHERE user_id = {user_id}")

    warnhistory_mass = []
    gi = 0
    if fetch == None:
        return False
    else:
        for i in fetch:
            gi = gi + 1
            moder_display = await get_user_or_group_mention(i[2])
            warnhistory_mass.append(f"{gi}) {moder_display} | {i[3]} | {i[5]}")
    return warnhistory_mass

async def warnlist(chat_id=int):
    fetch = await db.fetchall(f"SELECT * FROM warns_{chat_id}")

    warns = []
    gi = 0
    for i in fetch:
        gi = gi + 1
        user_display = await get_user_or_group_mention(i[0])
        moder_display = await get_user_or_group_mention(i[2])
        warns.append(f"{gi}) {user_display} | {i[3]} | {moder_display} | {i[1]}/3 | {i[5]}")
    if fetch == None: return False
    return warns

async def globalrole(user_id: int, level: int):
    """
    Выдаёт или обновляет глобальную роль пользователя в таблице global_managers.
    
    level (глобальные роли):
        0 - удаление роли
        8 - Заместитель Руководителя
        9 - Основной Заместитель Руководителя
        10 - Специальный Руководитель
        11 - Разработчик
    """
    fetch = await db.fetchone('SELECT user_id FROM global_managers WHERE user_id = $1', user_id,)

    if fetch is None:
        if level != 0:
            await db.execute("INSERT INTO global_managers (user_id, level) VALUES ($1, $2)", (user_id, level))
    else:
        if level == 0:
            await db.execute("DELETE FROM global_managers WHERE user_id = $1", (user_id,))
        else:
            await db.execute("UPDATE global_managers SET level = $1 WHERE user_id = $2", (level, user_id))

    pass
    print(f"Глобальная роль пользователя {user_id} изменена на уровень {level}")

async def staff(chat_id=int, owner_id=int):
    fetch = await db.fetchall(f"SELECT * FROM permissions_{chat_id}")

    moders = []
    stmoders = []
    admins = []
    stadmins = []
    zamspec = []
    spec = []
    owner = []
    if fetch == None: return False
    for i in fetch:
        level = i[1]
        user_display = await get_user_or_group_mention(i[0], chat_id)

        # Локальные роли чата (1-7)
        if level == 1:
            moders.append(user_display)
        elif level == 2:
            stmoders.append(user_display)
        elif level == 3:
            admins.append(user_display)
        elif level == 4:
            stadmins.append(user_display)
        elif level == 5:
            zamspec.append(user_display)
        elif level == 6:
            spec.append(user_display)
        elif level == 7:
            owner.append(user_display)
        # Глобальные роли (8-11) НЕ добавляем в локальный staff
    return {
        'moders': moders,
        'stmoders': stmoders,
        'admins': admins,
        'stadmins': stadmins,
        'zamspec': zamspec,
        'spec': spec,
        'owner': owner,
    }

async def addruk(user_id=int):
    await db.execute(f"INSERT INTO ruk VALUES ($1)", (user_id,))
    pass

async def delruk(user_id=int):
    await db.execute(f"DELETE FROM ruk WHERE user_id = {user_id}")
    pass

async def ruklist():
    fetch = await db.fetchall(f"SELECT * FROM ruk")

    if fetch:
        ids_list = [item[0] for item in fetch]
        idstuple = tuple(ids_list)
        return ids_list

async def check_quit(chat_id=int):
    fetch = await db.fetchone(f"SELECT silence FROM chats WHERE chat_id = {chat_id}")

    if fetch == None:
        return False
    else:
        return await get_logic(fetch[0])

async def get_banwords(chat_id=int):
    banwords = []
    fetch = await db.fetchall(f"SELECT * FROM banwords_{chat_id}")
    for i in fetch:
        banwords.append(i[0])
    return banwords

async def clear(cmid=int, chat_id=int, group_id=int, peer_id=int):
    try:
        await bot.api.messages.delete(group_id=group_id, peer_id=peer_id, delete_for_all=True, cmids=cmid)
    except:
        pass

async def new_message(user_id=int, message_id=int, cmid=int, chat_id=int):
    cd = str(moscow_now()).split('.')
    date_string = cd[0]
    await db.execute(f"INSERT INTO messages_{chat_id} VALUES ($1, $2, $3, $4, $5)",
                (user_id, time.time(), date_string, message_id, cmid))
    pass

async def roleG(user_id=int, chat_id=int, role=int):
    fetch = await db.fetchone(f"SElECT user_id FROM permissions_{chat_id} WHERE user_id = {user_id}")

    if fetch == None:
        if role == 0:
            await db.execute(f"DELETE FROM permissions_{chat_id} WHERE user_id = {user_id}")
        else:
            await db.execute(f"INSERT INTO permissions_{chat_id} VALUES ($1, $2)", (user_id, role))
    else:
        if role == 0:
            await db.execute(f"DELETE FROM permissions_{chat_id} WHERE user_id = {user_id}")
        else:
            await db.execute(f"UPDATE permissions_{chat_id} SET level = $1 WHERE user_id = $2", (role, user_id))
    pass

    # Записываем дату назначения роли (только для ролей ≥ 1)
    if role >= 1:
        await set_role_appointment_date(user_id, chat_id, role)
    if role >= 8:
        await logsrole(user_id, role, chat_id)

async def set_role_appointment_date(user_id=int, chat_id=int, role_level=int):
    """Установить/обновить дату назначения роли"""
    try:
        # Проверяем, есть ли уже запись
        existing = await db.fetchone(f"SELECT * FROM role_appointments WHERE user_id = $1 AND chat_id = $2", (user_id, chat_id))

        current_time = moscow_now().strftime('%Y-%m-%d')

        if existing:
            # Обновляем существующую запись
            await db.execute("""
                UPDATE role_appointments 
                SET role_level = $1, appointment_date = $2
                WHERE user_id = $3 AND chat_id = $4
            """, (role_level, current_time, user_id, chat_id))
        else:
            # Создаем новую запись
            await db.execute("""
                INSERT INTO role_appointments (user_id, chat_id, role_level, appointment_date)
                VALUES (?, ?, ?, ?)
            """, (user_id, chat_id, role_level, current_time))

        pass
        return True
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            # Таблица не существует, создаем
            await create_role_appointments_table()
            # Пробуем снова
            return await set_role_appointment_date(user_id, chat_id, role_level)
        else:
            print(f"Ошибка при записи даты назначения: {e}")
            return False

async def create_role_appointments_table():
    """Создать таблицу для хранения дат назначения ролей"""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS role_appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id BIGINT NOT NULL,
            chat_id BIGINT NOT NULL,
            role_level INTEGER NOT NULL,
            appointment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, chat_id)
        )
    """)
    pass

async def logsrole(user=int, role=int, chat_id=int):
    cd = str(moscow_now()).split('.')
    date_string = cd[0]
    await db.execute(f"INSERT INTO logsrole VALUES ($1, $2, $3, $4)", (user, role, chat_id, date_string))
    pass

async def logsrolelist():
    fetch = await db.fetchall(f"SELECT * FROM logsrole")

    banlist = []
    for i in fetch:
        user_display = await get_user_or_group_mention(i[0])
        banlist.append(f"{user_display} | Выдан {i[1]} уровень прав | Дата: {i[3]} | {i[2]}")
    return banlist

async def ban(user_id: int, moder: int, chat_id: int, reason: str, duration_minutes: int = 0,
              duration_text: str = "навсегда"):
    """
    Забанить пользователя
    duration_minutes: время в минутах (0 - навсегда)
    duration_text: текстовое представление времени
    """
    cd = str(moscow_now()).split('.')
    date_string = cd[0]
    current_timestamp = time.time()

    # Рассчитываем время окончания бана
    if duration_minutes > 0:
        expire_time = current_timestamp + (duration_minutes * 60)
        if duration_text == "навсегда" or not duration_text:
            duration_text = format_duration_text(duration_minutes)
        print(
            f"DEBUG БАН: duration_minutes={duration_minutes}, duration_text={duration_text}, expire_time={expire_time}")
    else:
        expire_time = 0
        duration_text = "навсегда"
        print(f"DEBUG БАН: навсегда")

    table_name = f"bans_{chat_id}"

    # ПРОВЕРЯЕМ И ДОБАВЛЯЕМ КОЛОНКИ ПЕРЕД ВСТАВКОЙ
    columns = await db.fetchall(f"PRAGMA table_info({table_name})")

    column_names = [col[1] for col in columns]

    # Добавляем недостающие колонки
    if 'ban_time' not in column_names:
        print(f"Добавляем колонку ban_time в {table_name}")
        await db.execute(f"ALTER TABLE {table_name} ADD COLUMN ban_time INTEGER DEFAULT 0")
        pass

    if 'ban_expire' not in column_names:
        print(f"Добавляем колонку ban_expire в {table_name}")
        await db.execute(f"ALTER TABLE {table_name} ADD COLUMN ban_expire REAL DEFAULT 0")
        pass

    if 'ban_duration_text' not in column_names:
        print(f"Добавляем колонку ban_duration_text в {table_name}")
        await db.execute(f"ALTER TABLE {table_name} ADD COLUMN ban_duration_text TEXT DEFAULT 'навсегда'")
        pass

    # Удаляем старую запись если есть
    await db.execute(f"DELETE FROM {table_name} WHERE user_id = $1", (user_id,))

    # Вставляем новую запись - УБЕДИТЕСЬ, ЧТО ВСЕ 8 КОЛОНОК НА МЕСТЕ
    await db.execute(f"""
        INSERT INTO {table_name} 
        (user_id, moder, reason, date, date_string, ban_time, ban_expire, ban_duration_text) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, moder, reason, current_timestamp, date_string, duration_minutes, expire_time, duration_text))

    pass

    # ПРОВЕРЯЕМ, ЧТО СОХРАНИЛОСЬ
    check = await db.fetchone(f"SELECT ban_time, ban_expire, ban_duration_text FROM {table_name} WHERE user_id = $1", (user_id,))

    if check:
        print(f"DEBUG ПРОВЕРКА: ban_time={check[0]}, ban_expire={check[1]}, ban_duration_text={check[2]}")
        if check[0] != duration_minutes:
            print(f"ОШИБКА: duration_minutes не совпадает! Ожидалось {duration_minutes}, получено {check[0]}")
    else:
        print(f"DEBUG ОШИБКА: данные не сохранились!")

async def is_user_banned(user_id: int, chat_id: int) -> tuple:
    """Проверить, забанен ли пользователь, и не истёк ли бан"""
    try:
        table_name = f"bans_{chat_id}"

        # Проверяем, существует ли таблица
        exists = await db.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
            (table_name,)
        )
        if not exists:

            return (False, None)

        ban_data = await db.fetchone(f"SELECT * FROM {table_name} WHERE user_id = $1", (user_id,))

        if not ban_data:
            return (False, None)

        columns_count = len(ban_data)
        print(f"DEBUG is_user_banned: columns_count={columns_count}")

        # Структура таблицы:
        # 0: user_id, 1: moder, 2: reason, 3: date, 4: date_string, 5: ban_time, 6: ban_expire, 7: ban_duration_text
        if columns_count >= 8:
            ban_time_minutes = ban_data[5] if ban_data[5] else 0  # Индекс 5 - ban_time (минуты)
            ban_expire = ban_data[6] if ban_data[6] else 0  # Индекс 6 - ban_expire (timestamp)
            duration_text = ban_data[7] if ban_data[7] else "навсегда"

            print(
                f"DEBUG is_user_banned: ban_time={ban_time_minutes}, ban_expire={ban_expire}, current_time={time.time()}")

            # Если бан временный и срок истек
            if ban_time_minutes > 0 and ban_expire > 0 and time.time() > ban_expire:
                print(f"Бан истек, удаляем")
                await unban(user_id, chat_id, auto=True)
                return (False, None)

            return (True, {
                'moder': ban_data[1],
                'reason': ban_data[2],
                'date': ban_data[3],
                'date_string': ban_data[4],
                'ban_time': ban_time_minutes,
                'ban_expire': ban_expire,
                'duration_text': duration_text
            })
        else:
            # Старая структура (6 колонок)
            return (True, {
                'moder': ban_data[1],
                'reason': ban_data[2],
                'date': ban_data[3],
                'date_string': ban_data[4],
                'ban_time': 0,
                'ban_expire': 0,
                'duration_text': "навсегда"
            })
    except Exception as e:
        print(f"Ошибка в is_user_banned: {e}")
        import traceback
        traceback.print_exc()
        return (False, None)

async def cleanup_expired_bans_on_start():
    """При запуске бота проверяет и снимает все истекшие баны"""
    print("🔄 Проверка истекших банов при запуске...")

    tables = await db.fetchall("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'bans_%'")

    current_time = time.time()
    removed_count = 0

    for table in tables:
        table_name = table[0]

        if table_name == 'banschats':
            continue

        try:
            chat_id = int(table_name.replace('bans_', ''))
        except ValueError:
            continue

        # Проверяем наличие колонки ban_expire
        columns = await db.fetchall(f"PRAGMA table_info({table_name})")

        column_names = [col[1] for col in columns]

        if 'ban_expire' in column_names:
            expired_bans = await db.fetchall(f"SELECT user_id, ban_expire FROM {table_name} WHERE ban_expire > 0 AND ban_expire <= $1", (current_time,))

            for expired in expired_bans:
                user_id = expired[0]
                await unban(user_id, chat_id, auto=True)
                removed_count += 1
                print(f"Снят истекший бан у пользователя {user_id} в чате {chat_id}")

    print(f"✅ Проверка завершена. Снято {removed_count} истекших банов.")

async def checkban(user_id: int, chat_id: int):
    """Получить информацию о бане пользователя в чате"""
    try:
        table_name = f"bans_{chat_id}"

        # Проверяем, существует ли таблица
        exists = await db.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
            (table_name,)
        )
        if not exists:

            return False

        fetch = await db.fetchone(f"SELECT * FROM {table_name} WHERE user_id = $1", (user_id,))

        if fetch is None:
            return False

        # Структура таблицы:
        # 0: user_id, 1: moder, 2: reason, 3: date, 4: date_string, 5: ban_time, 6: ban_expire, 7: ban_duration_text
        columns_count = len(fetch)
        print(f"DEBUG checkban: columns_count={columns_count}, fetch={fetch}")

        # Если есть колонки времени (8 колонок)
        if columns_count >= 8:
            ban_time_minutes = fetch[5] if fetch[5] else 0  # Индекс 5 - ban_time
            ban_expire = fetch[6] if fetch[6] else 0  # Индекс 6 - ban_expire
            duration_text = fetch[7] if fetch[7] else "навсегда"  # Индекс 7 - ban_duration_text

            print(
                f"DEBUG checkban: ban_time={ban_time_minutes}, ban_expire={ban_expire}, duration_text={duration_text}")

            # Проверяем, не истек ли бан (ban_time_minutes - это минуты, а не timestamp!)
            if ban_time_minutes > 0 and ban_expire > 0 and time.time() > ban_expire:
                # Бан истек - удаляем
                await unban(user_id, chat_id, auto=True)
                return False

            return {
                'moder': fetch[1],
                'reason': fetch[2],
                'date': fetch[3],
                'date_string': fetch[4],
                'ban_time': ban_time_minutes,
                'ban_expire': ban_expire,
                'duration_text': duration_text
            }
        else:
            # Старая структура (6 колонок)
            return {
                'moder': fetch[1],
                'reason': fetch[2],
                'date': fetch[3],
                'date_string': fetch[4],
                'ban_time': 0,
                'ban_expire': 0,
                'duration_text': "навсегда"
            }
    except Exception as e:
        print(f"Ошибка в checkban: {e}")
        import traceback
        traceback.print_exc()
        return False

async def unban(user_id: int, chat_id: int, admin_id: int = None, reason: str = None, auto: bool = False):
    """Снять бан (удалить из БД)"""
    try:
        await db.execute(f"DELETE FROM bans_{chat_id} WHERE user_id = $1", (user_id,))
        pass
        if auto:
            print(f"Автоматически снят бан у пользователя {user_id} в чате {chat_id}")
    except Exception as e:
        print(f"Ошибка при снятии бана: {e}")

async def gban(user_id: int, moderator: int, chat_id: int, reason: str):
    """Глобальный бан пользователя"""
    try:
        fetch = await db.fetchone('SELECT user_id FROM gbans WHERE user_id = $1', user_id,)
        cd = str(moscow_now()).split('.')
        date_string = cd[0]

        if fetch is None:
            await db.execute("INSERT INTO gbans (user_id, moder, reason, date, date_string) VALUES ($1, $2, $3, $4, $5)",
                        (user_id, moderator, reason, time.time(), date_string))
        else:
            await db.execute("UPDATE gbans SET moder = $1, reason = $2, date = $3, date_string = $4 WHERE user_id = $5",
                        (moderator, reason, time.time(), date_string, user_id))
        pass
    except Exception as e:
        print(f"Ошибка в gban: {e}")

async def ungban(user_id: int, admin_id: int = None, reason: str = None):
    """Снять глобальный бан"""
    try:
        await db.execute("DELETE FROM gbans WHERE user_id = $1", (user_id,))
        pass
    except Exception as e:
        print(f"Ошибка в ungban: {e}")

async def banlist(chat_id: int) -> list:
    """Получить список банов в чате"""
    try:
        # Проверяем, существует ли таблица для этого чата
        table_name = f"bans_{chat_id}"
        exists = await db.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
            (table_name,)
        )
        if not exists:

            return ["📭 В этой беседе нет заблокированных пользователей!"]

        fetch = await db.fetchall(f"SELECT * FROM bans_{chat_id} ORDER BY date DESC")

        if not fetch:
            return ["📭 В этой беседе нет заблокированных пользователей!"]

        banlist = []
        for i, row in enumerate(fetch, 1):
            # Базовая информация
            user_id = row[0]
            moder_id = row[1]
            reason = row[2]
            date_string = row[4]

            user_display = await get_user_or_group_mention(user_id)
            moder_display = await get_user_or_group_mention(moder_id)

            # Получаем информацию о времени бана (индексы: 5=ban_time, 6=ban_expire, 7=ban_duration_text)
            if len(row) >= 8:
                ban_time_minutes = row[5] if row[5] else 0
                ban_expire = row[6] if row[6] else 0
                duration_text = row[7] if row[7] else "навсегда"

                # Если бан временный и не истек, показываем время до снятия
                if ban_time_minutes > 0 and ban_expire > 0:
                    expire_time = moscow_fromtimestamp(ban_expire)
                    if expire_time > moscow_now():
                        time_display = f"{duration_text} (до {expire_time.strftime('%d.%m.%Y %H:%M')})"
                    else:
                        time_display = f"{duration_text} (истёк)"
                else:
                    time_display = duration_text
            else:
                time_display = "навсегда"

            banlist.append(f"{i}) {user_display} | {reason} | {moder_display} | {date_string} | ⏰ {time_display}")

        return banlist
    except Exception as e:
        print(f"Ошибка в banlist: {e}")
        return [f"❌ Ошибка при получении списка банов: {e}"]

async def gbanlist() -> list:
    """Получить список глобальных банов"""
    try:
        fetch = await db.fetchall("SELECT * FROM gbans ORDER BY date DESC")

        if not fetch:
            return ["🌐 Нет глобально заблокированных пользователей!"]

        all_ids = set()
        for row in fetch:
            all_ids.add(row[0])
            all_ids.add(row[1])

        user_ids = [i for i in all_ids if i > 0]
        group_ids = [abs(i) for i in all_ids if i < 0]

        names = {}
        if user_ids:
            for chunk_start in range(0, len(user_ids), 500):
                chunk = user_ids[chunk_start:chunk_start + 500]
                try:
                    info = await bot.api.users.get(user_id=chunk)
                    for u in info:
                        names[u.id] = f"{u.first_name} {u.last_name}"
                except:
                    pass

        if group_ids:
            for gid in group_ids:
                try:
                    gname = await get_group_name(-gid)
                    names[-gid] = gname
                except:
                    pass

        gbanlist_result = []
        for i, row in enumerate(fetch, 1):
            uid, moder_id, reason, _, date_string = row

            if uid > 0:
                user_display = f"[id{uid}|{names.get(uid, f'ID{uid}')}]"
            else:
                user_display = f"[club{abs(uid)}|{names.get(uid, f'ID{abs(uid)}')}]"

            if moder_id > 0:
                moder_display = f"[id{moder_id}|{names.get(moder_id, f'ID{moder_id}')}]"
            else:
                moder_display = f"[club{abs(moder_id)}|{names.get(moder_id, f'ID{abs(moder_id)}')}]"

            gbanlist_result.append(f"{i}) {user_display} | Забанил: {moder_display} | Причина: {reason} | Дата: {date_string}")

        return gbanlist_result
    except Exception as e:
        print(f"Ошибка в gbanlist: {e}")
        return [f"❌ Ошибка при получении списка глобальных банов: {e}"]

async def gcheckban(user_id: int, chat_id: int = None) -> dict:
    """Проверить глобальный бан пользователя"""
    try:
        fetch = await db.fetchone('SELECT * FROM gbans WHERE user_id = $1', user_id,)
        if fetch is None:
            return False
        else:
            # Структура: (user_id, moder, reason, date, date_string)
            return {
                'moder': fetch[1],
                'reason': fetch[2],
                'date': fetch[3],
                'date_string': fetch[4]
            }
    except Exception as e:
        print(f"Ошибка в gcheckban: {e}")
        return False

async def cleanup_bans():
    """Периодически проверяет и снимает истекшие баны"""
    while True:
        try:
            current_time = time.time()

            # Получаем все таблицы банов
            tables = await db.fetchall("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'bans_%'")

            for table in tables:
                table_name = table[0]

                # Пропускаем таблицу banschats (она не содержит баны пользователей)
                if table_name == 'banschats':
                    continue

                # Извлекаем chat_id из названия таблицы (bans_123 -> 123)
                try:
                    chat_id = int(table_name.replace('bans_', ''))
                except ValueError:
                    print(f"Пропущена таблица: {table_name}")
                    continue

                # Проверяем, есть ли колонка ban_expire
                columns = await db.fetchall(f"PRAGMA table_info({table_name})")

                column_names = [col[1] for col in columns]

                if 'ban_expire' in column_names:
                    # Находим истекшие баны
                    expired_bans = await db.fetchall(
                        f"SELECT user_id, ban_expire FROM {table_name} WHERE ban_expire > 0 AND ban_expire <= $1",
                        (current_time,))

                    for expired in expired_bans:
                        user_id = expired[0]
                        await unban(user_id, chat_id, auto=True)
                        print(f"Автоматически снят бан у пользователя {user_id} в чате {chat_id}")

            # Проверяем каждые 60 секунд
            await asyncio.sleep(60)

        except Exception as e:
            print(f"Ошибка в cleanup_bans: {e}")
            await asyncio.sleep(60)

def parse_duration(duration_str: str) -> tuple:
    """
    Парсит строку времени и возвращает (минуты, текст)
    Примеры: 1ч, 2ч, 30м, 1д, 1мес, 1г, 5мин, 1час
    """
    duration_str = duration_str.lower().strip()
    print(f"DEBUG parse_duration: входная строка = '{duration_str}'")

    # Проверяем специальные слова
    if duration_str in ['навсегда', 'бессрочно', 'forever', 'perm', '∞']:
        print(f"DEBUG parse_duration: навсегда")
        return (0, "навсегда")

    # Сопоставление единиц измерения с минутами
    units = {
        'м': 1, 'мин': 1, 'минута': 1, 'минуты': 1, 'минут': 1,
        'ч': 60, 'час': 60, 'часа': 60, 'часов': 60, 'hour': 60, 'hours': 60,
        'д': 1440, 'день': 1440, 'дня': 1440, 'дней': 1440, 'day': 1440, 'days': 1440,
        'нед': 10080, 'неделя': 10080, 'недели': 10080, 'недель': 10080, 'week': 10080, 'weeks': 10080,
        'мес': 43200, 'месяц': 43200, 'месяца': 43200, 'месяцев': 43200, 'month': 43200, 'months': 43200,
        'г': 525600, 'год': 525600, 'года': 525600, 'лет': 525600, 'year': 525600, 'years': 525600
    }

    # Извлекаем число и единицу
    import re
    match = re.match(r'(\d+)\s*([а-яa-z]+)', duration_str)

    if not match:
        print(f"DEBUG parse_duration: не удалось распарсить, возвращаем навсегда")
        return (0, "навсегда")

    number = int(match.group(1))
    unit = match.group(2)
    print(f"DEBUG parse_duration: number={number}, unit={unit}")

    # Находим соответствующую единицу
    for key, minutes in units.items():
        if unit.startswith(key) or key.startswith(unit):
            total_minutes = number * minutes
            text = format_duration_text(total_minutes)
            print(f"DEBUG parse_duration: total_minutes={total_minutes}, text={text}")
            return (total_minutes, text)

    print(f"DEBUG parse_duration: единица не найдена, возвращаем навсегда")
    return (0, "навсегда")

async def quiet(chat_id=int):
    result = await db.fetchone(f"SELECT silence FROM chats WHERE chat_id = {chat_id}")

    if not await get_logic(result):
        await db.execute(f"UPDATE chats SET silence = 1 WHERE chat_id = {chat_id}")
        pass
        return True
    else:
        await db.execute(f"UPDATE chats SET silence = 0 WHERE chat_id = {chat_id}")
        pass
        return False

async def get_gpull_chats(chat_id=int):
    fetch = await db.fetchone(f"SELECT owner_id, in_gpull FROM chats WHERE chat_id = {chat_id}")

    if fetch == None: return False
    if not await get_logic(fetch[1]): return False
    fetch2 = await db.fetchall(f"SELECT chat_id FROM chats WHERE owner_id = $1 AND in_gpull = $2", (fetch[0], fetch[1]))
    result = []
    for i in fetch2:
        result.append(i[0])
    return result

async def get_chat_id():
    fetch = await db.fetchone(f"SELECT MAX(chat_id) FROM chats")

    return fetch[0]

async def gpull_id():
    fetch = await db.fetchall(f"SELECT chat_id FROM chats")

    return fetch

async def check(self, message: Message) -> bool:
    msg_id = f"{message.from_id}_{message.date}"
    if msg_id in self.processed_messages:
        return False
    has_link = bool(re.search(r'https?://\S+', message.text or ''))
    if has_link and message.attachments:
        self.processed_messages.add(msg_id)
        if len(self.processed_messages) > 100:
            self.processed_messages.clear()
    return True

async def get_gpull_id(chat_id=int):
    fetch = await db.fetchone(f"SELECT in_gpull FROM chats WHERE chat_id = {chat_id}")

    return fetch[0]

async def get_pull_chats(chat_id=int):
    fetch = await db.fetchone(f"SELECT owner_id, in_pull FROM chats WHERE chat_id = {chat_id}")

    if fetch == None: return False
    if not await get_logic(fetch[1]): return False
    fetch2 = await db.fetchall(f"SELECT chat_id FROM chats WHERE owner_id = $1 AND in_pull = $2", (fetch[0], fetch[1]))
    result = []
    for i in fetch2:
        result.append(i[0])
    return result

async def get_pull_id(chat_id=int):
    fetch = await db.fetchone(f"SELECT in_pull FROM chats WHERE chat_id = {chat_id}")

    return fetch[0]

async def rnickall(chat_id=int):
    await db.execute(f"DELETE FROM nicks_{chat_id}")
    pass

async def banwords(slovo=str, delete=bool, chat_id=int):
    if delete:
        await db.execute(f"DELETE FROM banwords_{chat_id} WHERE banword = $1", (slovo,))
        pass
    else:
        fetch = await db.fetchone(f"SELECT * FROM banwords_{chat_id} WHERE banword = $1", (slovo,))

        if fetch == None:
            await db.execute(f"INSERT INTO banwords_{chat_id} VALUES ($1)", (slovo,))
            pass

async def get_invite_kick(chat_id=int):
    fetch = await db.fetchone(f"SELECT invite_kick FROM chats WHERE chat_id = {chat_id}")

    return await get_logic(fetch[0])

async def get_leave_kick(chat_id=int):
    fetch = await db.fetchone(f"SELECT leave_kick FROM chats WHERE chat_id = {chat_id}")

    return await get_logic(fetch[0])

async def set_filter(chat_id=int, value=int):
    await db.execute("UPDATE chats SET filter = $1 WHERE chat_id = $2", (value, chat_id))
    pass

async def get_filter(chat_id=int):
    fetch = await db.fetchone(f"SELECT filter FROM chats WHERE chat_id = {chat_id}")

    return await get_logic(fetch[0])

async def get_antiflood(chat_id=int):
    fetch = await db.fetchone(f"SELECT antiflood FROM chats WHERE chat_id = {chat_id}")

    return await get_logic(fetch[0])

async def set_antiflood(chat_id=int, value=int):
    await db.execute("UPDATE chats SET antiflood = $1 WHERE chat_id = $2", (value, chat_id))
    pass

async def get_spam(user_id=int, chat_id=int):
    fetch = await db.fetchall(
        f"SELECT date_string FROM messages_{chat_id}  WHERE user_id = {user_id} ORDER BY date_string DESC LIMIT 5")
    list_messages = []
    for i in fetch:
        list_messages.append(datetime.fromisoformat(i[0]))
    try:
        list_messages = list_messages[:5]
    except:
        return False
    if len(list_messages) > 4:
        if list_messages[0] - list_messages[4] < timedelta(seconds=5):
            return True
    else:
        return False

async def set_welcome(chat_id=int, text=int):
    await db.execute(f"UPDATE chats SET welcome_text = $1 WHERE chat_id = $2", (text, chat_id))
    pass

async def get_welcome(chat_id=int):
    fetch = await db.fetchone('SELECT welcome_text FROM chats WHERE chat_id = $1', chat_id,)
    if str(fetch[0]).lower().strip() == "off":
        return False
    else:
        return str(fetch[0])

async def set_rules(chat_id=int, text=int):
    fetch = await db.fetchone('SELECT text FROM rules WHERE chat_id = $1', chat_id,)
    if fetch:
        await db.execute("UPDATE rules SET text = $1 WHERE chat_id = $2", (text, chat_id))
        pass
    else:
        await db.execute(f"INSERT INTO rules(chat_id, text) VALUES ($1, $2)", (chat_id, text))
        pass

async def get_rules(chat_id=int):
    fetch = await db.fetchone('SELECT text FROM rules WHERE chat_id = $1', chat_id,)
    if fetch:
        if str(fetch[0]).lower().strip() == "off":
            return False
        else:
            return fetch

async def set_info(chat_id=int, text=int):
    fetch = await db.fetchone('SELECT text FROM info WHERE chat_id = $1', chat_id,)
    if fetch:
        await db.execute("UPDATE info SET text = $1 WHERE chat_id = $2", (text, chat_id))
        pass
    else:
        await db.execute(f"INSERT INTO info(chat_id, text) VALUES ($1, $2)", (chat_id, text))
        pass

async def get_info(chat_id=int):
    fetch = await db.fetchone('SELECT text FROM info WHERE chat_id = $1', chat_id,)
    if fetch:
        if str(fetch[0]).lower().strip() == "off":
            return False
        else:
            return fetch

async def invite_kick(chat_id=int, change=None):
    fetch = await db.fetchone('SELECT invite_kick FROM chats WHERE chat_id = $1', chat_id,)
    if not change == None:
        if await get_logic(fetch[0]):
            await db.execute("UPDATE chats SET invite_kick = 0 WHERE chat_id = $1", (chat_id,))
            pass
            return False
        else:
            await db.execute("UPDATE chats SET invite_kick = 1 WHERE chat_id = $1", (chat_id,))
            pass
            return True
    else:
        return await get_logic(fetch[0])

async def get_logic(number=int):
    if number < 1:
        return False
    else:
        return True

async def leave_kick(chat_id=int, change=None):
    fetch = await db.fetchone('SELECT leave_kick FROM chats WHERE chat_id = $1', chat_id,)
    if fetch == None: return False
    if change == None: return await get_logic(fetch[0])
    if await get_logic(fetch[0]):
        await db.execute("UPDATE chats SET leave_kick = 0 WHERE chat_id = $1", (chat_id,))
        pass
        return False
    else:
        await db.execute("UPDATE chats SET leave_kick = 1 WHERE chat_id = $1", (chat_id,))
        pass
        return True

async def message_stats(user_id=int, chat_id=int):
    try:
        fetch_all = await db.fetchall(f"SELECT date_string FROM messages_{chat_id} WHERE user_id = $1", (user_id,))

        fetch_last = await db.fetchone(f"SELECT date_string FROM messages_{chat_id} WHERE user_id = $1 ORDER BY date_string DESC LIMIT 1", (user_id,))

        last = fetch_last[0]
        return {
            'count': len(fetch_all),
            'last': last
        }
    except:
        return {
            'count': 0,
            'last': 0
        }

async def get_chat_title(bot: Bot, peer_id: int) -> str or None:
    try:
        conversations = await bot.api.messages.get_conversations_by_id(peer_ids=[peer_id], extended=True)
        if conversations.count > 0:
            conversation = conversations.items[0]
            chat_title = conversation.chat_settings.title
            return chat_title
        else:
            return None
    except Exception as e:
        print(f"Ошибка при получении названия беседы: {e}")
        return None

async def set_gpull(chat_id=int, value=int, glob=str):
    await db.execute(f"UPDATE chats SET in_gpull = $1 WHERE chat_id = $2", (value, chat_id))
    pass

async def set_pull(chat_id=int, value=int):
    await db.execute(f"UPDATE chats SET in_pull = $1 WHERE chat_id = $2", (value, chat_id))
    pass

async def get_user_nam(user_id=int, chat_id=int):
    fetch = await db.fetchone(f"SELECT nick FROM nicks_{chat_id} WHERE user_id = {user_id}")

    if not fetch == None:
        return fetch[0]

async def get_all_peerids():
    fetch = await db.fetchall("SELECT peer_id FROM chats")

    peer_ids = []
    for i in fetch:
        peer_ids.append(i[0])
    return peer_ids

async def add_punishment(chat_id=int, user_id=int):
    cd = str(moscow_now()).split('.')
    date_string = cd[0]
    await db.execute(f"INSERT INTO punishments_{chat_id} VALUES ($1, $2)", (user_id, date_string))
    pass

async def remove_punishment(chat_id=int, user_id=int):
    try:
        await db.execute(f"DELETE FROM punishments_{chat_id} WHERE user_id = $1", (user_id,))
        pass
    except Exception as e:
        print('error {e}')

async def get_sliv(user_id=int, chat_id=int):
    fetch = await db.fetchall(f"SELECT date FROM punishments_{chat_id}  WHERE user_id = {user_id} ORDER BY date DESC LIMIT 3")

    list_messages = []
    for i in fetch:
        list_messages.append(datetime.fromisoformat(i[0]))
    try:
        list_messages = list_messages[:3]
    except:
        return False
    if list_messages[0] - list_messages[2] < timedelta(seconds=6):
        return True
    else:
        return False

async def staff_zov(chat_id=int):
    fetch = await db.fetchall(f"SElECT user_id FROM permissions_{chat_id}")

    staff_zov_str = []
    for i in fetch:
        staff_zov_str.append(f"{await get_user_or_group_mention(i[0])} (⚜️)")
    return ''.join(staff_zov_str)

async def delete_message(group_id=int, peer_id=int, cmid=int):
    try:
        await bot.api.messages.delete(group_id=group_id, peer_id=peer_id, delete_for_all=True, cmids=cmid)
    except:
        pass

async def fix_old_bans():
    """Обновляет старые записи банов, добавляя информацию о времени"""
    try:
        tables = await db.fetchall("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'bans_%'")

        for table in tables:
            table_name = table[0]
            if table_name == 'banschats':
                continue

            # Проверяем структуру
            columns = await db.fetchall(f"PRAGMA table_info({table_name})")

            column_names = [col[1] for col in columns]

            # Если есть колонки времени, обновляем старые записи
            if 'ban_time' in column_names and 'ban_expire' in column_names:
                # Находим записи где ban_time = 0 но есть date
                old_bans = await db.fetchall(
                    f"SELECT rowid, user_id, date, date_string FROM {table_name} WHERE ban_time = 0 OR ban_time IS NULL")

                for old in old_bans:
                    rowid = old[0]
                    user_id = old[1]
                    ban_date = old[2]
                    date_string = old[3]

                    # Оставляем как навсегда (это старые баны)
                    await db.execute(f"""
                        UPDATE {table_name} 
                        SET ban_time = 0, ban_expire = 0, ban_duration_text = 'навсегда'
                        WHERE rowid = $1
                    """, (rowid,))

                    print(f"Обновлена запись для пользователя {user_id} в {table_name}")

                pass
                print(f"✅ Обновлены старые записи в {table_name}")

        print("✅ Все старые записи банов обновлены!")
    except Exception as e:
        print(f"Ошибка при обновлении старых банов: {e}")

async def get_role_appointment_date(user_id=int, chat_id=int):
    """Получить дату назначения на роль модератора"""
    try:
        fetch = await db.fetchone(f"SELECT appointment_date FROM role_appointments WHERE user_id = $1 AND chat_id = $2", (user_id, chat_id))

        if fetch:
            return fetch[0]
        else:
            return None
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            # Таблица не существует, создадим её
            await create_role_appointments_table()
            return None
        else:
            print(f"Ошибка при получении даты назначения: {e}")
            return None

async def set_owner(user=int, chat_id=int):
    await db.execute("UPDATE chats SET owner_id = $1 WHERE chat_id = $2", (user, chat_id))
    pass

@bot.on.chat_message(rules.ChatActionRule("chat_kick_user"))
async def user_leave(message: Message) -> None:
    user_id = message.from_id
    chat_id = message.chat_id
    if not await check_chat(chat_id): return True
    if not message.action.member_id == message.from_id: return True
    if await leave_kick(chat_id):
        try:
            await bot.api.messages.remove_chat_user(chat_id, user_id)
        except:
            pass
        user_display = await get_user_or_group_mention(user_id)
        await message.answer(f"{user_display} вышел(-а) и был исключен из беседы", disable_mentions=1)

@bot.on.chat_message(rules.ChatActionRule("chat_invite_user_by_link"))
async def user_joined_link(message: Message) -> None:
    user_id = message.from_id
    chat_id = message.chat_id
    if not await check_chat(chat_id): return True
    ggetban = await gcheckban(user_id, chat_id)
    if ggetban:
        try:
            await bot.api.messages.remove_chat_user(chat_id, user_id)
            moder_display = await get_user_or_group_mention(ggetban['moder'])
            await message.answer(
                f"У Пользователя имеется глобальная блокировка : \n\nКем была выдана блокировка : {moder_display} (Командoй бота) \nПричина : {ggetban['reason']} \nДата выдачи : {ggetban['date']}",
                disable_mentions=1)
            return True
        except:
            pass
    checkban_str = await checkban(user_id, chat_id)
    if checkban_str:
        try:
            await bot.api.messages.remove_chat_user(chat_id, user_id)
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("Снять бан", {"command": "unban", "user": user_id, "chatId": chat_id}),
                     color=KeyboardButtonColor.POSITIVE)
            )
            moder_display = await get_user_or_group_mention(checkban_str['moder'])
            user_display = await get_user_or_group_mention(user_id)
            await message.answer(
                f"{user_display} заблокирован(-а) в этой беседе!\n\nИнформация о блокировке:\n{moder_display} | {checkban_str['reason']} | {checkban_str['date']}",
                disable_mentions=1, keyboard=keyboard)
            return True
        except:
            pass
        info = await bot.api.users.get(user_id)
    welcome = await get_welcome(chat_id)
    if welcome:
        info = await bot.api.users.get(user_id)
        user_display = await get_user_or_group_mention(user_id)
        welcome = welcome.replace('%u', user_display)
        welcome = welcome.replace('%n', user_display)
        welcome = welcome.replace('%i', user_display)
        uinfo = await bot.api.users.get(user_id)
        welcome = welcome.replace('%p', user_display)
        await message.answer(welcome)

@bot.on.chat_message(rules.ChatActionRule("chat_invite_user"))
async def user_joined(message: Message) -> None:
    invited_user = message.action.member_id
    user_id = message.from_id
    chat_id = message.chat_id
    if invited_user == -232598001:
        try:
            await message.answer(
                "Бот успешно добавлен в беседу!\nДля активации напишите /start (нужна звезда у бота)!",
                attachment=[photo1])
        except Exception as e:
            print('')
    elif user_id != -232598001 or -234187998:
        ggetban = await gcheckban(invited_user, chat_id)
        if ggetban:
            try:
                await bot.api.messages.remove_chat_user(chat_id, invited_user)
                moder_display = await get_user_or_group_mention(ggetban['moder'])
                await message.answer(
                    f"У Пользователя имеется глобальная блокировка :\n\nКем была выдана блокировка : {moder_display} (Командoй бота) \nПричина : {ggetban['reason']} \nДата выдачи : {ggetban['date']}",
                    disable_mentions=1)
                return True
            except:
                pass
        checkban_str = await checkban(invited_user, chat_id)
        if checkban_str:
            try:
                await bot.api.messages.remove_chat_user(chat_id, invited_user)
                keyboard = (
                    Keyboard(inline=True)
                    .add(Callback("Снять бан", {"command": "unban", "user": invited_user, "chatId": chat_id}),
                         color=KeyboardButtonColor.POSITIVE)
                )
                user_display = await get_user_or_group_mention(invited_user)
                moder_display = await get_user_or_group_mention(checkban_str['moder'])
                await message.answer(
                    f"{user_display} заблокирован(-а) в этой беседе!\n\nИнформация о блокировке:\n{moder_display} | {checkban_str['reason']} | {checkban_str['date']}",
                    disable_mentions=1, keyboard=keyboard)
                return True
            except:
                pass
            info = await bot.api.users.get(invited_user)
        print('1')
        if await get_role_cached(user_id, chat_id) < 1 and await invite_kick(chat_id):
            try:
                await bot.api.messages.remove_chat_user(chat_id, invited_user)
            except:
                pass
            return True
        welcome = await get_welcome(chat_id)
        if welcome:
            info = await bot.api.users.get(invited_user)
            invited_display = await get_user_or_group_mention(invited_user)
            user_display = await get_user_or_group_mention(user_id)
            welcome = welcome.replace('%u', invited_display)
            welcome = welcome.replace('%n', invited_display)
            welcome = welcome.replace('%i', user_display)
            welcome = welcome.replace('%p', user_display)
            await message.answer(welcome)
    else:
        ggetban = await gcheckban(invited_user, chat_id)
        if ggetban:
            try:
                await bot.api.messages.remove_chat_user(chat_id, invited_user)
                moder_display = await get_user_or_group_mention(ggetban['moder'])
                await message.answer(
                    f"Имеется глобальная блокировка : \n\nКем была выдана блокировка : {moder_display} (Командoй бота) \nПричина : {ggetban['reason']} \nДата выдачи : {ggetban['date']}",
                    disable_mentions=1)
                return True
            except:
                pass
        checkban_str = await checkban(invited_user, chat_id)
        if checkban_str:
            try:
                await bot.api.messages.remove_chat_user(chat_id, invited_user)
            except:
                pass
            info = await bot.api.users.get(invited_user)
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("Снять бан", {"command": "unban", "user": invited_user, "chatId": chat_id}),
                     color=KeyboardButtonColor.POSITIVE)
            )
            user_display = await get_user_or_group_mention(invited_user)
            moder_display = await get_user_or_group_mention(checkban_str['moder'])
            await message.answer(
                f"{user_display} заблокирован(-а) в этой беседе!\n\nИнформация о блокировке:\n{moder_display} | {checkban_str['reason']} | {checkban_str['date']}",
                disable_mentions=1, keyboard=keyboard
            )

async def get_moderator_stats(user_id=int, chat_id=int):
    """Получить статистику модератора в конкретном чате"""
    try:
        # Количество выданных мутов
        mutes_count = await db.fetchone(f"SELECT COUNT(*) FROM mutes_{chat_id} WHERE moder = $1", (user_id,))

        # Количество выданных варнов (из истории)
        warns_count = await db.fetchone(f"SELECT COUNT(*) FROM warnhistory_{chat_id} WHERE moder = $1", (user_id,))

        # Количество выданных банов
        bans_count = await db.fetchone(f"SELECT COUNT(*) FROM bans_{chat_id} WHERE moder = $1", (user_id,))

        # Дата назначения на роль
        appointment_date = await get_role_appointment_date(user_id, chat_id)
        if appointment_date:
            try:
                # Форматируем дату для красивого отображения
                dt = datetime.strptime(appointment_date, '%Y-%m-%d')
                appointment_str = dt.strftime('%d.%m.%Y')
            except:
                appointment_str = appointment_date
        else:
            appointment_str = "Данные не найдены в БД"

        # Получаем текущую роль пользователя
        current_role = await get_role_cached(user_id, chat_id)
        role_names = {
            1: "Модератор",
            2: "Старший модератор",
            3: "Администратор",
            4: "Старший администратор",
            5: "Заместитель специального администратора",
            6: "Специальный администратор",
            7: "Владелец беседы"
        }
        role_name = role_names.get(current_role, "Пользователь")

        return {
            'mutes': mutes_count,
            'warns': warns_count,
            'bans': bans_count,
            'appointment_date': appointment_str,
            'current_role': role_name,
            'role_level': current_role
        }
    except Exception as e:
        print(f"Ошибка при получении статистики модератора: {e}")
        return None

def save_data(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Загружаем конфиг
with open("config2.json", "r") as js:
    open_file = json.load(js)

@bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=GroupTypes.MessageEvent)
async def handle_all_callbacks(message):
    payload = message.object.payload
    command = str(payload.get("command") or payload.get("cmd") or "").lower()
    user_id = message.object.user_id
    chat_id = payload.get("chatId") or payload.get("chat")

    # АДМИНИСТРАТИВНЫЙ БОТ - игнорируем игровые команды от game.py
    game_commands = ["economyminus", "economyplus", "economyallminus", "economyallplus", "duel_join",
                     "accept_clan_battle", "reject_clan_battle", "help_main", "help_jobs", "help_business",
                     "help_houses", "help_cars", "help_property", "help_marriage", "help_mafia",
                     "help_rp", "help_clans", "mafia_"]
    if command in game_commands or command.startswith("economy") or command.startswith("help_") or \
       command.startswith("mafia_") or command.startswith("duel") or command.startswith("clan"):
        return  # Игнорируем игровые команды

    # --- ОСТАЛЬНЫЕ КОМАНДЫ (из вашего старого обработчика) ---
    # ВАЖНО: chat_id может быть в разных местах payload
    if not chat_id and message.object.peer_id > 2000000000:
        chat_id = message.object.peer_id - 2000000000

    # Команда modersallminus
    if command == "modersallminus":
        if await get_role_cached(user_id, chat_id) < 9:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return

        page = payload.get("page")

        if page < 2:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это первая страница!"})
            )
            return

        logs = await db.fetchall("SELECT * FROM logchats ORDER BY rowid DESC LIMIT 9999999999999")

        total = len(logs)
        per_page = MAX_LOGS
        max_page = (total + per_page - 1) // per_page

        async def get_moders_page(page: int):
            start = (page - 1) * per_page
            end = start + per_page
            selected = logs[start:end]
            formatted = []
            for idx, entry in enumerate(selected, start=start + 1):
                u_id, t_id, amount, log_text = entry

                u_display = await get_user_or_group_mention(u_id)

                if t_id:
                    t_display = await get_user_or_group_mention(t_id)
                else:
                    t_display = "None"

                a_display = f"{format_number(amount)}$" if amount else "None"
                l_display = log_text if log_text else "—"

                formatted.append(
                    f"{idx}. {u_display} | Кому: {t_display} | Роль: {a_display} | Лог: {l_display}")
            return formatted

        new_page = page - 1
        moders_page = await get_moders_page(new_page)
        moders_text = "\n\n".join(moders_page)

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("⏪", {"command": "modersAllMinus", "page": new_page}), color=KeyboardButtonColor.NEGATIVE)
            .add(Callback("⏩", {"command": "modersAllPlus", "page": new_page}), color=KeyboardButtonColor.POSITIVE)
        )

        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=f"Общие логи модерации [{new_page}/{max_page}]:\n\n{moders_text}",
            disable_mentions=1, random_id=0, keyboard=keyboard
        )
        return

    # Команда modersallplus
    if command == "modersallplus":
        if await get_role_cached(user_id, chat_id) < 9:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return

        page = payload.get("page")

        logs = await db.fetchall("SELECT * FROM logchats ORDER BY rowid DESC LIMIT 9999999999999")

        total = len(logs)
        per_page = MAX_LOGS
        max_page = (total + per_page - 1) // per_page

        async def get_moders_page(page: int):
            start = (page - 1) * per_page
            end = start + per_page
            selected = logs[start:end]
            formatted = []
            for idx, entry in enumerate(selected, start=start + 1):
                u_id, t_id, amount, log_text = entry

                u_display = await get_user_or_group_mention(u_id)

                if t_id:
                    t_display = await get_user_or_group_mention(t_id)
                else:
                    t_display = "None"

                a_display = f"{format_number(amount)}$" if amount else "None"
                l_display = log_text if log_text else "—"

                formatted.append(
                    f"{idx}. {u_display} | Кому: {t_display} | Роль: {a_display} | Лог: {l_display}")
            return formatted

        new_page = page + 1
        moders_page = await get_moders_page(new_page)
        if len(moders_page) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это последняя страница!"})
            )
            return

        moders_text = "\n\n".join(moders_page)

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("⏪", {"command": "modersAllMinus", "page": new_page}), color=KeyboardButtonColor.NEGATIVE)
            .add(Callback("⏩", {"command": "modersAllPlus", "page": new_page}), color=KeyboardButtonColor.POSITIVE)
        )

        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=f"Общие логи модерации [{new_page}/{max_page}]:\n\n{moders_text}",
            disable_mentions=1, random_id=0, keyboard=keyboard
        )
        return

    # Команда nicksminus
    if command == "nicksminus":
        if await get_role_cached(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return
        page = payload.get("page")
        if page < 2:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это первая страница!"})
            )
            return
        keyboard = (
            Keyboard(inline=True)
            .add(Callback("⏪", {"command": "nicksMinus", "page": page - 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.NEGATIVE)
            .add(Callback("Без ников", {"command": "nonicks", "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
            .add(Callback("⏩", {"command": "nicksPlus", "page": page - 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.POSITIVE)
        )
        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        nicks_str = '\n'.join(await nlist(chat_id, page - 1))
        await bot.api.messages.send(peer_id=2000000000 + chat_id,
                                    message=f"Пользователи с ником [{page - 1} страница]:\n{nicks_str}\n\nПользователи без ников: «/nonick»",
                                    disable_mentions=1, random_id=0, keyboard=keyboard)
        return

    # Команда nicksplus
    if command == "nicksplus":
        if await get_role_cached(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return
        page = payload.get("page")
        nicks = await nlist(chat_id, page + 1)
        if len(nicks) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это последняя страница!"})
            )
            return
        keyboard = (
            Keyboard(inline=True)
            .add(Callback("⏪", {"command": "nicksMinus", "page": page + 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.NEGATIVE)
            .add(Callback("Без ников", {"command": "nonicks", "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
            .add(Callback("⏩", {"command": "nicksPlus", "page": page + 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.POSITIVE)
        )
        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        nicks_str = '\n'.join(nicks)
        await bot.api.messages.send(peer_id=2000000000 + chat_id,
                                    message=f"Пользователи с ником [{page + 1} страница]:\n{nicks_str}\n\nПользователи без ников: «/nonick»",
                                    disable_mentions=1, random_id=0, keyboard=keyboard)
        return

    # Команда activeWarns (активные предупреждения)
    if command == "activewarns":
        if await get_role_cached(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return

        target_user = payload.get("user")
        if not target_user:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Ошибка: пользователь не найден!"})
            )
            return

        warns = await gwarn(target_user, chat_id)
        string_info = str
        if not warns:
            string_info = "Активных предупреждений нет!"
        else:
            moder_display = await get_user_or_group_mention(warns['moder'])
            string_info = f"{moder_display} | {warns['reason']} | {warns['count']}/3 | {warns['time']}"

        target_display = await get_user_or_group_mention(target_user)

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("История предупреждений", {"command": "warnhistory", "user": target_user, "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
            .add(Callback("Вся информация", {"command": "stats", "user": target_user, "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
        )

        await bot.api.messages.edit(
            peer_id=message.object.peer_id,
            conversation_message_id=message.object.conversation_message_id,
            message=f"Информация о активных предупреждениях {target_display}:\n{string_info}",
            keyboard=keyboard,
            disable_mentions=1
        )
        return

    # Команда stats для колбэков
    if command == "stats":
        if await get_role_cached(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return

        target_user = payload.get("user")
        if not target_user:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Ошибка: пользователь не найден!"})
            )
            return

        # Получаем статистику пользователя
        role = await get_role_cached(target_user, chat_id)
        warns = await get_warns(target_user, chat_id)
        if await is_nick(target_user, chat_id):
            nick = await get_user_nam(target_user, chat_id)
        else:
            nick = "Нет"
        messages = await message_stats(target_user, chat_id)
        roles = {0: "Пользователь", 1: "Модератор", 2: "Старший модератор", 3: "Администратор",
                 4: "Старший администратор", 5: "Заместитель специального администратора",
                 6: "Специальный администратор", 7: "Владелец беседы",
                 8: "Заместитель руководителя", 9: "Руководитель", 10: "Разработчик"}

        target_display = await get_user_or_group_mention(target_user)

        keyboard = (
            Keyboard(inline=True)
            .add(
                Callback("Активные предупреждения", {"command": "activewarns", "user": target_user, "chatId": chat_id}),
                color=KeyboardButtonColor.PRIMARY)
            .add(Callback("История предупреждений", {"command": "warnhistory", "user": target_user, "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
        )

        await bot.api.messages.edit(
            peer_id=message.object.peer_id,
            conversation_message_id=message.object.conversation_message_id,
            message=f"📊 Cтатистика {target_display}:\n\n"
                    f"🎭 Роль: {roles.get(role)}\n"
                    f"⚠️ Активные предупреждения: {warns}\n"
                    f"👾 Ник: {nick}\n"
                    f"💬 Всего сообщений: {messages['count']}\n"
                    f"📆 Последнее сообщение: {messages['last']}",
            keyboard=keyboard,
            disable_mentions=1
        )
        return

    # Команда warnhistory для колбэков
    if command == "warnhistory":
        if await get_role_cached(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return

        target_user = payload.get("user")
        if not target_user:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Ошибка: пользователь не найден!"})
            )
            return

        warnhistory_mass = await warnhistory(target_user, chat_id)
        if not warnhistory_mass:
            wh_string = "Предупреждений не было!"
        else:
            wh_string = '\n'.join(warnhistory_mass)

        target_display = await get_user_or_group_mention(target_user)

        keyboard = (
            Keyboard(inline=True)
            .add(
                Callback("Активные предупреждения", {"command": "activewarns", "user": target_user, "chatId": chat_id}),
                color=KeyboardButtonColor.PRIMARY)
            .add(Callback("Вся информация", {"command": "stats", "user": target_user, "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
        )

        await bot.api.messages.edit(
            peer_id=message.object.peer_id,
            conversation_message_id=message.object.conversation_message_id,
            message=f"Информация о всех предупреждениях {target_display}\n"
                    f"Количество предупреждений пользователя: {await get_warns(target_user, chat_id)}\n\n"
                    f"Информация о последних 10 предупреждений пользователя:\n{wh_string}",
            keyboard=keyboard,
            disable_mentions=1
        )
        return

    # Команда nonicks
    if command == "nonicks":
        if await get_role_cached(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return
        nonicks = await nonick(chat_id, 1)
        nonick_list = '\n'.join(nonicks)
        if nonick_list == "": nonick_list = "Пользователи без ников отсутствуют!"
        keyboard = (
            Keyboard(inline=True)
            .add(Callback("⏪", {"command": "nonickMinus", "page": 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.NEGATIVE)
            .add(Callback("С никами", {"command": "nicks", "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
            .add(Callback("⏩", {"command": "nonickPlus", "page": 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.POSITIVE)
        )
        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        await bot.api.messages.send(peer_id=2000000000 + chat_id,
                                    message=f"Пользователи без ников [1]:\n{nonick_list}\n\nПользователи с никами: «/1111t»",
                                    disable_mentions=1, random_id=0, keyboard=keyboard)
        return

    # Команда nicks
    if command == "nicks":
        if await get_role_cached(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return
        nicks = await nlist(chat_id, 1)
        nick_list = '\n'.join(nicks)
        if nick_list == "": nick_list = "Ники отсутствуют!"
        keyboard = (
            Keyboard(inline=True)
            .add(Callback("⏪", {"command": "nicksMinus", "page": 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.NEGATIVE)
            .add(Callback("Без ников", {"command": "nonicks", "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
            .add(Callback("⏩", {"command": "nicksPlus", "page": 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.POSITIVE)
        )
        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        await bot.api.messages.send(peer_id=2000000000 + chat_id,
                                    message=f"Пользователи с ником [1 страница]:\n{nick_list}\n\nПользователи без ников: «/nonick»",
                                    disable_mentions=1, keyboard=keyboard, random_id=0)
        return

    # Команда nonickminus
    if command == "nonickminus":
        if await get_role_cached(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return
        page = payload.get("page")
        if page < 2:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это первая страница!"})
            )
            return
        nonicks = await nonick(chat_id, 1)
        nonick_list = '\n'.join(nonicks)
        if nonick_list == "": nonick_list = "Пользователи без ников отсутствуют!"
        keyboard = (
            Keyboard(inline=True)
            .add(Callback("⏪", {"command": "nonickMinus", "page": page + 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.NEGATIVE)
            .add(Callback("С никами", {"command": "nicks", "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
            .add(Callback("⏩", {"command": "nonickPlus", "page": page + 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.POSITIVE)
        )
        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        await bot.api.messages.send(peer_id=2000000000 + chat_id,
                                    message=f"Пользователи без ников [{page - 1}]:\n{nonick_list}\n\nПользователи с никами: «/nlist»",
                                    disable_mentions=1, random_id=0, keyboard=keyboard)
        return

    # Команда nonickplus
    if command == "nonickplus":
        if await get_role_cached(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return
        page = payload.get("page")
        nonicks = await nonick(chat_id, page + 1)
        if len(nonicks) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это последняя страница!"})
            )
            return
        nonicks_str = '\n'.join(nonicks)
        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        await bot.api.messages.send(peer_id=2000000000 + chat_id,
                                    message=f"Пользователи без ников [{page + 1}]:\n{nonicks_str}\n\nПользователи с никами: «/nlist»",
                                    disable_mentions=1, random_id=0)
        return

    # Команда clear
    if command == "clear":
        if await get_role_cached(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return
        user = payload.get("user")
        await clear(user, chat_id, message.group_id, 2000000000 + chat_id)
        x = await bot.api.messages.get_by_conversation_message_id(peer_id=2000000000 + chat_id,
                                                                  conversation_message_ids=message.object.conversation_message_id,
                                                                  group_id=message.group_id)
        x = json.loads(x.json())['items'][0]['text']
        await bot.api.messages.edit(peer_id=2000000000 + chat_id, message=x,
                                    conversation_message_id=message.object.conversation_message_id, keyboard=None)
        user_display = await get_user_or_group_mention(user_id)
        await bot.api.messages.send(peer_id=2000000000 + chat_id,
                                    message=f"{user_display} очистил(-а) сообщения",
                                    disable_mentions=1, random_id=0)
        return

    # Команда unwarn
    if command == "unwarn":
        if await get_role_cached(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return
        user = payload.get("user")
        if await equals_roles(user_id, user, chat_id) < 2:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps(
                    {"type": "show_snackbar", "text": "Вы не можете снять пред данному пользователю!"})
            )
            return
        await unwarn(chat_id, user)
        x = await bot.api.messages.get_by_conversation_message_id(peer_id=2000000000 + chat_id,
                                                                  conversation_message_ids=message.object.conversation_message_id,
                                                                  group_id=message.group_id)
        x = json.loads(x.json())['items'][0]['text']
        await bot.api.messages.edit(peer_id=2000000000 + chat_id, message=x,
                                    conversation_message_id=message.object.conversation_message_id, keyboard=None)
        user_display = await get_user_or_group_mention(user_id)
        target_display = await get_user_or_group_mention(user)
        await bot.api.messages.send(peer_id=2000000000 + chat_id,
                                    message=f"{user_display} снял(-а) предупреждение {target_display}",
                                    disable_mentions=1, random_id=0)
        return

    # Команда unmute
    if command == "unmute":
        if await get_role_cached(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return
        user = payload.get("user")
        if await get_role_cached(user_id, chat_id) <= await get_role_cached(user, chat_id):
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return
        await unmute(user, chat_id)
        x = await bot.api.messages.get_by_conversation_message_id(peer_id=2000000000 + chat_id,
                                                                  conversation_message_ids=message.object.conversation_message_id,
                                                                  group_id=message.group_id)
        x = json.loads(x.json())['items'][0]['text']
        await bot.api.messages.edit(peer_id=2000000000 + chat_id, message=x,
                                    conversation_message_id=message.object.conversation_message_id, keyboard=None)
        user_display = await get_user_or_group_mention(user_id)
        target_display = await get_user_or_group_mention(user)
        await bot.api.messages.send(peer_id=2000000000 + chat_id,
                                    message=f"{user_display} размутил(-а) {target_display}",
                                    disable_mentions=1, random_id=0)
        return

    # Команда unban
    if command == "unban":
        if await get_role_cached(user_id, chat_id) < 2:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return
        user = payload.get("user")
        if await equals_roles(user_id, user, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps(
                    {"type": "show_snackbar", "text": "Вы не можете снять бан данному пользователю!"})
            )
            return
        await unban(user, chat_id)
        x = await bot.api.messages.get_by_conversation_message_id(peer_id=2000000000 + chat_id,
                                                                  conversation_message_ids=message.object.conversation_message_id,
                                                                  group_id=message.group_id)
        x = json.loads(x.json())['items'][0]['text']
        await bot.api.messages.edit(peer_id=2000000000 + chat_id, message=x,
                                    conversation_message_id=message.object.conversation_message_id, keyboard=None)
        user_display = await get_user_or_group_mention(user_id)
        target_display = await get_user_or_group_mention(user)
        await bot.api.messages.send(peer_id=2000000000 + chat_id,
                                    message=f"{user_display} разблокировал(-а) {target_display}",
                                    disable_mentions=1, random_id=0)
        return

    # Команда alt
    if command == "alt":
        commands_levels = {
            0: [
                '\nКоманды пользователей:',
                '/help — хелп, помощь',
                '/stats — стата, статистика',
                '/getid — id, ид',
                '/info — инфо',
                '/rules — правила',
                '/infobot — инфобот',
            ],
            1: [
                '\nКоманды модератора:',
                '/setnick — сетник, snick, ник',
                '/removenick — снятьник, рник, rnick',
                '/getnick — гник, гетник, gnick',
                '/getacc — аккаунт, гетакк'
                '/nlist — ники',
                '/nonick — none',
                '/kick — исключить, кик',
                '/warn — pred, варн, пред',
                '/unwarn — унварн, анварн, снятьпред',
                '/getwarn — гварн, гетварн, gwarn',
                '/warnhistory — историяварнов, историяпредов, гетварн, гварн',
                '/warnlist — warns, варны, варнлист',
                '/staff — стафф',
                '/mute — мут, мьют, муте',
                '/unmute — унмут, анмут, анмьют',
                '/getmute — гетмут, gmute, гмут',
                '/mutelist — мутлист, муты',
                '/clear — чистка, очистка, очистить',
                '/getban — гетбан, чекбан',
            ],
            2: [
                '\nКоманды Старшего модератора',
                '/addmoder — модер',
                '/ban — бан, блокировка',
                '/unban — анбан, снятьбан',
                '/removerole — rrole, снятьроль',
                '/onlinelist — олист',
                '/banlist — банлист, баны, bans',
            ],
            3: [
                '\nСписок команд Администратора:',
                '/addstmoder — стмодер',
                '/quiet — тишина',
                '/skick — скик, снят',
                '/online — ozov, озов',
                '/srole — prole, pullrole',
                '/zov — зов, вызов',
            ],
            4: [
                '\nСписок команд Старшего администратора:',
                '/addadmin — админ',
                '/szov — сзов',
                '/serverinfo —serveri',
                '/banwords — bws',
                '/filter — none',
                '/sban — сбан',
                '/pin — закрепить',
                '/unpin — открепить',
                '/sremovenick — srnick',
                '/sunban — сунбан, санбан',
                '/sremoverole — srrole',
            ],
            5: [
                '\nСписок команд Заместителя специального администратора:',
                '/addstadmin — стадмин',
                '/antiflood — none',
                '/server — none',
                '/gszov — гсзов',
                '/gsban — гсбан',
                '/gsunban — гсунбан',
                '/gssrole — none',
                '/gsrrole — none',
                '/gssnick — гсник',
                '/gsrnick — гсрник',
                '/gskick — гскик',
            ],
            6: [
                '\nСписок команд Специального администратора:',
                '/addzamspec — замспец, addzsa, зса',
                '/say — none',
                '/invite — none',
                '/leave — none',
                '/masskick all/все — none',
                '/rnickall — none',
                '/masskick — mkick',
                '/gserver — none',
                '/gserverinfo — gserveri',
            ],
            7: [
                '\nСписок команд Владельца беседы:',
                '/addspec — спец, addsa, са',
                '/welcometext — welcome',
                '/editowner — none',
            ],
        }
        user_role = await get_role_cached(user_id, chat_id)
        commands = []
        for i in commands_levels.keys():
            if i <= user_role:
                for b in commands_levels[i]:
                    commands.append(b)
        level_commands = '\n'.join(commands)
        await bot.api.messages.edit(peer_id=2000000000 + chat_id, message=f"Альтернативные команды\n\n{level_commands}",
                                    conversation_message_id=message.object.conversation_message_id, keyboard=None)
        return

@bot.on.private_message()
async def on_private_message(message: Message):
    await message.reply(
        'Здравствуйте, к сожалению, данный бот не принимает команды в личные сообщения, он создан для модерации бесед.\nЕсли вы хотите связать с разработчиком бота - @roman_makendi.\nЖелаем вам удачного использования нашего чат-бота GREAT MANAGER!')
    return True

async def chats_log(user_id=None, target_id=None, role=None, log=None):
    try:
        await db.execute(
            "INSERT INTO logchats (user_id, target_id, role, log) VALUES ($1, $2, $3, $4)",
            (user_id, target_id, role, log)
        )
        pass
        print(f"")
    except Exception as e:
        print(f"")

def format_number(n: int) -> str:
    return f"{n:,}".replace(",", ".")

@bot.on.chat_message()
async def on_chat_message(message: Message):
    # Системная защита: игнорируем сообщения от других ботов
    if message.from_id < 0 or (hasattr(message, 'is_bot') and message.is_bot):
        return True
    
    bot_identifiers = ['/', '+', '!']
    user_id = message.from_id
    chat_id = message.chat_id
    peer_id = message.peer_id
    text_start = message.text[:20] if message.text else ""
    cache_key = f"{message.peer_id}_{text_start}"
    current_time = time.time()
    if hasattr(ctx, 'last_messages'):
        if cache_key in ctx.last_messages:
            if current_time - ctx.last_messages[cache_key] < 2.0:
                return
    else:
        ctx.last_messages = {}
    ctx.last_messages[cache_key] = current_time
    for key in list(ctx.last_messages.keys()):
        if current_time - ctx.last_messages[key] > 10.0:
            del ctx.last_messages[key]
    arguments = message.text.split(' ')
    arguments_lower = message.text.lower().split(' ')
    try:
        if await db.fetchone("SELECT chat_id FROM banschats WHERE chat_id = $1", (chat_id,)):

            await message.reply("Имеется блокировка чата. Hе буду здесь работать.")
            return True
    except Exception:
        # Если таблицы нет, значит нет и блокировок
        pass

    global all_chat_title
    global chat_titles_string
    try:
        command_identifier = arguments[0].strip()[0]
        command = arguments_lower[0][1:]
    except:
        command_identifier = " "
        command = " "
    ggetban = await gcheckban(user_id, chat_id)

    if ggetban:
        print(8)
        return True

    try:
        if await db.fetchone("SELECT user_id FROM blacklist WHERE user_id = $1", (user_id,)):

            return True
    except:
        pass

    if command_identifier in bot_identifiers:
        # ПРОВЕРКА МУТА - удаляем сообщения
        if await check_chat(chat_id):
            # Проверяем, не в муте ли пользователь
            if await is_muted(user_id, chat_id):
                # Проверяем, не команда ли это (команды могут обрабатываться)
                is_command = False
                if message.text and len(message.text) > 0:
                    if message.text[0] in bot_identifiers:
                        is_command = True

                # Если это НЕ команда или команда от обычного пользователя - удаляем
                if not is_command or await get_role_cached(user_id, chat_id) < 1:
                    try:
                        await bot.api.messages.delete(
                            group_id=message.group_id,
                            peer_id=message.peer_id,
                            delete_for_all=True,
                            cmids=message.conversation_message_id
                        )
                    except Exception as e:
                        print(f"Ошибка при удалении сообщения замьюченного пользователя: {e}")

            # Далее остальные проверки (режим тишины и т.д.)
            elif await check_quit(chat_id) and await get_role_cached(user_id, chat_id) < 1:
                try:
                    await bot.api.messages.delete(group_id=message.group_id, peer_id=message.peer_id,
                                                  delete_for_all=True, cmids=message.conversation_message_id)
                except:
                    pass
            elif await check_quit(chat_id) and await get_role_cached(user_id, chat_id) < 1:
                try:
                    await bot.api.messages.delete(group_id=message.group_id, peer_id=message.peer_id,
                                                  delete_for_all=True, cmids=message.conversation_message_id)
                except:
                    pass
            else:
                for i in await get_banwords(chat_id):
                    if i in message.text.lower() and await get_role_cached(user_id, chat_id) < 1:
                        await mute(user_id, chat_id, 'Бот', 'Написание запрещенных слов', 30)
                        keyboard = (
                            Keyboard(inline=True)
                            .add(Callback("Снять мут", {"command": "unmute", "chatId": chat_id, "user": user_id}),
                                 color=KeyboardButtonColor.POSITIVE)
                        )
                        user_display = await get_user_or_group_mention(user_id)
                        await message.reply(
                            f"{user_display} получил(-а) мут на 30 минут за написание запрещенного слова!")
                        try:
                            await bot.api.messages.delete(group_id=message.group_id, peer_id=message.peer_id,
                                                          delete_for_all=True, cmids=message.conversation_message_id)
                        except:
                            pass
                        return True
        global bot_enabled, chat_mode, enabled_chats
        if command in ['startbot', 'включибот']:
            if await get_role_cached(user_id, chat_id) < 11:
                await message.reply("Недостаточно прав для этой команды.", disable_mentions=1)
                return
            bot_enabled = True
            await message.reply("Бот включен!", disable_mentions=1)
            return
        elif command in ['offbot', 'выключибот']:
            if (await get_role_cached(user_id, chat_id) or 0) < 11:
                await message.reply("Недостаточно прав для этой команды.", disable_mentions=1)
                return
            bot_enabled = False
            await message.reply("Бот выключен!", disable_mentions=1)
            return
        elif command in ['startbotchat', 'включиботчат']:
            if (await get_role_cached(user_id, chat_id) or 0) < 11:
                await message.reply("Недостаточно прав для этой команды.", disable_mentions=1)
                return
            bot_enabled = False
            await message.reply("Бот выключен во всех чатах.", disable_mentions=1)
            return
        elif command in ['startbotchat', 'включиботчат']:
            if (await get_role_cached(user_id, chat_id) or 0) < 9:
                await message.reply("Недостаточно прав для этой команды.", disable_mentions=1)
                return
            if not chat_id:
                await message.reply("Эту команду можно использовать только в групповых чатах.", disable_mentions=1)
                return
            chat_mode = "local"
            enabled_chats.add(chat_id)
            await message.reply("Бот активен только в этом чате. Режим: локальный.", disable_mentions=1)
            return
        elif command in ['stopbotchat', 'выключиботчат']:
            if await get_role_cached(user_id, chat_id) < 11:
                await message.reply("Недостаточно прав для этой команды.", disable_mentions=1)
                return
            if not chat_id:
                await message.reply("Эту команду можно использовать только в групповых чатах.", disable_mentions=1)
                return
            if chat_id in enabled_chats:
                enabled_chats.remove(chat_id)
                await message.reply("Бот выключен в этом чате (остается в локальном режиме для других).",
                                    disable_mentions=1)
            else:
                await message.reply("Бот не был активен в этом чате в локальном режиме.", disable_mentions=1)
            return
        if not bot_enabled and command not in ['startbot', 'включибот', 'offbot', 'выключибот', 'startbotchat',
                                               'включиботчат', 'stopbotchat', 'выключиботчат']:
            return True
        if chat_mode == "local":
            if not chat_id:
                return True
            if chat_id not in enabled_chats:
                return True

        if command in ['start', 'старт', 'активировать']:
            if not chat_id:
                await message.reply("Эту команду можно использовать только в беседе!", disable_mentions=1)
                return True
            if await check_chat(chat_id):
                await message.reply("Бот уже был активирован в этой беседе!", disable_mentions=1)
                return True
            try:
                x = await bot.api.messages.get_conversations_by_id(
                    peer_ids=peer_id, extended=1, fields='chat_settings', group_id=message.group_id
                )
                x = json.loads(x.model_dump_json())
                for i in x['items']:
                    owner = int(i["chat_settings"]["owner_id"])

                is_owner = (owner == user_id)
                is_admin = False
                if not is_owner:
                    members = await bot.api.messages.get_conversation_members(
                        peer_id=peer_id, group_id=message.group_id
                    )
                    members_dict = json.loads(members.json())
                    for item in members_dict.get('items', []):
                        if item.get('member_id') == user_id and item.get('is_admin', False):
                            is_admin = True
                            break

                if not (is_owner or is_admin):
                    await message.reply(
                        "Включить бота может только создатель беседы или администратор (со звездой)!",
                        disable_mentions=1
                    )
                    return True

                await new_chat(chat_id, peer_id, owner)
                await message.reply(
                    "Бот успешно активирован!\nДля списка команд напишите /помощь",
                    disable_mentions=1
                )
            except Exception as ex:
                print(f"Ошибка в /start: {ex}")
                await message.reply("Произошла ошибка при активации. Убедитесь, что боту выдана звезда!", disable_mentions=1)
                return True
            return True

        if command in ['banid', 'забанитьчат', 'забанить']:
            if (await get_role_cached(user_id, chat_id) or 0) < 7:
                await message.replyLocalizedMessage('Недостаточно прав!')
                return True
            if len(arguments) < 2:
                await message.reply("Укажите чат!")
                return True
            try:
                target_chat = int(arguments[1])
            except:
                await message.reply("Укажите чат!")
                return True
            if await db.fetchone("SELECT chat_id FROM banschats WHERE chat_id = $1", (target_chat,)):

                await message.reply("Беседа уже находится в блокировке!")
                return True
            await db.execute("INSERT INTO banschats (chat_id) VALUES ($1)", (target_chat,))
            pass
            target_peer = 2000000000 + target_chat
            await bot.api.messages.send(
                peer_id=target_peer,
                random_id=0,
                message=(
                    f"Уведомление!!!\nВаш чат был заблокирован в боте руководством бота."
                )
            )
            user_display = await get_user_or_group_mention(user_id)
            await message.reply(
                f"{user_display} заблокировал(-а) беседу №«{target_chat}»")
            return True

        if command in ["unbanid", "разбанчата"]:
            if await get_role_cached(user_id, chat_id) < 9:
                await message.replyLocalizedMessage('Недостаточно прав!')
                return True
            if len(arguments) < 2:
                await message.reply("Укажите чат!")
                return True
            try:
                target_chat = int(arguments[-1])
            except:
                await message.reply("Укажите чат!")
                return True
            if not await db.fetchone("SELECT chat_id FROM banschats WHERE chat_id = $1", (target_chat,)):

                await message.reply("Беседа и так находится в блокировке!")
                return True
            await db.execute("DELETE FROM banschats WHERE chat_id = $1", (target_chat,))
            pass
            target_peer = 2000000000 + target_chat
            await bot.api.messages.send(
                peer_id=target_peer,
                random_id=0,
                message=(
                    f"Чат разблокирован в боте!"
                )
            )
            user_display = await get_user_or_group_mention(user_id)
            await message.reply(
                f"{user_display} разблокировал(-а) беседу №«{target_chat}»")
            return True

        if command in ['addwhiteruk']:
            if await get_role_cached(user_id, chat_id) < 9:
                await message.reply("Недостаточно прав!")
                return True
            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            await addruk(user)
            await message.reply('Выдан вайт лист к доступу к боту')
            return True

        if command in ['delwhiteruk']:
            if await get_role_cached(user_id, chat_id) < 9:
                await message.reply("Недостаточно прав!")
                return True
            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            await delruk(user)
            await message.reply('Удален вайт лист доступа к боту')
            return True

        if command in ['listwhiteruk']:
            i = await ruklist()
            await message.reply(f'{i}')
            return True

        # ================== КОМАНДЫ СПЕЦИАЛЬНОГО РУКОВОДИТЕЛЯ (10+) ==================
        if command in ['обнулитьбанк', 'resetbank']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("❌ Недостаточно прав! Команда доступна только Специальному Руководителю (10+)", disable_mentions=1)
                return True

            target_id = None
            if message.reply_message:
                target_id = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                target_id = await getID(arguments[1])
            else:
                await message.reply("❌ Укажите пользователя!", disable_mentions=1)
                return True

            # Обнуляем банк
            await db.execute("UPDATE balance SET bank = 0 WHERE user_id = $1", (target_id,))
            pass

            target_display = await get_user_or_group_mention(target_id)
            await message.reply(
                f"✅ Банк обнулен!\n\n"
                f"👤 Пользователь: {target_display}\n"
                f"💰 Банк: 0₽\n\n"
                f"👤 Обнулил: {await get_user_or_group_mention(user_id)}",
                disable_mentions=1
            )

            # Логируем
            await db.execute(
                "INSERT INTO logchats (user_id, target_id, role, log) VALUES ($1, $2, $3, $4)",
                (user_id, target_id, 9, f"обнулил банк пользователю {target_id}")
            )
            pass
            return True

        if command in ['обнулитьвип', 'resetvip']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("❌ Недостаточно прав! Команда доступна только Специальному Руководителю (10+)", disable_mentions=1)
                return True

            target_id = None
            if message.reply_message:
                target_id = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                target_id = await getID(arguments[1])
            else:
                await message.reply("❌ Укажите пользователя!", disable_mentions=1)
                return True

            # Удаляем VIP статус
            await db.execute("DELETE FROM vip WHERE user_id = $1", (target_id,))
            pass

            target_display = await get_user_or_group_mention(target_id)
            await message.reply(
                f"✅ VIP статус обнулен!\n\n"
                f"👤 Пользователь: {target_display}\n"
                f"⭐ VIP: снят\n\n"
                f"👤 Обнулил: {await get_user_or_group_mention(user_id)}",
                disable_mentions=1
            )

            # Логируем
            await db.execute(
                "INSERT INTO logchats (user_id, target_id, role, log) VALUES ($1, $2, $3, $4)",
                (user_id, target_id, 9, f"обнулил VIP статус пользователю {target_id}")
            )
            pass
            return True

        if command in ['обнулитьимущ', 'resetproperty']:
            if await get_role_cached(user_id, chat_id) < 9:
                await message.reply("❌ Недостаточно прав! Команда доступна только Специальному Руководителю (9+)", disable_mentions=1)
                return True

            target_id = None
            if message.reply_message:
                target_id = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                target_id = await getID(arguments[1])
            else:
                await message.reply("❌ Укажите пользователя!", disable_mentions=1)
                return True

            # Получаем количество домов и машин до удаления
            houses_count = await db.fetchone('SELECT COUNT(*) FROM houses WHERE user_id = $1', target_id,)

            cars_count = await db.fetchone('SELECT COUNT(*) FROM cars WHERE user_id = $1', target_id,)

            # Удаляем все дома
            await db.execute("DELETE FROM houses WHERE user_id = $1", (target_id,))

            # Удаляем все машины
            await db.execute("DELETE FROM cars WHERE user_id = $1", (target_id,))
            pass

            target_display = await get_user_or_group_mention(target_id)
            await message.reply(
                f"✅ Имущество обнулено!\n\n"
                f"👤 Пользователь: {target_display}\n"
                f"🏠 Удалено домов: {houses_count}\n"
                f"🚗 Удалено машин: {cars_count}\n\n"
                f"👤 Обнулил: {await get_user_or_group_mention(user_id)}",
                disable_mentions=1
            )

            # Логируем
            await db.execute(
                "INSERT INTO logchats (user_id, target_id, role, log) VALUES ($1, $2, $3, $4)",
                (user_id, target_id, 9, f"обнулил имущество пользователю {target_id} (дома: {houses_count}, машины: {cars_count})")
            )
            pass
            return True

        if command in ['удалитьклан', 'deleteclan']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("❌ Недостаточно прав! Команда доступна только Специальному Руководителю (10+)", disable_mentions=1)
                return True

            if len(arguments) < 2:
                await message.reply("❌ Укажите ID клана или название!\nПример: /удалитьклан 5", disable_mentions=1)
                return True

            # Пытаемся найти клан по ID
            try:
                clan_id = int(arguments[1])
                clan = await db.fetchone('SELECT name FROM clans WHERE clan_id = $1', clan_id,)
                if not clan:
                    await message.reply("❌ Клан с таким ID не найден!", disable_mentions=1)
                    return True
            except ValueError:
                # Ищем по названию
                clan_name = " ".join(arguments[1:])
                clan = await db.fetchone('SELECT clan_id, name FROM clans WHERE LOWER(name) LIKE LOWER($1)', f"%{clan_name}%",)
                if not clan:
                    await message.reply("❌ Клан не найден!", disable_mentions=1)
                    return True
                clan_id = clan[0]

            # Получаем название клана
            clan_name = clan[0] if isinstance(clan, tuple) else clan

            # Удаляем клан
            await db.execute("DELETE FROM clan_members WHERE clan_id = $1", (clan_id,))
            await db.execute("DELETE FROM clans WHERE clan_id = $1", (clan_id,))
            pass

            await message.reply(
                f"✅ Клан удален!\n\n"
                f"🏰 Клан: {clan_name} (ID: {clan_id})\n"
                f"👤 Удалил: {await get_user_or_group_mention(user_id)}",
                disable_mentions=1
            )

            # Логируем
            await db.execute(
                "INSERT INTO logchats (user_id, target_id, role, log) VALUES ($1, $2, $3, $4)",
                (user_id, 0, 9, f"удалил клан {clan_name} (ID: {clan_id})")
            )
            pass
            return True

        if command in ['обнулитьнавык', 'resetskill']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("❌ Недостаточно прав! Команда доступна только Специальному Руководителю (10+)", disable_mentions=1)
                return True

            target_id = None
            if message.reply_message:
                target_id = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                target_id = await getID(arguments[1])
            else:
                await message.reply("❌ Укажите пользователя!", disable_mentions=1)
                return True

            # Обнуляем навык в jobs
            await db.execute("UPDATE jobs SET skill = 0 WHERE user_id = $1", (target_id,))

            # Обнуляем в user_skills
            await db.execute("UPDATE user_skills SET skill = 0 WHERE user_id = $1", (target_id,))
            pass

            target_display = await get_user_or_group_mention(target_id)
            await message.reply(
                f"✅ Навык обнулен!\n\n"
                f"👤 Пользователь: {target_display}\n"
                f"📊 Навык: 0\n\n"
                f"👤 Обнулил: {await get_user_or_group_mention(user_id)}",
                disable_mentions=1
            )

            # Логируем
            await db.execute(
                "INSERT INTO logchats (user_id, target_id, role, log) VALUES ($1, $2, $3, $4)",
                (user_id, target_id, 9, f"обнулил навык пользователю {target_id}")
            )
            pass
            return True

        if command in ['обнулитьбрак', 'resetmarriage']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("❌ Недостаточно прав! Команда доступна только Специальному Руководителю (10+)", disable_mentions=1)
                return True

            target_id = None
            if message.reply_message:
                target_id = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                target_id = await getID(arguments[1])
            else:
                await message.reply("❌ Укажите пользователя!", disable_mentions=1)
                return True

            # Проверяем, есть ли запись о браке
            marriage = await db.fetchone('SELECT * FROM marriage WHERE user1 = $2 OR user2 = $1', target_id, target_id)

            if not marriage:
                await message.reply("ℹ️ У пользователя нет активного брака!", disable_mentions=1)
                return True

            # Удаляем брак
            await db.execute("DELETE FROM marriage WHERE user1 = $1 OR user2 = $2", (target_id, target_id))
            pass

            target_display = await get_user_or_group_mention(target_id)
            await message.reply(
                f"✅ Брак обнулен!\n\n"
                f"👤 Пользователь: {target_display}\n"
                f"💍 Брак: расторгнут\n\n"
                f"👤 Обнулил: {await get_user_or_group_mention(user_id)}",
                disable_mentions=1
            )

            # Логируем
            await db.execute(
                "INSERT INTO logchats (user_id, target_id, role, log) VALUES ($1, $2, $3, $4)",
                (user_id, target_id, 9, f"обнулил брак пользователю {target_id}")
            )
            pass
            return True

        if command in ['обнулитьбиз', 'resetbusiness']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("❌ Недостаточно прав! Команда доступна только Специальному Руководителю (10+)", disable_mentions=1)
                return True

            target_id = None
            if message.reply_message:
                target_id = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                target_id = await getID(arguments[1])
            else:
                await message.reply("❌ Укажите пользователя!", disable_mentions=1)
                return True

            # Получаем количество бизнесов
            businesses_count = await db.fetchone('SELECT COUNT(*) FROM user_businesses WHERE user_id = $1', target_id,)

            if businesses_count == 0:
                await message.reply("ℹ️ У пользователя нет бизнесов!", disable_mentions=1)
                return True

            # Удаляем все бизнесы
            await db.execute("DELETE FROM user_businesses WHERE user_id = $1", (target_id,))
            pass

            target_display = await get_user_or_group_mention(target_id)
            await message.reply(
                f"✅ Бизнесы обнулены!\n\n"
                f"👤 Пользователь: {target_display}\n"
                f"🏢 Удалено бизнесов: {businesses_count}\n\n"
                f"👤 Обнулил: {await get_user_or_group_mention(user_id)}",
                disable_mentions=1
            )

            # Логируем
            await db.execute(
                "INSERT INTO logchats (user_id, target_id, role, log) VALUES ($1, $2, $3, $4)",
                (user_id, target_id, 9, f"обнулил бизнесы пользователю {target_id} (количество: {businesses_count})")
            )
            pass
            return True

        if command in ['snick', 'setnick', 'nick', 'addnick', 'ник', 'сетник', 'сник']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!")
                return True
            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if await equals_roles(user_id, user, chat_id) == 0:
                await message.reply("⛔️ Вы не можете установить ник данному пользователю!", disable_mentions=1)
                return True
            new_nick = get_string(arguments, arg)
            if not new_nick:
                await message.reply("Укажите ник пользователя!", disable_mentions=1)
                return True
            else:
                await setnick(user, chat_id, new_nick)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"👾 {user_display} установил новое имя {target_display}!\n🆕 Новый ник: {new_nick}",
                disable_mentions=1)
            return True

        if command in ['settings']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 5:
                await message.reply("Недостаточно прав!")
                return True
            antif = await get_antiflood(chat_id)
            if antif == 0:
                resultantif = '-'
            else:
                resultantif = '+'
            leave = await get_leave_kick(chat_id)
            if leave:
                resultleave = '+'
            else:
                resultleave = '-'
            invite = await get_invite_kick(chat_id)
            if invite:
                resultinvite = '+'
            else:
                resultinvite = '-'
            filter = await get_filter(chat_id)
            if filter:
                resultfilter = '+'
            else:
                resultfilter = '-'
            pull = await get_pull_id(chat_id)
            gpull = await get_gpull_id(chat_id)

            ir = await db.fetchone('SELECT chat_id FROM chats WHERE chat_id = $1', chat_id,)
            await message.reply(
                f'Настройки беседы:\n\nАйди чата: {ir}\nCистема AntiFlood: {resultantif}\nДобавление администраторами: {resultinvite}\nИсключение при выходе: {resultleave}\nФильтр запрещенных слов: {resultfilter}\nСервер: {pull}\nГлобальный сервер: {gpull}')
            return True

        if command in ['newcolumn', 'setcolumn']:
            if user_id != 597064735:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            table_name = str(arguments[1])
            column_name = str(arguments[2])
            column_type = str(arguments[3])
            try:
                await ensure_column_exists(table_name, column_name, column_type)
                await message.reply(
                    f"Успешно создана колонка {column_name} в таблице {table_name} класса {column_type}")
                return True
            except:
                await message.reply("Ошибка")
                return True

        if command in ['логиобщие', 'logs', 'logsmoders', 'логи']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 9:
                await message.replyLocalizedMessage('not_preminisionss')
                return True

            target = None
            if message.reply_message:
                target = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                target = await getID(arguments[1])

            if target:
                logs = await db.fetchall("SELECT * FROM logchats WHERE user_id = $1 ORDER BY rowid DESC LIMIT 9999999999999", (target,))

                if not logs:
                    target_display = await get_user_or_group_mention(target)
                    await message.reply(
                        f"У {target_display} отсутствуют записи в логах модерации.",
                        disable_mentions=1)
                    return True

                total = len(logs)
                per_page = MAX_LOGS
                max_page = (total + per_page - 1) // per_page

                async def get_moders_page(page: int):
                    start = (page - 1) * per_page
                    end = start + per_page
                    selected = logs[start:end]
                    formatted = []
                    for idx, entry in enumerate(selected, start=start + 1):
                        u_id, t_id, amount, log_text = entry

                        u_display = await get_user_or_group_mention(u_id)

                        if t_id:
                            t_display = await get_user_or_group_mention(t_id)
                        else:
                            t_display = "None"

                        a_display = f"{format_number(amount)}$" if amount else "None"
                        l_display = log_text if log_text else "—"

                        formatted.append(
                            f"{idx}. {u_display} | Кому: {t_display} | Роль: {a_display} | Лог: {l_display}")
                    return formatted

                page = 1
                moders_page = await get_moders_page(page)
                moders_text = "\n\n".join(moders_page)

                keyboard = (
                    Keyboard(inline=True)
                    .add(Callback("⏪", {"command": "modersMinus", "target": target, "page": 1}),
                         color=KeyboardButtonColor.NEGATIVE)
                    .add(Callback("⏩", {"command": "modersPlus", "target": target, "page": 1}),
                         color=KeyboardButtonColor.POSITIVE)
                )

                target_display = await get_user_or_group_mention(target)
                await message.reply(
                    f"Логи модерации {target_display} [1/{max_page}]:\n\n{moders_text}",
                    disable_mentions=1, keyboard=keyboard
                )
                return True

            else:
                logs = await db.fetchall("SELECT * FROM logchats ORDER BY rowid DESC LIMIT 9999999999999")

                if not logs:
                    await message.reply(f"Логи с действиями модераторов отсутствуют!", disable_mentions=1)
                    return True

                total = len(logs)
                per_page = MAX_LOGS
                max_page = (total + per_page - 1) // per_page

                async def get_moders_page(page: int):
                    start = (page - 1) * per_page
                    end = start + per_page
                    selected = logs[start:end]
                    formatted = []
                    for idx, entry in enumerate(selected, start=start + 1):
                        u_id, t_id, amount, log_text = entry

                        u_display = await get_user_or_group_mention(u_id)

                        if t_id:
                            t_display = await get_user_or_group_mention(t_id)
                        else:
                            t_display = "None"

                        a_display = f"{format_number(amount)}$" if amount else "None"
                        l_display = log_text if log_text else "—"

                        formatted.append(
                            f"{idx}. {u_display} | Кому: {t_display} | Роль: {a_display} | Лог: {l_display}")
                    return formatted

                page = 1
                moders_page = await get_moders_page(page)
                moders_text = "\n\n".join(moders_page)

                keyboard = (
                    Keyboard(inline=True)
                    .add(Callback("⏪", {"command": "modersAllMinus", "page": 1}),
                         color=KeyboardButtonColor.NEGATIVE)
                    .add(Callback("⏩", {"command": "modersAllPlus", "page": 1}), color=KeyboardButtonColor.POSITIVE)
                )

                await message.reply(
                    f"Общие логи модерации [1/{max_page}]:\n\n{moders_text}",
                    disable_mentions=1, keyboard=keyboard
                )
                return True

        if command in ['rnick', 'removenick', 'clearnick', 'cnick', 'рник', 'удалитьник', 'снятьник']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if await equals_roles(user_id, user, chat_id) == 0:
                await message.reply("⛔ Вы не можете удалить ник данному пользователю!", disable_mentions=1)
                return True
            await rnick(user, chat_id)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} убрал(-а) ник у {target_display}!",
                disable_mentions=1)
            return True

        if command in ['getacc', 'acc', 'гетакк', 'аккаунт', 'account']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            nick = get_string(arguments, 1)
            if not nick:
                await message.reply("Укажите ник!", disable_mentions=1)
                return True
            nick_result = await get_acc(chat_id, nick)
            if not nick_result:
                await message.reply(f"Ник {nick} никому не принадлежит!", disable_mentions=1)
            else:
                info = await bot.api.users.get(nick_result)
                target_display = await get_user_or_group_mention(nick_result)
                await message.reply(
                    f"Ник {nick} принадлежит - {target_display}",
                    disable_mentions=1)
            return True

        if command in ['getnick', 'gnick', 'гник', 'гетник']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = 0
            if message.reply_message:
                user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            nick = await get_nick(user, chat_id)
            target_display = await get_user_or_group_mention(user)
            if not nick:
                await message.reply(f"У данного {target_display} нет ника!", disable_mentions=1)
            else:
                await message.reply(f"Ник данного {target_display}: {nick}", disable_mentions=1)
            return True

        if command in ['никлист', 'ники', 'всеники', 'nlist', 'nickslist', 'nicklist', 'nicks']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            nicks = await nlist(chat_id, 1)
            nick_list = '\n'.join(nicks)
            if nick_list == "": nick_list = "Ники отсутствуют!"
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("⏪", {"command": "nicksMinus", "page": 1, "chatId": chat_id}),
                     color=KeyboardButtonColor.NEGATIVE)
                .add(Callback("Без ников", {"command": "nonicks", "chatId": chat_id}),
                     color=KeyboardButtonColor.PRIMARY)
                .add(Callback("⏩", {"command": "nicksPlus", "page": 1, "chatId": chat_id}),
                     color=KeyboardButtonColor.POSITIVE)
            )
            await message.reply(f"Пользователи с ником [1 страница]:\n{nick_list}\n\nПользователи без ников: «/nonick»",
                                disable_mentions=1, keyboard=keyboard)
            return True

        if command in ['nonick', 'nonicks', 'nonicklist', 'nolist', 'nnlist', 'безников', 'ноникс']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            nonicks = await nonick(chat_id, 1)
            nonick_list = '\n'.join(nonicks)
            if nonick_list == "": nonick_list = "Пользователи без ников отсутствуют!"
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("⏪", {"command": "nonickMinus", "page": 1, "chatId": chat_id}),
                     color=KeyboardButtonColor.NEGATIVE)
                .add(Callback("С никами", {"command": "nicks", "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
                .add(Callback("⏩", {"command": "nonickPlus", "page": 1, "chatId": chat_id}),
                     color=KeyboardButtonColor.POSITIVE)
            )
            await message.reply(f"Пользователи без ников [1]:\n{nonick_list}\n\nПользователи с никами: «/nlist»",
                                disable_mentions=1, keyboard=keyboard)
            return True

        if command in ['kick', 'кик', 'исключить']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            # ЗАЩИТА БОТА - НЕЛЬЗЯ КИКНУТЬ БОТА
            if user == BOT_ID or user == -232598001:
                await message.reply("🤖 Нельзя исключить бота из беседы!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете исключить данного пользователя!", disable_mentions=1)
                return True
            reason = get_string(arguments, arg)
            try:
                await bot.api.messages.remove_chat_user(chat_id, user)
            except:
                target_display = await get_user_or_group_mention(user)
                await message.reply(
                    f"Не удается исключить данного {target_display}! Необходимо забрать у него звезду.",
                    disable_mentions=1)
                return True
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("Очистить", {"command": "clear", "chatId": chat_id, "user": user}),
                     color=KeyboardButtonColor.NEGATIVE)
            )
            target_display = await get_user_or_group_mention(user)
            if not reason:
                await message.reply(
                    f"Пользователь {target_display} был исключен из конференции.\nПричина: Не указана!",
                    attachment='audio-2001815713_128815713', disable_mentions=1, keyboard=keyboard)

            else:
                await message.reply(
                    f"Пользователь {target_display} был исключен из конференции.\nПричина: {reason}",
                    attachment='audio-2001815713_128815713', disable_mentions=1, keyboard=keyboard)
            await rnick(user, chat_id)
            await roleG(user, chat_id, 0)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 5:
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"❗️ Уровень прав {user_display} был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")
            return True

        if command in ['vig', 'выг']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете выдать выговор данному пользователю!", disable_mentions=1)
                return True
            if await get_role_cached(user, chat_id) < 1:
                await message.reply('⛔️ Операция невозможна! Данный пользователь не является модератором')
                return True
            reason = get_string(arguments, arg)
            if not reason:
                await message.reply("Укажите причину выговора!")
                return True
            warns = await vigs(chat_id, user, user_id, reason)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            if warns < 3:
                await message.reply(
                    f"{user_display} выдал(-а) выговор модератору {target_display}\nПричина: {reason}\nКоличество выговоров: {warns}",
                    disable_mentions=1)
            else:
                await message.answer(
                    f"{user_display} выдал(-а) последний выговор модератору {target_display} (3/3)\nПричина: {reason}\n{target_display} была удалена роль и ник!",
                    disable_mentions=1)
                try:
                    await rnick(user, chat_id)
                    await roleG(user, chat_id, 0)
                except:
                    print('')
                await clear_vig(chat_id, user)
            await add_punishment(chat_id, user_id)

        if command in ['unvig', 'унвыг', 'анвыг', 'снятьвыг', 'минусвыг']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете снять выговор данному пользователю!", disable_mentions=1)
                return True
            if await get_vig(user, chat_id) < 1:
                await message.reply("У пользователя нет выговоров!")
                return True
            if await get_role_cached(user, chat_id) < 1:
                await message.reply('Операция невозможна! Данный пользователь не является модератором')
                return True
            warns = await unvig(chat_id, user)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} снял(-а) выговор модератору {target_display}\nКоличество выговоров: {warns}",
                disable_mentions=1)
            return True

        if command in ['getvig', 'gvig', 'getvig', 'гетвыг', 'гвыг']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("⛔️ Вы не указали @пользователя!", disable_mentions=1)
                return True
            if await get_role_cached(user, chat_id) < 1:
                await message.reply('⛔️ Операция невозможна! Данный пользователь не является модератором')
                return True
            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете cмотреть информацию данного модератора, так как он выше вас!",
                                    disable_mentions=1)
                return True
            warns = await gvig(user, chat_id)
            string_info = str
            if not warns:
                string_info = "Активных выговоров нет!"
            else:
                moder_display = await get_user_or_group_mention(warns['moder'])
                string_info = f"{moder_display} | {warns['reason']} | {warns['count']}/3 | {warns['time']}"

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display}, информация о активных выговоров {target_display}:\n{string_info}",
                disable_mentions=1)
            return True

        if command in ['warn', 'пред', 'варн', 'pred', 'предупреждение']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            # ЗАЩИТА БОТА - НЕЛЬЗЯ ВЫДАТЬ ВАРН БОТУ
            if user == BOT_ID or user == -232598001:
                await message.reply("🤖 Нельзя выдавать предупреждение боту!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете выдать пред данному пользователю!", disable_mentions=1)
                return True
            reason = get_string(arguments, arg)
            if not reason:
                await message.reply("Укажите причину предупреждения!")
                return True
            warns = await warn(chat_id, user, user_id, reason)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            if warns < 3:
                keyboard = (
                    Keyboard(inline=True)
                    .add(Callback("Снять варн", {"command": "unwarn", "user": user, "chatId": chat_id}),
                         color=KeyboardButtonColor.POSITIVE)
                    .add(Callback("Очистить", {"command": "clear", "chatId": chat_id, "user": user}),
                         color=KeyboardButtonColor.NEGATIVE)
                )
                await message.reply(
                    f"⚠️ {user_display} выдал(-а) предупреждение {target_display}\n✍️ Причина: {reason}\n🔢 Количество предупреждений: {warns}",
                    disable_mentions=1, keyboard=keyboard)
            else:
                keyboard = (
                    Keyboard(inline=True)
                    .add(Callback("Очистить", {"command": "clear", "chatId": chat_id, "user": user}),
                         color=KeyboardButtonColor.NEGATIVE)
                )
                await message.answer(
                    f"{user_display} выдал(-а) последнее предупреждение {target_display} (3/3)\nПричина: {reason}\n{target_display} был исключен за большое количество предупреждений!",
                    disable_mentions=1, keyboard=keyboard)
                try:
                    await bot.api.messages.remove_chat_user(chat_id=chat_id, member_id=user)
                except vk_api.exception.ApiError as e:
                    error_message_for_mod = ""
                    if e.code == 15:
                        error_message_for_mod = f"⚠️ Ошибка исключения {target_display}: У бота нет прав администратора в этом чате."
                    elif e.code == 935:
                        error_message_for_mod = f"⚠️ Ошибка исключения {target_display}: Пользователь не найден в чате или уже вышел."
                    else:
                        error_message_for_mod = f"⚠️ Ошибка исключения {target_display}: API ошибка {e.code} - {e.error}."
                    await message.answer(error_message_for_mod, disable_mentions=1)
                except Exception as e:
                    await message.answer(f"⚠️ Ошибка исключения {target_display}: Неизвестная ошибка ({e}).",
                                         disable_mentions=1)
                await clear_warns(chat_id, user)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"❗️ Уровень прав {user_display} был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")
            return True

        if command in ['unwarn', 'унварн', 'анварн', 'снятьпред', 'минуспред']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете снять пред данному пользователю!", disable_mentions=1)
                return True
            if await get_warns(user, chat_id) < 1:
                await message.reply("⛔️ У пользователя нет предупреждений!")
                return True
            warns = await unwarn(chat_id, user)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} снял(-а) предупреждение {target_display}\nКоличество предупреждений: {warns}",
                disable_mentions=1)
            return True

        if command in ['getwarn', 'gwarn', 'getwarns', 'гетварн', 'гварн']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Вы не указали @пользователя!", disable_mentions=1)
                return True
            warns = await gwarn(user, chat_id)
            string_info = str
            if not warns:
                string_info = "Активных предупреждений нет!"
            else:
                moder_display = await get_user_or_group_mention(warns['moder'])
                string_info = f"{moder_display} | {warns['reason']} | {warns['count']}/3 | {warns['time']}"
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("История предупреждений", {"command": "warnhistory", "user": user, "chatId": chat_id}),
                     color=KeyboardButtonColor.PRIMARY)
            )
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display}, информация о активных предупреждениях {target_display}:\n{string_info}",
                disable_mentions=1, keyboard=keyboard)
            return True

        if command in ['say']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 6:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            text = get_string(arguments)
            text = text.replace('/say', '')
            if not text:
                await message.reply('Пожалуйста введите текст!')
                return
            await message.answer(text)
            return True

        if command in ['topsms', 'топсмс']:
            top_10 = await topsms(chat_id)
            await message.answer(top_10)

        if command in ['warnhistory', 'historywarns', 'whistory', 'историяварнов', 'историяпредов']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            warnhistory_mass = await warnhistory(user, chat_id)
            if not warnhistory_mass:
                wh_string = "Предупреждений не было!"
            else:
                wh_string = '\n'.join(warnhistory_mass)
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("Активные предупреждения", {"command": "activewarns", "user": user, "chatId": chat_id}),
                     color=KeyboardButtonColor.PRIMARY)
                .add(Callback("Вся информация", {"command": "stats", "user": user, "chatId": chat_id}),
                     color=KeyboardButtonColor.PRIMARY)
            )
            target_display = await get_user_or_group_mention(user)
            await message.reply(
                f"Информация о всех предупреждениях {target_display}\nКоличество предупреждений пользователя: {await get_warns(user, chat_id)}\n\nИнформация о последних 10 предупреждений пользователя:\n{wh_string}",
                disable_mentions=1, keyboard=keyboard)
            return True

        if command in ['warnlist', 'warns', 'wlist', 'варны', 'варнлист']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            warns = await warnlist(chat_id)
            if warns == False:
                warns_string = "Пользователей с предупреждениями нет!"
            else:
                warns_string = '\n'.join(warns)
            user_display = await get_user_or_group_mention(user_id)
            await message.answer(
                f"{user_display}, список пользователей с варнами:\n{warns_string}",
                disable_mentions=1)
            return True

        if command in ['viglist', 'vigl', 'vlist', 'выги', 'выглист']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            warns = await viglist(chat_id)
            if warns == False:
                warns_string = "Пользователей с выговоровами нет!"
            else:
                warns_string = '\n'.join(warns)
            user_display = await get_user_or_group_mention(user_id)
            await message.answer(
                f"{user_display}, список пользователей с выговорами:\n{warns_string}",
                disable_mentions=1)
            return True

        # Пропускаем дубликат команды /staff - он ниже

        if command in ['reg', 'registration', 'regdate', 'рег', 'регистрация', 'датарегистрации']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                user = user_id
            registration_date = await get_registration_date(user)
            if registration_date:
                today = date.today()
                time_delta = today - registration_date
                years = time_delta.days // 365
                if years in [0, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 25, 26, 27, 28, 29, 30, 35,
                             36, 37, 38, 39, 40]:
                    yea = "лет"
                if years in [1, 21, 31, 41]:
                    yea = "год"
                if years in [2, 3, 4, 22, 23, 24, 32, 33, 34]:
                    yea = "года"
                months = (time_delta.days % 365) // 30
                if months == 1:
                    mon = "месяц"
                if months in [2, 3, 4]:
                    mon = "месяца"
                if months in [0, 5, 6, 7, 8, 9, 10, 11, 12]:
                    mon = "месяцев"
                days = (time_delta.days % 365) % 30
                if days in [1, 21, 31]:
                    day = "день"
                if days in [2, 3, 4, 22, 23, 24, 32]:
                    day = "дня"
                if days in [0, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 25, 26, 27, 28, 29, 30]:
                    day = "дней"
                time_passed_string = f"{years} {yea}, {months} {mon}, {days} {day}"
                user_display = await get_user_or_group_mention(user)
                await message.reply(
                    f"Информация о регистрации пользователя во ВКонтакте:\n\nНикнейм: {user_display}\nАйди ВКонтакте: {user}\nСсылка на страницу ВК:\nhttps://vk.com/id{user}\nДата регистрации пользователя:\n{registration_date.strftime('%d.%m.%Y')}\nС момента создания аккаунта:\n{time_passed_string}")
            else:
                await message.answer(f"Не удалось получить дату регистрации пользователя с ID {user_id}.")
            return True

        if command in ['mute', 'мут', 'мьют', 'муте', 'addmute']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            arg = 0
            reason_start_index = 0

            if message.reply_message:
                user = message.reply_message.from_id
                reason_start_index = 2
                time_arg_index = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                reason_start_index = 2
                time_arg_index = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                reason_start_index = 3
                time_arg_index = 2
            else:
                await message.reply("Укажите пользователя!")
                return True

            # ЗАЩИТА БОТА - НЕЛЬЗЯ ЗАМУТИТЬ БОТА
            if user == BOT_ID or user == -232598001:
                await message.reply("🤖 Нельзя замутить бота!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔ Вы не можете выдать мут данному пользователю!", disable_mentions=1)
                return True

            # Проверяем, не замьючен ли уже пользователь
            if await is_muted(user, chat_id):
                await message.reply("⛔️ Пользователь уже замьючен!")
                return True

            # Получаем аргумент времени
            time_arg = None
            if len(arguments) > time_arg_index:
                time_arg = arguments[time_arg_index].lower()

            # Получаем причину
            reason = get_string(arguments, reason_start_index)

            # Определяем время мута
            mute_time = 0  # По умолчанию навсегда
            time_display = "навсегда"

            if time_arg:
                try:
                    potential_time = int(time_arg)
                    if potential_time > 0:
                        mute_time = potential_time
                        time_display = f"{mute_time} мин"
                except ValueError:
                    if time_arg in ['навсегда', 'бессрочно', 'forever', 'perm', '∞']:
                        mute_time = 0
                        time_display = "навсегда"
                        if reason:
                            words = reason.split()
                            if words and words[0].lower() in ['навсегда', 'бессрочно', 'forever', 'perm', '∞']:
                                reason = ' '.join(words[1:])
                    else:
                        mute_time = 0
                        time_display = "навсегда"
                        if reason:
                            reason = f"{time_arg} {reason}"
                        else:
                            reason = time_arg

            if not reason:
                reason = "Не указана"

            try:
                # Выдаем мут
                result = await mute(user, chat_id, user_id, reason, mute_time)

                if mute_time > 0:
                    expire_time = moscow_fromtimestamp(result["expire_time"])
                    expire_str = expire_time.strftime('%d.%m.%Y %H:%M')
                    time_text = f"до {expire_str}"
                else:
                    time_text = "навсегда"

                keyboard = (
                    Keyboard(inline=True)
                    .add(Callback("Снять мут", {"command": "unmute", "user": user, "chatId": chat_id}),
                         color=KeyboardButtonColor.POSITIVE)
                    .add(Callback("Очистить", {"command": "clear", "chatId": chat_id, "user": user}),
                         color=KeyboardButtonColor.NEGATIVE)
                )

                user_display = await get_user_or_group_mention(user_id)
                target_display = await get_user_or_group_mention(user)
                await message.answer(
                    f"🤫 {user_display} замутил(-а) {target_display}\n"
                    f"✍️ Причина: {reason}\n"
                    f"🕖 Мут: {time_text}",
                    disable_mentions=1, keyboard=keyboard
                )

            except Exception as e:
                await message.reply(f"❌ Ошибка: {str(e)}", disable_mentions=1)

            await add_punishment(chat_id, user_id)
            return True

        if command in ['unmute', 'снятьмут', 'анмут', 'анмьют', 'унмут']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if not await is_muted(user, chat_id):
                await message.reply("ℹ️ У пользователя нет активного мута!", disable_mentions=1)
                return True

            try:
                result = await unmute(user, chat_id)

                user_display = await get_user_or_group_mention(user_id)
                target_display = await get_user_or_group_mention(user)
                await message.answer(
                    f"👾 {user_display} размутил(-а) {target_display}",
                    disable_mentions=1
                )

            except Exception as e:
                await message.reply(f"❌ Ошибка: {str(e)}", disable_mentions=1)

            return True

        if command in ['getmute', 'gmute', 'гмут', 'гетмут', 'чекмут']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            mute_info = await get_mute(user, chat_id)

            if not mute_info:
                target_display = await get_user_or_group_mention(user)
                await message.reply(f"ℹ️ У {target_display} нет активного мута!", disable_mentions=1)
                return True

            if mute_info["time"] > 0:
                if time.time() > mute_info["expire_time"]:
                    target_display = await get_user_or_group_mention(user)
                    await message.reply(f"ℹ️ У {target_display} мут истек!", disable_mentions=1)
                    await unmute(user, chat_id, auto=True)
                    return True

                expire_time = moscow_fromtimestamp(mute_info["expire_time"])
                expire_str = expire_time.strftime('%d.%m.%Y %H:%M')
                time_text = f"До: {expire_str}"
            else:
                time_text = "Навсегда"

            moder_name = await get_user_or_group_name(mute_info["moder"]) if mute_info["moder"] != "Бот" and mute_info[
                "moder"] != "Bot" else "Бот"
            target_display = await get_user_or_group_mention(user)

            await message.reply(
                f"🔇 Информация о муте {target_display}:\n\n"
                f"👤 Модератор: {moder_name}\n"
                f"📝 Причина: {mute_info['reason']}\n"
                f"⏰ {time_text}",
                disable_mentions=1
            )

            return True

        if command in ['mutelist', 'mutes', 'муты', 'мутлист']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            mutes = await mutelist(chat_id)

            if not mutes:
                await message.reply("📭 В чате нет замьюченных пользователей!", disable_mentions=1)
            else:
                muted_list = "\n".join(mutes)
                await message.reply(
                    f"🔇 Список замьюченных пользователей ({len(mutes)}):\n\n{muted_list}",
                    disable_mentions=1
                )

            return True

        if command in ['clear', 'чистка', 'очистить', 'очистка']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете очистить сообщения данного пользователя!", disable_mentions=1)
                return True
            cmid = message.reply_message.conversation_message_id
            await clear(cmid, chat_id, message.group_id, message.peer_id)
            user_display = await get_user_or_group_mention(user_id)
            await message.reply(f"{user_display} очистил(-а) сообщение(-я)!")
            return True

        if command in ['q', 'quit', 'выйти']:
            # Пользователь может выйти из чата по собственному желанию
            target_id = user_id
            
            # Проверяем, не является ли пользователь владельцем чата
            chat_owner = await db.fetchone('SELECT owner_id FROM chats WHERE chat_id = $1', chat_id,)
            
            if chat_owner and chat_owner[0] == target_id:
                await message.reply("❌ Вы не можете покинуть чат, так как являетесь владельцем! Передайте права через /editowner", disable_mentions=1)
                return True
            
            try:
                await bot.api.messages.remove_chat_user(chat_id, target_id)
                
                target_display = await get_user_or_group_mention(target_id)
                await message.reply(
                    f"🚪 {target_display} покинул(-а) беседу по собственному желанию.",
                    disable_mentions=1
                )
            except Exception as e:
                await message.reply(f"❌ Не удалось исключить пользователя: {e}", disable_mentions=1)
            
            return True

        if command in ['help', 'хелп', 'помощь', 'команды', 'commands']:
            commands_levels = {
                0: [
                    '\n👾 Команды пользователей:',
                    '/help — список доступных вам команд',
                    '/stats — информация о пользователе',
                    '/getid — узнать оригинальный ID пользователя в ВК',
                    '/rules — правила',
                    '/info — инфо',
                    '/infobot — ресурсы бота',
                    '/q — выйти из беседы по собственному желанию',
                ],
                1: [
                    '\n⚡️ Команды модератора:',
                    '/delete — удалить смс скрытно',
                    '/setnick — сменить ник у пользователя',
                    '/reg — посмотреть дату регистрации пользователя',
                    '/removenick — очистить ник у пользователя',
                    '/mstats — статистика модератора',
                    '/getnick — проверить ник пользователя',
                    '/getacc — узнать пользователя по нику',
                    '/nlist — просмотреть ники пользователей',
                    '/nonick — пользователи без ников',
                    '/kick — исключить пользователя из беседы',
                    '/warn — выдать предупреждение пользователю',
                    '/unwarn — снять предупреждение пользователю',
                    '/getwarn — информация о активных предупреждениях пользователя',
                    '/warnhistory — информация о всех предупреждениях пользователя',
                    '/warnlist — список пользователей с варном',
                    '/staff — пользователи с ролями',
                    '/mute — замутить пользователя',
                    '/unmute — размутить пользователя',
                    '/getmute — информация о муте пользователя',
                    '/mutelist — список пользователей с мутом',
                    '/gcheckban — информация о блокировках пользователя во всех беседах',
                    '/clear — очистить сообщения',
                    '/getban — информация о банах пользователя',
                ],
                2: [
                    '\n💫 Команды Старшего модератора:',
                    '/addmoder — выдать пользователю права модератора',
                    '/ban — заблокировать пользователя в беседе',
                    '/unban — разблокировать пользователя в беседе',
                    '/removerole — забрать роль у пользователя',
                    '/onlinelist — посмотреть пользователей в онлайн',
                    '/banlist — посмотреть заблокированных',
                ],
                3: [
                    '\n✨ Список команд Администратора:',
                    '/addstmoder — выдать пользователю права старшего модератора',
                    '/quiet — Включить выключить режим тишины',
                    '/skick — исключить пользователя с бесед сетки',
                    '/online — упомянуть пользователей онлайн',
                    '/srole — выдать права',
                    '/zov — упомянуть всех пользователей',
                    '/vig — выдать выговор модератору',
                    '/unvig — снять выговор модератору',
                    '/viglist — список выговоров модераторов',
                    '/getvig — история выговоров модератора',
                ],
                4: [
                    '\n💫 Список команд Старшего администратора:',
                    '/addadmin — выдать пользователю права администратора',
                    '/szov — вызов участников бесед сетки',
                    '/serverinfo — информация о сетке бесед',
                    '/banwords — запрещенные в беседе слова',
                    '/filter — фильтр запрещенных слов',
                    '/pin — закрепить сообщение',
                    '/unpin — открепить сообщение',
                    '/sban — заблокировать пользователя в сетке бесед',
                    '/sunban — разбанить пользователя в сетке бесед',
                    '/ssrole — выдать права в сетке бесед',
                    '/ssnick — выдать ник в сетке бесед',
                    '/sremovenick — очистить ник у пользователя в сетке бесед',
                    '/sremoverole — забрать роль у пользователя в сетке бесед',
                ],
                5: [
                    '\n⭐️ Список команд Заместителя специального администратора:',
                    '/addstadmin — выдать пользователю права старшего администратора',
                    '/antiflood — режим защиты от спама',
                    '/server — изменить сетку бесед',
                    '/settings — посмотреть настройки беседы',
                    '/gszov — вызвать участников в глобальном сервере',
                    '/gsban — заблокировать пользователя в глобальном сервере',
                    '/gsunban — разблокировать пользователя в глобальном сервере',
                    '/gssrole — выдать права в глобальном сервере',
                    '/gsrrole — забрать права в глобальном сервере',
                    '/gssnick — установить ник в глобальном сервере',
                    '/gsrnick — удалить ник в глобальном сервере',
                    '/gskick — исключить пользователя в глобальном сервере',
                ],
                6: [
                    '\n🌟 Список команд Специального администратора:',
                    '/addzamspec — выдать пользователю права заместителя специального администратора',
                    '/say — написать сообщение от имени бота',
                    '/invite — система добавления пользователей только модераторами',
                    '/leave — система исключения пользователей при выходе',
                    '/masskick all/все — исключить участников без ролей',
                    '/rnickall — очистить все ники в беседе',
                    '/masskick — исключить нескольких пользователей',
                    '/gserver — привязать беседу к глобальному серверу',
                    '/rename — изменить название чата',
                    '/gserverinfo — информация о глобальном сервере',
                ],
                7: [
                    '\n👑 Список команд Владельца бесед:',
                    '/addspec — выдать пользователю права специального администратора',
                    '/welcometext — текст приветствия',
                    '/editowner — передать права Владельца беседы',
                    '/demote — расформировать беседу исключив всех',
                    '/setinfo — установить инфо в беседе',
                    '/setrules — установить правила в беседе',
                    '/addchatowner — выдать пользователю права владельца беседы',
                ],
                8: [
                    '\n💼 Список команд Заместителя Руководителя:',
                    '/zunban — снять пользователю блокировки во всех беседах',
                    '/gban — заблокировать пользователя во всех беседах бота',
                    '/ungban — разблокировать пользователя во всех беседах',
                    '/gbanlist — список глобальных блокировок в беседах игроков',
                    '/blacklist — черный список бота',
                    '/gstaff — пользователи с глобальными ролями',
                    '/infochat — информация о беседе по айди',
                ],
                9: [
                    '\n📋 Список команд Основного Заместителя Руководителя:',
                    '/setowner — установить владельца беседы',
                    '/grrole — забрать глобальную роль у пользователя (снимает роли 8+)',
                    '/gzammanager — выдать глобальные права Заместителя Руководителя',
                    '/логи — логи модерации (по пользователю или общие)',
                    '/логиэко — логи экономики (по пользователю или общие)',
                ],
                10: [
                    '\n💎 Список команд Специального Руководителя:',
                    '/goszammanager — выдать глобальные права Основного Заместителя Руководителя',
                    '/sayall — рассылка по всем чатам',
                    '/news — рассылка новостей',
                    '/gzov — вызвать участников во всех чатах',
                    '/infoid — группы по айди владельца',
                    '/banid — забанить группу в боте по чат айди',
                    '/unbanid — разбанить группу в боте по чат айди',
                    '/clearchat — очистить все данные из чата',
                    '/delchat — удалить чат из базы данных',
                    '/чаты — список зарегистрированных бесед',
                    '/addblack — добавить пользователя в черный список бота',
                    '/unblack — вынести пользователя из черного списка бота',
                    '/clearbans — удалить все блокировки в чате',
                    '/выдатьбанк — выдать деньги пользователю',
                    '/выдатьвип — выдать VIP статус',
                    '/выдатьдом — выдать дом',
                    '/выдатьмашину — выдать машину',
                    '/выдатьбиз — выдать бизнес',
                    '/обнулитьбанк — обнулить баланс',
                    '/обнулитьвип — обнулить VIP',
                    '/обнулитьимущ — обнулить имущество',
                    '/обнулитьнавык — обнулить навык',
                    '/обнулитьбрак — обнулить брак',
                    '/обнулитьбиз — обнулить бизнес',
                    '/удалитьклан — удалить клан',
                ],
                11: [
                    '\n🔧 Список команд Разработчика:',
                    '/adddev — выдать права Разработчика',
                    '/разраб — выдать себе права Разработчика',
                    '/оффроль — снять права Разработчика',
                    '/startbot — запустить бота',
                    '/offbot — отключить бота',
                    '/infoid — чатыпользователя',
                    '/фиксбиз — исправить базу данных бизнесов',
                    '/gmanager — выдать права Специального Руководителя'
                ],
            }
            user_role = await get_role_cached(user_id, chat_id) or 0
            commands = []
            for i in commands_levels.keys():
                if i <= user_role:
                    for b in commands_levels[i]:
                        commands.append(b)
            level_commands = '\n'.join(commands)
            
            keyboard = None
            if user_role > 0:
                keyboard = (
                    Keyboard(inline=True)
                    .add(Callback("Альтернативные команды", {"command": "alt", "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
                )

            await message.reply(f"📋 Список команд бота:\n\n{level_commands}", disable_mentions=1, keyboard=keyboard)
            return True

        if command in ['alt', 'альт', 'альтернативные']:
            commands_levels = {
                0: [
                    '\n👾 Команды пользователей:',
                    '/help — хелп, помощь',
                    '/stats — стата, статистика',
                    '/getid — id, ид',
                    '/infobot — инфобот',
                    '/getid — id, ид',
                    '/rules — правила',
                    '/info — инфо',
                    '/infobot — инфобот',
                    '/q — выйти, выход',
                ],
                1: [
                    '\n⚡️ Команды модератора:',
                    '/setnick — сетник, snick, ник',
                    '/removenick — снятьник, рник, rnick',
                    '/getnick — гник, гетник, gnick',
                    '/getacc — аккаунт, гетакк',
                    '/nlist — ники',
                    '/reg — рег',
                    '/nonick — none',
                    '/kick — исключить, кик',
                    '/warn — pred, варн, пред',
                    '/unwarn — унварн, анварн, снятьпред',
                    '/getwarn — гварн, гетварн, gwarn',
                    '/warnhistory — историяварнов, историяпредов, гетварн, гварн',
                    '/warnlist — warns, варны, варнлист',
                    '/staff — стафф',
                    '/mute — мут, мьют, муте',
                    '/unmute — унмут, анмут, анмьют',
                    '/getmute — гетмут, gmute, гмут',
                    '/mutelist — мутлист, муты',
                    '/gcheckban — гчекбан',
                    '/clear — чистка, очистка, очистить',
                    '/getban — гетбан, чекбан',
                ],
                2: [
                    '\n💫 Команды Старшего модератора',
                    '/addmoder — модер',
                    '/ban — бан, блокировка',
                    '/unban — анбан, снятьбан',
                    '/removerole — rrole, снятьроль',
                    '/onlinelist — олист',
                    '/banlist — банлист, баны, bans',
                    '/banlist — банлист, баны, bans',
                ],
                3: [
                    '\n✨ Список команд Администратора:',
                    '/addstmoder — стмодер',
                    '/quiet — тишина',
                    '/skick — скик, снят',
                    '/online — ozov, озов',
                    '/sremovenick — srnick',
                    '/srole — prole, pullrole',
                    '/zov — зов, вызов',
                ],
                4: [
                    '\n💫 Список команд Старшего администратора:',
                    '/addadmin — админ',
                    '/szov — сзов',
                    '/serverinfo —serveri',
                    '/banwords — bws',
                    '/filter — none',
                    '/pin — закрепить',
                    '/unpin — открепить',
                    '/sban — сбан',
                    '/sunban — сунбан, санбан',
                    '/sremoverole — srrole',
                ],
                5: [
                    '\n⭐️ Список команд Заместителя специального администратора:',
                    '/addstadmin — стадмин',
                    '/antiflood — none',
                    '/server — none',
                    '/gszov — гсзов',
                    '/gsban — гсбан',
                    '/gsunban — гсунбан',
                    '/gssrole — none',
                    '/gsrrole — none',
                    '/gssnick — гсник',
                    '/gsrnick — гсрник',
                    '/gskick — гскик',
                ],
                6: [
                    '\n🌟 Список команд Специального администратора:',
                    '/addzamspec — замспец, addzsa, зса, spec',
                    '/say — none',
                    '/invite — none',
                    '/leave — none',
                    '/masskick all/все — none',
                    '/rnickall — none',
                    '/masskick — mkick',
                    '/gserver — none',
                    '/gserverinfo — gserveri',
                ],
                7: [
                    '\n👑 Список команд Владельца беседы:',
                    '/addspec — спец, addsa, са',
                    '/welcometext — welcome',
                    '/demote — расформ беседы',
                    '/editowner — none',

                ],
                8: [
                    '\n✨ Список команд Заместителя Руководителя:',
                    '/gzammanager — выдать права Заместителя Руководителя',
                    '/gban — гбан, глобалбан',
                    '/ungban — унгбан',
                    '/blacklist — черныйсписок, ЧСБ',
                    '/infochat — инфочат',
                ],
                9: [
                    '\n💫 Список команд Основного Заместителя Руководителя:',
                    '/goszammanager — выдать права Основного Заместителя Руководителя',
                    '/grrole — снять глобальную роль',
                    '/setowner — установить владельца',
                    '/dban — дбан',
                    '/news — рассылка',
                    '/gzammanager — выдать права Заместителя Руководителя',
                    '/логи — logs, логиобщие',
                    '/логиэко — logeco, logeconomy',
                ],
                10: [
                    '\n🔮 Список команд Специального Руководителя:',
                    '/чаты — listchats, листчатов, списокбесед',
                    '/goszammanager — выдать права Основного Заместителя Руководителя',
                    '/sayall — рассылка по всем чатам',
                    '/news — рассылка новостей',
                    '/gzov — вызвать участников во всех чатах',
                    '/infoid — группы по айди владельца',
                    '/banid — забанить группу в боте по чат айди',
                    '/unbanid — разбанить группу в боте по чат айди',
                    '/clearchat — очистить все данные из чата',
                    '/delchat — удалить чат из базы данных',
                    '/addblack — добавить пользователя в черный список бота',
                    '/unblack — вынести пользователя из черного списка бота',
                    '/clearbans — удалить все блокировки в чате',
                    '/выдатьбанк — givebank',
                    '/выдатьвип — givevip',
                    '/выдатьдом — givehouse',
                    '/выдатьмашину — givecar',
                    '/выдатьбиз — givebusiness',
                    '/обнулитьбанк — resetbank',
                    '/обнулитьвип — resetvip',
                    '/обнулитьимущ — resetproperty',
                    '/обнулитьнавык — resetskill',
                    '/обнулитьбрак — resetmarriage',
                    '/обнулитьбиз — resetbusiness',
                    '/удалитьклан — deleteclan',
                ],
                11: [
                    '\n🔧 Список команд Разработчика:',
                    '/adddev — выдать права Разработчика',
                    '/разраб — выдать себе права Разработчика',
                    '/оффроль — снять права Разработчика',
                    '/startbot — запустить бота',
                    '/offbot — отключить бота',
                    '/infoid — чатыпользователя',
                    '/фиксбиз — исправить базу данных бизнесов',
                    '/gmanager — выдать права Специального Руководителя',
                ],
            }
            user_role = await get_role_cached(user_id, chat_id)
            commands = []
            for i in commands_levels.keys():
                if i <= user_role:
                    for b in commands_levels[i]:
                        commands.append(b)
            level_commands = '\n'.join(commands)
            await message.reply(f"Альтернативные команды\n\n{level_commands}", disable_mentions=1)
            return True

        if command in ['pin', 'закрепить']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            if message.reply_message:
                target = message.reply_message.conversation_message_id
                chati = message.peer_id
            try:
                await bot.api.messages.pin(peer_id=chati, conversation_message_id=target)
                await message.answer('Сообщение закреплено')
            except Exception as e:
                await message.reply('Ошибка при закреплении сообщения')
            return True

        if command in ['rename']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 6:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = get_string(arguments)
            user = user.replace('/rename', '')
            try:
                await bot.api.messages.edit_chat(chat_id={chat_id}, title={user})
                await message.answer(f'Название чата изменено на {user}')
            except Exception as e:
                await message.reply(f'Ошибка при изменении названия чата {e}')
            return True

        if command in ['unpin', 'открепить']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            chati = chat_id + 2000000000
            try:
                await bot.api.messages.unpin(peer_id=chati)
                await message.answer('Сообщение откреплено')
            except Exception as e:
                await message.reply('Ошибка при откреплении сообщения')
            return True

        if command in ['getban', 'чекбан', 'гетбан', 'checkban']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            # Проверяем бан в чате
            getban = await checkban(user, chat_id)

            if not getban:
                getban_str = '🔓 Блокировка отсутствует!'
            else:
                moder_display = await get_user_or_group_mention(getban['moder'])

                # Формируем информацию о времени
                duration_info = ""
                ban_time = getban.get('ban_time', 0)
                ban_expire = getban.get('ban_expire', 0)
                duration_text = getban.get('duration_text', 'навсегда')

                print(f"DEBUG: ban_time={ban_time}, ban_expire={ban_expire}, duration_text={duration_text}")

                if ban_time > 0:
                    if ban_expire > 0:
                        expire_time = moscow_fromtimestamp(ban_expire)
                        if expire_time > moscow_now():
                            duration_info = f"\n⏰ Длительность: {duration_text}\n📅 Снятие: {expire_time.strftime('%d.%m.%Y %H:%M')}"
                        else:
                            duration_info = f"\n⏰ Бан истёк!"
                    else:
                        duration_info = f"\n⏰ Длительность: {duration_text}"
                else:
                    duration_info = "\n⏰ Длительность: навсегда"

                getban_str = f"🔨 Кем выдана: {moder_display}\n📝 Причина: {getban['reason']}\n📅 Дата: {getban['date_string']}{duration_info}"

            # Проверяем глобальный бан
            ggetban = await gcheckban(user)

            if not ggetban:
                ggetban_str = '🌐 Отсутствует!'
            else:
                moder_display = await get_user_or_group_mention(ggetban['moder'])
                ggetban_str = f"🌐 Кем выдана: {moder_display}\n📝 Причина: {ggetban['reason']}\n📅 Дата: {ggetban['date_string']}"

            target_display = await get_user_or_group_mention(user)

            await message.reply(
                f"🔍 ИНФОРМАЦИЯ О БЛОКИРОВКАХ {target_display}:\n\n"
                f"🌐 ГЛОБАЛЬНАЯ БЛОКИРОВКА:\n{ggetban_str}\n\n"
                f"💬 БЛОКИРОВКА В ЧАТЕ:\n{getban_str}",
                disable_mentions=1
            )
            return True

        if command in ['staff', 'стафф']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            staff_mass = await staff(chat_id)

            if staff_mass is None:
                staff_str = "В данной беседе нет пользователей с ролями!"
                await message.reply(staff_str, disable_mentions=1)
                return True
            else:
                moders = '\n'.join(staff_mass['moders']) if staff_mass['moders'] else "Отсутствуют"
                stmoders = '\n'.join(staff_mass['stmoders']) if staff_mass['stmoders'] else "Отсутствуют"
                admins = '\n'.join(staff_mass['admins']) if staff_mass['admins'] else "Отсутствуют"
                stadmins = '\n'.join(staff_mass['stadmins']) if staff_mass['stadmins'] else "Отсутствуют"
                zamspec = '\n'.join(staff_mass['zamspec']) if staff_mass['zamspec'] else "Отсутствуют"
                spec = '\n'.join(staff_mass['spec']) if staff_mass['spec'] else "Отсутствуют"
                chat_owner = '\n'.join(staff_mass['owner']) if staff_mass['owner'] else "Отсутствуют"

                owner = await get_chat_owner_display(chat_id)

                await message.reply(
                    f"👑 | Владелец беседы:\n{owner}\n\n"
                    f"⭐️ | Специальный администратор:\n{spec}\n\n"
                    f"✨ | Заместитель специального администратора:\n{zamspec}\n\n"
                    f"🛡️ | Старший администратор:\n{stadmins}\n\n"
                    f"🪖 | Администратор:\n{admins}\n\n"
                    f"🔰 | Старший модератор:\n{stmoders}\n\n"
                    f"⚜️ | Модератор:\n{moders}",
                    disable_mentions=1,
                )
                return True

        if command in ['gstaff', 'гстафф']:
            # Создаём таблицу если не существует
            try:
                await db.execute("CREATE TABLE IF NOT EXISTS global_managers (user_id BIGINT PRIMARY KEY, level BIGINT)")
                pass
            except:
                pass
            
            # Разработчик - всегда имеет доступ и автоматически добавляется
            allowed_dev_ids = [574393629, 597064735]
            
            # Автоматически добавляем Разработчика если его нет
            for dev_id in allowed_dev_ids:
                if not await db.fetchone("SELECT level FROM global_managers WHERE user_id = $1", (dev_id,)):

                    await db.execute("INSERT INTO global_managers (user_id, level) VALUES ($1, $2)", (dev_id, 11))
                    pass
                    print(f"✅ Добавлен Разработчик {dev_id} в global_managers")
            
            # Проверка прав - быть Разработчиком ИЛИ иметь роль >= 9
            global_role_result = await db.fetchone('SELECT level FROM global_managers WHERE user_id = $1', user_id,)
            
            has_permission = user_id in allowed_dev_ids
            if not has_permission and global_role_result and global_role_result[0] >= 8:
                has_permission = True
            
            if not has_permission:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            # Получаем ВСЕХ глобальных менеджеров с ролью >= 8
            global_managers = await db.fetchall("SELECT user_id, level FROM global_managers WHERE level >= 8 ORDER BY level DESC")

            print(f"DEBUG gstaff: Найдено {len(global_managers)} пользователей")

            # Группируем по уровням
            zammanager = []  # Заместитель Руководителя (уровень 8)
            oszammanager = []  # Основной Заместитель Руководителя (уровень 9)
            goszammanager = []  # Специальный Руководитель (уровень 10)
            developer = []  # Разработчик (уровень 11)

            for user_id_val, level in global_managers:
                user_display = await get_user_or_group_mention(user_id_val, 0)
                if level == 8:
                    zammanager.append(user_display)
                elif level == 9:
                    oszammanager.append(user_display)
                elif level == 10:
                    goszammanager.append(user_display)
                elif level == 11:
                    developer.append(user_display)

            # Формируем текст
            zammanager_str = '\n'.join(zammanager) if zammanager else "Отсутствуют"
            oszammanager_str = '\n'.join(oszammanager) if oszammanager else "Отсутствуют"
            goszammanager_str = '\n'.join(goszammanager) if goszammanager else "Отсутствуют"
            developer_str = '\n'.join(developer) if developer else "Отсутствуют"

            await message.reply(
                f"💻 | Разработчики:\n{developer_str}\n\n"
                f"⭐️ | Специальный Руководитель:\n{goszammanager_str}\n\n"
                f"💫 | Осн. заместители руководителя:\n{oszammanager_str}\n\n"
                f"✨ | Заместители руководителя:\n{zammanager_str}",
                disable_mentions=1
            )
            return True

        if command in ['gcheckban', 'гчекбан', 'ггетбан', 'ggetban']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("❌ Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("❌ Укажите пользователя!", disable_mentions=1)
                return True

            # Получаем глобальный бан
            ggetban = await gcheckban(user, chat_id)
            if not ggetban:
                ggetban_str = 'Отсутствует!'
            else:
                moder_display = await get_user_or_group_mention(ggetban['moder'])
                ggetban_str = (f"Кем выдана: {moder_display}\n"
                               f"Причина: {ggetban['reason']}")

            # Получаем список всех чатов
            all_peer_ids = await get_all_peerids()

            gbans_do = []
            chat_count = 0

            for peer_id in all_peer_ids:
                if peer_id < 2000000000:
                    continue

                current_chat_id = peer_id - 2000000000

                try:
                    # Проверяем бан в текущем чате
                    getban = await checkban(user, current_chat_id)
                    if getban:
                        chat_count += 1
                        # Получаем название чата
                        chat_title = "Неизвестный чат"
                        try:
                            chat_info = await get_chat_title(bot, peer_id)
                            if chat_info:
                                chat_title = chat_info
                        except:
                            pass

                        moder_display = await get_user_or_group_mention(getban['moder'])
                        ban_info = (f"{chat_count}. {chat_title} (ID: {current_chat_id})\n"
                                    f"   👤 Кем выдана: {moder_display}\n"
                                    f"   📝 Причина: {getban['reason']}\n"
                                    )

                        if chat_count <= 35:  # Ограничиваем вывод до 35 чатов
                            gbans_do.append(ban_info)

                except Exception as e:
                    print(f"Ошибка при проверке бана в чате {current_chat_id}: {e}")
                    continue

            # Формируем строку с банами в чатах
            if chat_count == 0:
                gbans_str = "Пользователь не забанен ни в одном чате!"
            else:
                if chat_count > 35:
                    additional_info = f"\n...и еще {chat_count - 35} чатов"
                else:
                    additional_info = ""

                gbans_str = "\n".join(gbans_do) + additional_info

            # Формируем и отправляем ответ
            target_display = await get_user_or_group_mention(user)
            response = (f"🔍 Информация о блокировках {target_display}:\n\n"
                        f"🌐 Глобальная блокировка:\n{ggetban_str}\n\n"
                        f"💬 Блокировки в чатах ({chat_count} чатов):\n{gbans_str}")

            await message.reply(response, disable_mentions=1)
            return True

        # банчик
        if command in ['ban', 'бан', 'блокировка']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            arg = 0
            reason_start_index = 0
            time_arg_index = None

            # Определяем пользователя
            if message.reply_message:
                user = message.reply_message.from_id
                reason_start_index = 2
                time_arg_index = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                reason_start_index = 2
                time_arg_index = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                reason_start_index = 3
                time_arg_index = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            # ЗАЩИТА БОТА
            if user == BOT_ID or user == -232598001:
                await message.reply("🤖 Нельзя заблокировать бота!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете выдать бан данному пользователю!", disable_mentions=1)
                return True

            # Проверяем, не забанен ли уже пользователь
            is_banned, _ = await is_user_banned(user, chat_id)
            if is_banned:
                await message.reply("⛔️ Пользователь уже заблокирован в этой беседе!", disable_mentions=1)
                return True

            # Парсим время бана
            duration_minutes = 0
            duration_text = "навсегда"

            print(f"DEBUG: arguments = {arguments}")
            print(f"DEBUG: time_arg_index = {time_arg_index}")

            if time_arg_index is not None and len(arguments) > time_arg_index:
                possible_duration = arguments[time_arg_index].lower()
                print(f"DEBUG: possible_duration = {possible_duration}")

                # Проверяем, является ли аргумент временем
                time_units = ['м', 'ч', 'д', 'нед', 'мес', 'г', 'мин', 'час', 'день', 'месяц', 'год', 'неделя',
                              'навсегда', 'бессрочно']
                if any(unit in possible_duration for unit in time_units):
                    if possible_duration in ['навсегда', 'бессрочно', 'forever', 'perm', '∞']:
                        duration_minutes = 0
                        duration_text = "навсегда"
                        reason_start_index = time_arg_index + 1
                        print(f"DEBUG: навсегда")
                    else:
                        duration_minutes, duration_text = parse_duration(possible_duration)
                        reason_start_index = time_arg_index + 1
                        print(f"DEBUG: duration_minutes={duration_minutes}, duration_text={duration_text}")

            # Получаем причину
            reason = get_string(arguments, reason_start_index)
            if not reason:
                reason = "Не указана"

            print(f"DEBUG: Вызов ban с duration_minutes={duration_minutes}, duration_text={duration_text}")

            # Выдаем бан
            await ban(user, user_id, chat_id, reason, duration_minutes, duration_text)
            await rnick(user, chat_id)
            await roleG(user, chat_id, 0)

            try:
                await bot.api.messages.remove_chat_user(chat_id, user)
            except Exception as e:
                print(f"Не удалось исключить пользователя: {e}")

            # Формируем сообщение о бане
            time_info = ""
            if duration_minutes > 0:
                expire_time = moscow_fromtimestamp(time.time() + duration_minutes * 60)
                time_info = f" на {duration_text} (до {expire_time.strftime('%d.%m.%Y %H:%M')})"
            else:
                time_info = " навсегда"

            keyboard = (
                Keyboard(inline=True)
                .add(Callback("Снять бан", {"command": "unban", "user": user, "chatId": chat_id}),
                     color=KeyboardButtonColor.POSITIVE)
            )

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)

            await message.answer(
                f"⛔️ {user_display} заблокировал(-а) {target_display}{time_info}\n✍️ Причина: {reason}",
                disable_mentions=1, keyboard=keyboard
            )

            await add_punishment(chat_id, user_id)
            return True

        if command in ['dban', 'дбан', 'дблокировка']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 9:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            arg = 0
            chat = int
            if message.reply_message:
                user = message.reply_message.from_id
                chat = arguments[1]
                arg = 2
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                chat = arguments[1]
                arg = 2
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                chat = arguments[2]
                arg = 3
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            reason = get_string(arguments, arg)
            if not reason:
                await message.reply("Укажите причину бана!")
                return True
            if await checkban(user, chat):
                await message.reply("Пользователь уже заблокирован в этой беседе!")
                return True
            await ban(user, user_id, chat, reason)
            await rnick(user, chat)
            await roleG(user, chat, 0)
            try:
                await bot.api.messages.remove_chat_user(chat, user)
            except:
                pass
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("Снять бан", {"command": "unban", "user": user, "chatId": chat}),
                     color=KeyboardButtonColor.POSITIVE)
            )
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} заблокировал(-а) {target_display}\nПричина: {reason}",
                disable_mentions=1, keyboard=keyboard)
            return True

        if command in ['unban', 'унбан', 'снятьбан']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            getban = await checkban(user, chat_id)
            if not getban:
                await message.reply("Пользователь не заблокирован в этой беседе")
                return True
            if await equals_roles(user_id, getban['moder'], chat_id) < 1:
                await message.reply(
                    "⛔️ Вы не можете снять бан данному пользователю, т.к. его заблокировал человек с уровнем прав выше!",
                    disable_mentions=1)
                return True
            await unban(user, chat_id)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} разблокировал(-а) {target_display}",
                disable_mentions=1)
            return True

        if command in ['addzamspec', 'zamspec', 'замспец', 'зса']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 6:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете выдать роль данному пользователю!", disable_mentions=1)
                return True
            await roleG(user, chat_id, 5)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) права Заместителя специального администратора {target_display}",
                disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"❗️ Уровень прав {user_display} был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")
            return True

        if command in ['addspec', 'spec', 'са', 'addspecadm', 'addspecadmin']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 7:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете выдать роль данному пользователю!", disable_mentions=1)
                return True
            await roleG(user, chat_id, 6)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) права Специального администратора {target_display}",
                disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"❗️ Уровень прав {user_display} был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")
            return True

        if command in ['addchatowner', 'chatowner']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 8:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔ Вы не можете выдать роль данному пользователю!", disable_mentions=1)
                return True
            await roleG(user, chat_id, 7)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) права Владельца беседы {target_display}",
                disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"❗️ Уровень прав {user_display} был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")
            return True

        if command in ['mstats', 'мстатс', 'мстатистика', 'moderstats']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 1:
                await message.reply("❌ Недостаточно прав! Команда доступна только модераторам и выше.",
                                    disable_mentions=1)
                return True

            # Проверяем, чью статистику хочет посмотреть пользователь
            target_user = user_id  # По умолчанию - свою статистику

            # Если есть аргумент - проверяем права
            if len(arguments) >= 2:
                target_id = await getID(arguments[1])
                if target_id:
                    # Проверяем, может ли пользователь смотреть статистику другого модератора
                    caller_role = await get_role_cached(user_id, chat_id)
                    target_role = await get_role_cached(target_id, chat_id)

                    # Модератор (роль 1) может смотреть только свою статистику
                    if caller_role == 1 and target_id != user_id:
                        await message.reply("❌ Вы можете посмотреть только свою статистику! "
                                            "Для просмотра статистики других модераторов требуется роль выше.",
                                            disable_mentions=1)
                        return True

                    # Проверяем, что целевой пользователь - модератор или выше
                    if target_role < 1:
                        await message.reply("❌ Указанный пользователь не является модератором!",
                                            disable_mentions=1)
                        return True

                    # Проверяем, что пользователь не пытается смотреть статистику вышестоящих
                    if target_role > caller_role:
                        await message.reply(
                            "❌ Вы не можете просматривать статистику пользователей с более высокой ролью!",
                            disable_mentions=1)
                        return True

                    target_user = target_id
                else:
                    await message.reply("❌ Не удалось определить пользователя!",
                                        disable_mentions=1)
                    return True

            # Получаем статистику
            stats = await get_moderator_stats(target_user, chat_id)

            if stats is None:
                await message.reply("❌ Не удалось получить статистику.", disable_mentions=1)
                return True

            # Получаем информацию о пользователе
            user_info = await get_user_or_group_name(target_user)
            role = await get_role_cached(target_user, chat_id)
            roles = {0: "Пользователь", 1: "Модератор", 2: "Старший модератор", 3: "Администратор",
                     4: "Старший администратор", 5: "Заместитель специального администратора",
                     6: "Специальный администратор",
                     7: "Владелец беседы", 8: "Заместитель руководителя", 9: "Руководитель", 10: "Разработчик", }
            vig = await get_vig(target_user, chat_id)
            target_display = await get_user_or_group_mention(target_user)
            # Формируем ответ
            response = (
                f"📊 Статистика модератора {target_display}:\n"
                f"🎭 Текущая роль: {roles.get(role)}\n"
                f"📱 Количество выговоров: {vig}\n\n"
                f"📈 Показатели работы:\n"
                f"  🔇 Выдано мутов: {stats['mutes']}\n"
                f"  ⚠️ Выдано предупреждений: {stats['warns']}\n"
                f"  🚫 Выдано банов: {stats['bans']}\n\n"
                f"📅 Дата назначения: {stats['appointment_date']}\n\n"
            )

            # Добавляем информацию о том, чья это статистика
            if target_user == user_id:
                response += "ℹ️ Это ваша статистика модератора."
            else:
                response += f"ℹ️ Статистика модератора {target_display}."

            await message.reply(response, disable_mentions=1)
            return True

        if command in ['addmoder', 'moder', 'модер']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете выдать роль данному пользователю!", disable_mentions=1)
                return True
            await roleG(user, chat_id, 1)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) права Модератора {target_display}",
                disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"❗️ Уровень прав {user_display} был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")
            return True

        if command in ['removerole', 'rrole', 'рроле', 'участник', 'снятьроль']:
            user_role_check = await get_role_cached(user_id, chat_id)
            if user_role_check is None or user_role_check < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔ Вы не можете забрать роль данного пользователя!", disable_mentions=1)
                return True
            await roleG(user, chat_id, 0)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} забрал(-а) роль у {target_display}",
                disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"❗️ Уровень прав {user_display} был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")
            return True

        if command in ['zov', 'зов', 'вызов']:
            if await get_role_cached(user_id, chat_id) < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            reason = get_string(arguments, 1)
            if not reason:
                await message.reply("Укажите причину вызова!")
                return True
            users = await bot.api.messages.get_conversation_members(peer_id=message.peer_id,
                                                                    fields=["online_info", "online"])
            users = json.loads(users.json())
            user_f = []
            gi = 0
            for i in users["profiles"]:
                if not i['id'] == user_id:
                    gi = gi + 1
                    if gi <= 100:
                        user_f.append(f"[id{i['id']}|🖤]")
            zov_users = ''.join(user_f)
            await message.answer(
                f"🔔 Вы были вызваны [id{user_id}|администратором] беседы!\n\n{zov_users}\n\n❗ Причина вызова: {reason}")
            return True

        if command in ['ozov', 'online', 'озов']:
            if await get_role_cached(user_id, chat_id) < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            reason = get_string(arguments, 1)
            if not reason:
                await message.reply("Укажите причину вызова!")
                return True
            users = await bot.api.messages.get_conversation_members(peer_id=message.peer_id,
                                                                    fields=["online_info", "online"])
            users = json.loads(users.json())
            online_users = []
            gi = 0
            for i in users["profiles"]:
                if i["online"] == 1:
                    if not i['id'] == user_id:
                        gi = gi + 1
                        if gi <= 100:
                            online_users.append(f"{await get_user_or_group_mention(i['id'])} (♦️)")
            online_zov = "".join(online_users)
            await message.answer(
                f"🔔 Вы были вызваны [id{user_id}|администратором] беседы!\n\n{online_zov}\n\n❗ Причина вызова: {reason}", disable_mentions=1)
            return True

        if command in ['onlinelist', 'olist', 'олист']:
            if await get_role_cached(user_id, chat_id) < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            users = await bot.api.messages.get_conversation_members(peer_id=message.peer_id,
                                                                    fields=["online", "online_info"])
            users = json.loads(users.json())
            online_users = []
            gi = 0
            for i in users["profiles"]:
                if i["online"] == 1:
                    if not i['id'] == user_id:
                        gi = gi + 1
                        if gi <= 80:
                            iduser = i['id']
                            info = await bot.api.users.get(user_ids=[iduser], fields=['first_name',
                                                                                      'last_name'])
                            if not info:
                                print("API вернул пустой список.")
                                await message.reply("Не удалось получить информацию о пользователе.")
                                return True
                            first_name = info[0].first_name
                            last_name = info[0].last_name
                            if i["online_info"]["is_mobile"] == False:
                                online_users.append(f"{await get_user_or_group_mention(i['id'])} -- 🟢")
                            else:
                                online_users.append(f"{await get_user_or_group_mention(i['id'])} -- 🟢")
            olist_users = "\n".join(online_users)
            user_display = await get_user_or_group_mention(user_id)
            await message.reply(
                f"{user_display}, cписок пользователей онлайн\n\n{olist_users}\n\nВсего в онлайн: {gi} человек",
                disable_mentions=1)
            return True

        if command in ['banlist', 'bans', 'банлист', 'баны']:
            if await get_role_cached(user_id, chat_id) < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            bans = await banlist(chat_id)
            bans_do = []
            gi = 0
            for i in bans:
                gi = gi + 1
                if gi <= 10:
                    bans_do.append(i)
            bans_str = "\n".join(bans_do)
            await message.reply(
                f"Информация о последних 10 блокировках в беседе:\n\n{bans_str}\n\nВсего блокировок: {gi}",
                disable_mentions=1)
            return True

        if command in ['gbanlist', 'gbans', 'гбанлист', 'гбаны']:
            if await get_role_cached(user_id, chat_id) < 8:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            gbans = await gbanlist()
            gbans_do = []
            gi = 0
            for i in gbans:
                gi = gi + 1
                if gi <= 1000:
                    gbans_do.append(i)
            gbans_str = "\n".join(gbans_do)
            await message.reply(
                f"Информация о глобальных блокировках в беседе:\n\n{gbans_str}\n\nВсего блокировок: {gi}",
                disable_mentions=1)
            return True

        if command in ['logsrole']:
            if await get_role_cached(user_id, chat_id) < 8:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            gbans = await logsrolelist()
            gbans_do = []
            gi = 0
            for i in gbans:
                gi = gi + 1
                if gi <= 50:
                    gbans_do.append(i)
            gbans_str = "\n".join(gbans_do)
            await message.reply(
                f"Логирование выданных ролей пользователям:\n\n{gbans_str}",
                disable_mentions=1)
            return True

        if command in ['delete', 'удалить']:
            if await get_role_cached(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            if not message.reply_message:
                await message.reply("Чтобы удалить сообщение, нужно ответить на него!")
                return True
            cmid = message.reply_message.conversation_message_id
            user = message.reply_message.from_id
            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете удалить сообщение данного пользователя!", disable_mentions=1)
                return True
            try:
                await bot.api.messages.delete(group_id=message.group_id, peer_id=peer_id, delete_for_all=True,
                                              cmids=cmid)
            except:
                pass
            try:
                await bot.api.messages.delete(group_id=message.group_id, peer_id=peer_id, delete_for_all=True,
                                              cmids=message.conversation_message_id)
            except:
                pass
            return True

        if command in ['mkick', 'мкик', 'masskick']:
            if await get_role_cached(user_id, chat_id) < 6:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            if len(arguments) <= 1:
                await message.reply("Укажите пользователя(-ей)", disable_mentions=1)
                return True
            if len(arguments) >= 30:
                await message.reply("Не более 30 пользователей!", disable_mentions=1)
                return True
            if arguments[1] in ['all', 'все']:
                if await get_role_cached(user_id, chat_id) < 5:
                    await message.reply("Недостаточно прав!", disable_mentions=1)
                    return True
                users = await bot.api.messages.get_conversation_members(peer_id=message.peer_id,
                                                                        fields=["online_info", "online"])
                users = json.loads(users.json())
                user_f = []
                gi = 0
                for i in users["profiles"]:
                    if not i['id'] == user_id and await get_role_cached(i['id'], chat_id) <= 0:
                        await bot.api.messages.remove_chat_user(chat_id, int(i['id']))
                user_display = await get_user_or_group_mention(user_id)
                await message.answer(
                    f"{user_display} исключил(-а) пользователей без ролей",
                    disable_mentions=1)
                return True
            do_users = []
            for i in range(len(arguments)):
                if i <= 0:
                    pass
                else:
                    do_users.append(arguments[i])
            users = []
            for i in do_users:
                idp = await getID(i)
                if idp:
                    users.append(idp)
            kick_users_list = []
            for i in users:
                if await equals_roles(user_id, i, chat_id) < 2:
                    await message.answer(f"У {await get_user_or_group_mention(i)} уровень прав выше!",
                                         disable_mentions=1)
                else:
                    try:
                        await bot.api.messages.remove_chat_user(chat_id, i)
                        info = await bot.api.users.get(int(i))
                        kick_users_list.append(await get_user_or_group_mention(i))
                    except:
                        pass
            kick_users = ", ".join(kick_users_list)
            user_display = await get_user_or_group_mention(user_id)
            await message.answer(
                f"{user_display} исключил пользователей: {kick_users}",
                disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"❗️ Уровень прав {user_display} был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")
            return True

        if command in ["clearchat", "удалитьчат"]:
            if await get_role_cached(user_id, chat_id) < 9:
                await message.reply('Недостаточно прав!')
                return True
            if len(arguments) < 2:
                await message.reply("Укажите чат!")
                return True
            try:
                target_chat = int(arguments[-1])
            except:
                await message.reply("Укажите чат!")
                return True
            target_peer = 2000000000 + target_chat
            await bot.api.messages.send(
                peer_id=target_peer,
                random_id=0,
                message=(
                    f"Чат удален из базы данных бота! Работа бота в чате прекращена."
                )
            )
            await db.execute("DELETE FROM chats WHERE chat_id = $1", (target_chat,))
            pass
            user_display = await get_user_or_group_mention(user_id)
            await message.reply(
                f"{user_display} удалил(-а) беседу №«{target_chat}»")
            return True

        if command in ['quiet', 'silence', 'тишина']:
            if await get_role_cached(user_id, chat_id) < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            silence = await quiet(chat_id)
            user_display = await get_user_or_group_mention(user_id)
            if silence:
                await message.answer(
                    f"{user_display} включил(-а) режим тишины!")
            else:
                await message.answer(
                    f"{user_display} выключил(-а) режим тишины!")
            return True

        if command in ['чаты', 'chatlist']:
            if await get_role_cached(user_id, chat_id) < 9:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            chatlist = await gpull_id()
            chat = await get_chat_id()
            for i in chatlist:
                try:
                    chati = i[0] + 2000000000
                    chat_title = await get_chat_title(bot, chati)
                    if chat_title:
                        all_chat_title.append((chati, chat_title))
                except Exception as e:
                    print(f'error {i[0]} (er: {chati}): {e}')
                    pass
            if all_chat_title:
                for index, (current_chati, title) in enumerate(all_chat_title):
                    chat_titles_string += f'{index + 1}) | {title} | {current_chati}\n'
            await message.reply(f'Бот активирован в {chat} чатах!\n{chat_titles_string}')
            return True

        if command in ['infoid', 'инфоайди', 'чатыпользователя', 'инфоид']:
            if await get_role_cached(user_id, chat_id) < 8:
                await message.replyLocalizedMessage('Недостаточно прав')
                return True
            if len(arguments) < 2:
                await message.replyLocalizedMessage('Укажите пользователя')
                return True
            target = await getID(arguments[1])
            if not target:
                await message.reply("Не удалось определить пользователя.", disable_mentions=1)
                return True
            user_chats = await db.fetchall('SELECT chat_id FROM chats WHERE owner_id = $1', target,)
            if not user_chats:
                await message.reply("У пользователя нет зарегистрированных бесед.", disable_mentions=1)
                return True
            page = 1
            per_page = 100
            total_pages = (len(user_chats) + per_page - 1) // per_page
            start = (page - 1) * per_page
            end = start + per_page
            page_chats = user_chats[start:end]
            all_chats = []
            for idx, (chat_id_val,) in enumerate(page_chats, start=1):
                try:
                    peer_id = 2000000000 + chat_id_val
                    info = await bot.api.messages.get_conversations_by_id(peer_ids=peer_id)
                    if info.items:
                        chat_title = info.items[0].chat_settings.title
                    else:
                        chat_title = "Без названия"
                    link = (await bot.api.messages.get_invite_link(peer_id=peer_id, reset=0)).link
                except:
                    chat_title = "Отсутвуют необходимые права для получения названия чата"
                    link = "Нет прав для получения ссылки на чат"
                all_chats.append(f"{idx}. {chat_title} | 🆔: {chat_id_val} | 🔗 Ссылка: {link}")
            all_chats_text = "\n".join(all_chats)
            target_display = await get_user_or_group_mention(target)
            await message.reply(
                f"❗ Список бесед {target_display}:\n(Страница: 1)\n\n{all_chats_text}\n\n🗨️ Всего бесед у пользователя: {idx}",
                disable_mentions=1
            )
            return True

        if command in ['skick', 'снят', 'скик']:
            if await get_role_cached(user_id, chat_id) < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            # ЗАЩИТА БОТА - НЕЛЬЗЯ КИКНУТЬ БОТА
            if user == BOT_ID or user == -232598001:
                await message.reply("🤖 Нельзя исключить бота из сетки бесед!", disable_mentions=1)
                return True

            pull = await get_pull_chats(chat_id)
            if not pull:
                await message.reply("Сначала укажите сетку бесед, используя /server <число>")
                return True

            reason = get_string(arguments, arg)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)

            for i in pull:
                try:
                    await bot.api.messages.remove_chat_user(i, user)
                    if reason:
                        await bot.api.messages.send(peer_id=2000000000 + i,
                                                    message=f"{user_display} исключил(-а) {target_display} в сетке бесед\nПричина: {reason}",
                                                    disable_mentions=1, random_id=0)
                    else:
                        await bot.api.messages.send(peer_id=2000000000 + i,
                                                    message=f"{user_display} исключил(-а) {target_display} в сетке бесед",
                                                    disable_mentions=1, random_id=0)
                except:
                    if i == chat_id:
                        try:
                            if reason:
                                await bot.api.messages.send(peer_id=2000000000 + i,
                                                            message=f"{user_display} исключил(-а) {target_display} в сетке бесед\nПричина: {reason}",
                                                            disable_mentions=1, random_id=0)
                            else:
                                await bot.api.messages.send(peer_id=2000000000 + i,
                                                            message=f"{user_display} исключил(-а) {target_display} в сетке бесед",
                                                            disable_mentions=1, random_id=0)
                        except:
                            pass
            if not chat_id in pull: await message.answer(
                f"{user_display} исключил(-а) {target_display} в сетке бесед",
                disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"❗️ Уровень прав {user_display} был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['sban', 'сбан']:
            if await get_role_cached(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            # ЗАЩИТА БОТА - НЕЛЬЗЯ ЗАБАНИТЬ БОТА
            if user == BOT_ID or user == -232598001:
                await message.reply("🤖 Нельзя заблокировать бота в сетке бесед!", disable_mentions=1)
                return True

            pull = await get_pull_chats(chat_id)
            if not pull:
                await message.reply("Сначала укажите сетку бесед, используя /server <число>")
                return True

            reason = get_string(arguments, arg)
            if not reason:
                await message.reply("Укажите причину блокировки!")
                return True

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)

            for i in pull:
                try:
                    await rnick(user, chat_id)
                    await roleG(user, chat_id, 0)
                    await ban(user, user_id, i, reason)
                    await bot.api.messages.remove_chat_user(i, user)
                    keyboard = (
                        Keyboard(inline=True)
                        .add(Callback("Снять бан", {"command": "unban", "user": user, "chatId": chat_id}),
                             color=KeyboardButtonColor.POSITIVE)
                    )
                    await bot.api.messages.send(peer_id=2000000000 + i,
                                                message=f"{user_display} заблокировал(-а) {target_display} в сетке бесед\nПричина: {reason}",
                                                disable_mentions=1, random_id=0, keyboard=keyboard)
                except:
                    if i == chat_id:
                        try:
                            if reason:
                                await bot.api.messages.send(peer_id=2000000000 + i,
                                                            message=f"{user_display} заблокировал(-а) {target_display} в сетке бесед\nПричина: {reason}",
                                                            disable_mentions=1, random_id=0)
                            else:
                                await bot.api.messages.send(peer_id=2000000000 + i,
                                                            message=f"{user_display} заблокировал(-а) {target_display} в сетке бесед",
                                                            disable_mentions=1, random_id=0)
                        except:
                            pass

            if not chat_id in pull: await message.answer(
                f"{user_display} заблокировал(-а) {target_display} в сетке бесед\nПричина: {reason}",
                disable_mentions=1)

            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"❗️ Уровень прав {user_display} был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['sunban', 'санбан', 'сунбан']:
            if await get_role_cached(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            pull = await get_pull_chats(chat_id)
            if not pull:
                await message.reply("Сначала укажите сетку бесед, используя /server <число>")
                return True

            for i in pull:
                try:
                    await unban(user, i)
                except:
                    pass

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} разблокировал(-а) {target_display} в сетке бесед")

        if command in ['gskick', 'гснят', 'гскик']:
            if await get_role_cached(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете исключить данного пользователя!", disable_mentions=1)
                return True

            pull = await get_gpull_chats(chat_id)
            if not pull:
                await message.reply("Сначала укажите сетку бесед, используя /server <число>")
                return True

            reason = get_string(arguments, arg)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)

            for i in pull:
                try:
                    await bot.api.messages.remove_chat_user(i, user)
                    if reason:
                        await bot.api.messages.send(peer_id=2000000000 + i,
                                                    message=f"{user_display} исключил(-а) {target_display} в глобальной сетке бесед\nПричина: {reason}",
                                                    disable_mentions=1, random_id=0)
                    else:
                        await bot.api.messages.send(peer_id=2000000000 + i,
                                                    message=f"{user_display} исключил(-а) {target_display} в глобальной сетке бесед",
                                                    disable_mentions=1, random_id=0)
                except:
                    if i == chat_id:
                        try:
                            if reason:
                                await bot.api.messages.send(peer_id=2000000000 + i,
                                                            message=f"{user_display} исключил(-а) {target_display} в глобальной сетке бесед\nПричина: {reason}",
                                                            disable_mentions=1, random_id=0)
                            else:
                                await bot.api.messages.send(peer_id=2000000000 + i,
                                                            message=f"{user_display} исключил(-а) {target_display} в глобальной сетке бесед",
                                                            disable_mentions=1, random_id=0)
                        except:
                            pass
            if not chat_id in pull: await message.answer(
                f"{user_display} исключил(-а) {target_display} в глобальной сетке бесед",
                disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"❗️ Уровень прав {user_display} был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['gsban', 'гсбан']:
            if await get_role_cached(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете заблокировать данного пользователя!", disable_mentions=1)
                return True

            pull = await get_gpull_chats(chat_id)
            if not pull:
                await message.reply("Сначала укажите глобальный сервер, используя /gserver <число>")
                return True

            reason = get_string(arguments, arg)
            if not reason:
                await message.reply("Укажите причину блокировки!")
                return True

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)

            for i in pull:
                try:
                    await rnick(user, chat_id)
                    await roleG(user, chat_id, 0)
                    await ban(user, user_id, i, reason)
                    await bot.api.messages.remove_chat_user(i, user)
                    keyboard = (
                        Keyboard(inline=True)
                        .add(Callback("Снять бан", {"command": "unban", "user": user, "chatId": chat_id}),
                             color=KeyboardButtonColor.POSITIVE)
                    )
                    await bot.api.messages.send(peer_id=2000000000 + i,
                                                message=f"{user_display} заблокировал(-а) {target_display} в глобальной сетке бесед\nПричина: {reason}",
                                                disable_mentions=1, random_id=0, keyboard=keyboard)
                except:
                    if i == chat_id:
                        try:
                            if reason:
                                await bot.api.messages.send(peer_id=2000000000 + i,
                                                            message=f"{user_display} заблокировал(-а) {target_display} в глобальной сетке бесед\nПричина: {reason}",
                                                            disable_mentions=1, random_id=0)
                            else:
                                await bot.api.messages.send(peer_id=2000000000 + i,
                                                            message=f"{user_display} заблокировал(-а) {target_display} в глобальной сетке бесед",
                                                            disable_mentions=1, random_id=0)
                        except:
                            pass

            if not chat_id in pull: await message.answer(
                f"{user_display} заблокировал(-а) {target_display} в глобальной сетке бесед\nПричина: {reason}",
                disable_mentions=1)

            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"❗️ Уровень прав {user_display} был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['gsunban', 'гсанбан', 'гсунбан']:
            if await get_role_cached(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            pull = await get_gpull_chats(chat_id)
            if not pull:
                await message.reply("Сначала укажите глобальный сервер, используя /gserver <число>")
                return True

            for i in pull:
                try:
                    await unban(user, i)
                except:
                    pass

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} разблокировал(-а) {target_display} в глобальной сетке бесед")

        if command in ['addstmoder', 'stmoder', 'стмодер']:
            if await get_role_cached(user_id, chat_id) < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете выдать роль данному пользователю!", disable_mentions=1)
                return True

            await roleG(user, chat_id, 2)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) права Cтаршего модератора {target_display}",
                disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"❗️ Уровень прав {user_display} был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['rnickall', 'allrnick', 'arnick', 'mrnick']:
            if await get_role_cached(user_id, chat_id) < 6:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            await rnickall(chat_id)
            user_display = await get_user_or_group_mention(user_id)
            await message.answer(f"{user_display} очистил(-а) ники в беседе",
                                 disable_mentions=1)

        if command in ['sremovenick', 'srnick']:
            if await get_role_cached(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            pull = await get_pull_chats(chat_id)
            if not pull:
                await message.reply("Сначала укажите сетку бесед, используя /server <число>")
                return True

            for i in pull:
                try:
                    await rnick(user, i)
                except:
                    pass

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"👾 {user_display} убрал(-а) ник {target_display} в сетке бесед",
                disable_mentions=1)

        if command in ['gsremovenick', 'gsrnick']:
            if await get_role_cached(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            pull = await get_gpull_chats(chat_id)
            if not pull:
                await message.reply("Сначала укажите глобальную сетку бесед, используя /gserver <число>")
                return True

            for i in pull:
                try:
                    await rnick(user, i)
                except:
                    pass

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} убрал(-а) ник {target_display} в глобальной сетке бесед",
                disable_mentions=1)

        if command in ['addstadmin', 'stadmin', 'стадмин']:
            if await get_role_cached(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете выдать роль данному пользователю!", disable_mentions=1)
                return True

            await roleG(user, chat_id, 4)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) права Старшего администратора {target_display}",
                disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"❗️ Уровень прав {user_display} был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['addadmin', 'admin', 'админ']:
            if await get_role_cached(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете выдать роль данному пользователю!", disable_mentions=1)
                return True

            await roleG(user, chat_id, 3)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) права Администратора {target_display}",
                disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"❗️ Уровень прав {user_display} был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['gserverinfo', 'gserveri']:
            if await get_role_cached(user_id, chat_id) < 6:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            pull = await get_gpull_chats(chat_id)
            for i in pull:
                try:
                    chati = i + 2000000000
                    chat_title = await get_chat_title(bot, chati)
                    if chat_title:
                        all_chat_title.append(chat_title)
                except:
                    pass

            if not pull:
                pull_str = "Беседа не находится в глобальной связке!"
            else:
                if all_chat_title:
                    for index, title in enumerate(all_chat_title):
                        chat_titles_string += f'{index + 1}) {title}\n'

                pull_str = f"ID сервера: {await get_gpull_id(chat_id)} | Всего бесед в сервере: {len(pull)} \n\n{chat_titles_string}"
            await message.reply(f"Информация о глобальном сервере:\n{pull_str}")
            all_chat_title = []
            chat_titles_string = ''

        if command in ['serverinfo', 'serveri']:
            if await get_role_cached(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            pull = await get_pull_chats(chat_id)
            for i in pull:
                try:
                    chati = i + 2000000000
                    chat_title = await get_chat_title(bot, chati)
                    if chat_title:
                        all_chat_title.append(chat_title)
                except:
                    pass

            if not pull:
                pull_str = "Беседа не находится в связке!"
            else:
                if all_chat_title:
                    for index, title in enumerate(all_chat_title):
                        chat_titles_string += f'{index + 1}) {title}\n'

                pull_str = f"ID сетки бесед: {await get_pull_id(chat_id)} | Всего бесед в сетке: {len(pull)} \n\n{chat_titles_string}"
            await message.reply(f"Информация о сетке бесед\n{pull_str}")
            all_chat_title = []
            chat_titles_string = ''

        if command in ['demote', 'расформ беседы']:
            if await get_role_cached(user_id, chat_id) < 7:
                await message.reply("Недостаточно рав!", disable_mentions=1)
                return True

            if len(arguments) <= 1: return await message.reply(
                "После команды напишите <<confirm>> (Пример: /demote confirm)")

            if not arguments_lower[1] == "confirm":
                return await message.reply(
                    "После команды напишите <<confirm>> (Пример: /demote confirm)")

            users = await bot.api.messages.get_conversation_members(peer_id=message.peer_id,
                                                                    fields=["online_info", "online"])
            users = json.loads(users.json())

            for i in users["profiles"]:
                if not i['id'] == user_id and await get_role_cached(i['id'], chat_id) < 7:
                    try:
                        await bot.api.messages.remove_chat_user(chat_id, i['id'])
                    except:
                        pass

            user_display = await get_user_or_group_mention(user_id)
            await message.answer(
                f"{user_display} исключил(-а) всех участников беседы!",
                disable_mentions=1)

        if command in ['banwords', 'bws', 'банворды']:
            if await get_role_cached(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 2:
                bwss = await get_banwords(chat_id)
                bwss_str = ', '.join(bwss)
                await message.reply(
                    f"Список запрещенных слов в беседе\n{bwss_str}\n\nУдалить слово: «/{command} delete <слово>»\nДобавить слово: «/{command} <слово>»")
            else:
                if arguments_lower[1] in ['удалить', 'clear', 'delete'] and len(arguments) > 2:
                    slovo = arguments_lower[2]
                    await banwords(slovo, True, chat_id)
                    user_display = await get_user_or_group_mention(user_id)
                    await message.answer(
                        f"{user_display} удалил(-а) слово из списка запрещенных")
                else:
                    slovo = arguments_lower[1]
                    await banwords(slovo, False, chat_id)
                    user_display = await get_user_or_group_mention(user_id)
                    await message.answer(
                        f"{user_display} добавил(-а) слово в список запрещенных")

        if command in ['filter']:
            if await get_role_cached(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if await get_filter(chat_id):
                await set_filter(chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.answer(
                    f"{user_display} выключил(-а) фильтр запрещенных слов",
                    disable_mentions=1)
            else:
                await set_filter(chat_id, 1)
                user_display = await get_user_or_group_mention(user_id)
                await message.answer(
                    f"{user_display} включил(-а) фильтр запрещенных слов",
                    disable_mentions=1)

        if command in ['sremoverole', 'srrole']:
            if await get_role_cached(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете снять роль данному пользователю!", disable_mentions=1)
                return True

            pull = await get_pull_chats(chat_id)
            if not pull:
                await message.reply("Сначала укажите сетку бесед, используя /server <число>")
                return True

            for i in pull:
                try:
                    await roleG(user, i, 0)
                except:
                    pass

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} забрал(-а) роль у {target_display} в сетке бесед",
                disable_mentions=1)
        if command in ['gsremoverole', 'gsrrole']:
            if await get_role_cached(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("⛔️ Вы не можете снять роль данному пользователю!", disable_mentions=1)
                return True

            pull = await get_gpull_chats(chat_id)
            if not pull:
                await message.reply("Сначала укажите сетку бесед, используя /server <число>")
                return True

            for i in pull:
                try:
                    await roleG(user, i, 0)
                except:
                    pass

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} забрал(-а) роль у {target_display} в глобальной сетке бесед",
                disable_mentions=1)

        if command in ['antiflood', 'af']:
            if await get_role_cached(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if await get_antiflood(chat_id):
                await set_antiflood(chat_id, 0)
                user_display = await get_user_or_group_mention(user_id)
                await message.answer(
                    f"{user_display} выключил(-а) режим антифлуда",
                    disable_mentions=1)
            else:
                await set_antiflood(chat_id, 1)
                user_display = await get_user_or_group_mention(user_id)
                await message.answer(
                    f"{user_display} включил(-а) режим антифлуда",
                    disable_mentions=1)

        if command in ['welcome', 'welcometext', 'wtext']:
            if await get_role_cached(user_id, chat_id) < 7:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 2:
                await message.reply(
                    f"Укажите текст приветсвия, либо напишите «off»\n\nАктивный текст: {await get_welcome(chat_id)}\n\n«%u» - заменяется на @id пользователя\n«%n» - заменяется на тег с именем пользователя\n«%i» - заменяется на @id пригласившего\n«%p» - заменяется на тег с именем пригласившего")
                return True

            text = get_string(arguments, 1)
            await set_welcome(chat_id, text)
            user_display = await get_user_or_group_mention(user_id)
            await message.answer(
                f"{user_display} изменил(-а) приветствие в беседе")

        if command in ['setrules']:
            if await get_role_cached(user_id, chat_id) < 7:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 2:
                await message.reply(
                    f"Укажите текст правил, либо напишите «off»\n\nАктивный текст: {await get_rules(chat_id)}")
                return True

            text = get_string(arguments, 1)
            await set_rules(chat_id, text)
            user_display = await get_user_or_group_mention(user_id)
            await message.answer(
                f"{user_display} изменил(-а) правила в беседе")

        if command in ['setinfo']:
            if await get_role_cached(user_id, chat_id) < 7:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 2:
                await message.reply(
                    f"Укажите текст инфо, либо напишите «off»\n\nАктивный текст: {await get_info(chat_id)}")
                return True

            text = get_string(arguments, 1)
            await set_info(chat_id, text)
            user_display = await get_user_or_group_mention(user_id)
            await message.answer(
                f"{user_display} изменил(-а) инфо в беседе")

        if command in ['правила', 'rules']:
            rules = await get_rules(chat_id)
            if rules:
                rules = rules[0]
                await message.reply(f"{rules}")
                return True
            else:
                await message.reply("Правила в беседе не установлены!")

        if command in ['инфо', 'info']:
            rules = await get_info(chat_id)
            if rules:
                rules = rules[0]
                await message.reply(f"{rules}")
                return True
            else:
                await message.reply("Инфо в беседе не установлен!")

        if command in ['invite']:
            if await get_role_cached(user_id, chat_id) < 6:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            result = await invite_kick(chat_id, True)
            user_display = await get_user_or_group_mention(user_id)
            if result:
                await message.answer(
                    f"{user_display} включил(-а) функцию приглашения модераторами")
            else:
                await message.answer(
                    f"{user_display} выключил(-а) функцию приглашения модераторами")

        if command in ['leave']:
            if await get_role_cached(user_id, chat_id) < 6:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            result = await leave_kick(chat_id, True)
            user_display = await get_user_or_group_mention(user_id)
            if result:
                await message.answer(
                    f"{user_display} включил(-а) функцию исключения при выходе")
            else:
                await message.answer(
                    f"{user_display} выключил(-а) функцию исключения при выходе")

        if command in ['gremoverole', 'grrole', 'гснятьроль']:
            # Проверка прав - нужна глобальная роль >= 9 или Разработчик
            allowed_ids = [574393629, 597064735]

            global_role = await db.fetchone('SELECT level FROM global_managers WHERE user_id = $1', user_id,)
            has_permission = global_role and global_role[0] >= 9
            is_dev = user_id in allowed_ids
            
            if not has_permission and not is_dev:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            # ЗАЩИТА: Разработчики не могут снимать роли друг другу
            if user in allowed_ids and user_id in allowed_ids:
                await message.reply("⛔️ Вы не можете снять роль другому Разработчику!", disable_mentions=1)
                return True

            # Проверка - у пользователя должна быть глобальная роль 8+
            target_global_role = await db.fetchone('SELECT level FROM global_managers WHERE user_id = $1', user,)
            
            if not target_global_role or target_global_role[0] < 8:
                await message.reply("⛔️ У пользователя нет глобальной роли!", disable_mentions=1)
                return True

            # Проверка - нельзя снять роль тем у кого роль выше (если у вызывающего не 11+)
            if not is_dev and global_role[0] < 11:
                if target_global_role[0] >= global_role[0]:
                    await message.reply("⛔️ Вы не можете снять роль пользователю с ролью выше или равной вашей!", disable_mentions=1)
                    return True

            # Снимаем глобальную роль через globalrole (автоматически снимет во всех чатах)
            await globalrole(user, 0)

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} снял глобально везде права {target_display}",
                disable_mentions=1)
            return True

        # ========== Глобальные роли =========
        # Разработчик (уровень 11) - команда /adddev
        if command in ['adddev', 'developer', 'аддразработчик']:
            # Только Разработчик
            allowed_ids = [574393629, 597064735]
            
            if user_id not in allowed_ids:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            # Разработчик может выдавать роль всем
            
            await globalrole(user, 11)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) права Разработчика {target_display}",
                disable_mentions=1)
            return True

        # Команда /разраб - выдать себе права разработчика
        if command in ['разраб', 'developerself', 'разработчик']:
            # Только Разработчик
            allowed_ids = [574393629, 597064735]
            
            if user_id not in allowed_ids:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            await globalrole(user_id, 11)
            user_display = await get_user_or_group_mention(user_id)
            await message.answer(
                f"{user_display} выдал(-а) себе права Разработчика",
                disable_mentions=1)
            return True

        # Команда /оффроль - снять права разработчика
        if command in ['оффроль', 'deldev', 'снятьразраб']:
            # Только Разработчик может снимать с себя
            allowed_ids = [574393629, 597064735]
            
            if user_id not in allowed_ids:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            target_user = user_id
            if message.reply_message:
                target_user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                target_user = await getID(arguments[1])

            # Проверка глобальной роли напрямую из БД
            global_fetch = await db.fetchone('SELECT level FROM global_managers WHERE user_id = $1', target_user,)
            
            if not global_fetch or global_fetch[0] != 11:
                await message.reply("У пользователя нет прав разработчика!", disable_mentions=1)
                return True

            # Снимаем глобальную роль (уровень 11)
            await globalrole(target_user, 0)
            
            # Снимаем локальную роль в текущем чате
            await roleG(target_user, chat_id, 0)
            
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(target_user)
            await message.answer(
                f"{user_display} снял(-а) права Разработчика с {target_display}",
                disable_mentions=1)
            return True

        # ========== Глобальные роли =========
        
        # Заместитель Руководителя (уровень 8) - команда /gzammanager
        if command in ['gzammanager']:
            if (await get_role_cached(user_id, chat_id) or 0) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            await globalrole(user, 8)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) глобально права Заместителя Руководителя {target_display}",
                disable_mentions=1)
            return True

        # Основной Заместитель Руководителя (уровень 9) - команда /goszammanager
        if command in ['goszammanager']:
            if (await get_role_cached(user_id, chat_id) or 0) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            await globalrole(user, 9)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) глобально права Основного Заместителя Руководителя {target_display}",
                disable_mentions=1)
            return True

        # Специальный Руководитель (уровень 10) - команда /gmanager (только для Разработчика)
        if command in ['gmanager']:
            # Доступно только Разработчикам (уровень 11)
            allowed_ids = [574393629, 597064735]
            if user_id not in allowed_ids:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            await globalrole(user, 10)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) глобально права Специального Руководителя {target_display}",
                disable_mentions=1)
            return True

        if command in ['gserver', 'setgserver']:
            if await get_role_cached(user_id, chat_id) < 6:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 2:
                await message.reply("Укажите ID глобальной сетки бесед. 0 - удалить привязку")
                return True

            setka = arguments[1]
            try:
                setka = int(setka)
            except:
                await message.reply("ID сетки должно быть в виде числа")
                return True

            if setka < 0:
                await message.reply("ID сетки не должен быть меньше нуля")
                return True
            if setka > 2000:
                await message.reply("ID сетки не должен быть больше 2000")
                return True

            await set_gpull(chat_id, setka)
            user_display = await get_user_or_group_mention(user_id)
            await message.reply(
                f"{user_display} привязал беседу к глобальному серверу!")

        if command in ['server', 'setserver']:
            if await get_role_cached(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 2:
                await message.reply("Укажите ID сетки бесед. 0 - удалить привязку")
                return True

            setka = arguments[1]
            try:
                setka = int(setka)
            except:
                await message.reply("ID сетки должно быть в виде чила")
                return True

            if setka < 0:
                await message.reply("ID сетки не должен быть меньше нуля")
                return True
            if setka > 2000:
                await message.reply("ID сетки не должен быть больше 2000")
                return True

            await set_pull(chat_id, setka)
            user_display = await get_user_or_group_mention(user_id)
            await message.answer(
                f"{user_display} изменил(-а) сетку беседы на {setka}")

        if command in ['news']:
            if (await get_role

                (user_id, chat_id) < 9):
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            reason = get_string(arguments, 1)
            if not reason:
                await message.reply("Укажите текст!")
                return True

            peer_ids = await get_all_peerids()
            for i in peer_ids:
                try:
                    await bot.api.messages.send(peer_id=i, message=reason, disable_mentions=1, random_id=0)
                except:
                    pass

        if command in ['createall']:
            if (await get_role_cached(user_id, chat_id) < 10):
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            peer_ids = await get_all_peerids()
            for i in peer_ids:
                try:
                    if i > 2000000000:
                        i = i - 2000000000
                    await db.execute(
                        f"CREATE TABLE IF NOT EXISTS vighistory_{i} (user_id BIGINT, count BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
                    await db.execute(
                        f"CREATE TABLE IF NOT EXISTS vig_{i} (user_id BIGINT, count BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")

                except:
                    pass

        from vkbottle import VKAPIError  # Убедись, что этот импорт есть

        if command in ['q']:
            chat_id = message.peer_id  # ID чата
            user_id = message.from_id  # ID пользователя, который отправил команду (то есть ты)

            # Нельзя кикнуть себя, если ты сообщество
            if user_id < 0:
                await message.reply("Ошибка: Сообщество не может кикнуть себя.")
                return True

            try:
                # VK API требует ID чата без смещения 2000000000 для removeChatUser
                await bot.api.messages.remove_chat_user(chat_id=chat_id - 2000000000, user_id=user_id)
                # Это сообщение, скорее всего, не будет доставлено, так как пользователь будет кикнут
                # Но можно попробовать отправить его до кика или в другом месте
                user_display = await get_user_or_group_mention(user_id)
                await message.reply(
                    f"Пользователь {user_display} был исключен из конференции.\nПричина: Собственное желание",
                    attachment='audio-2001815713_128815713', disable_mentions=1)

            except VKAPIError as e:
                if e.code == 15:  # Access denied (нет прав у бота)
                    await message.reply(
                        "Ошибка: У бота недостаточно прав для кика. Выдайте боту права администратора в беседе.")
                elif e.code == 935:  # User is not in chat (пользователя уже нет в чате)
                    await message.reply("Ошибка: Вы уже не в чате.")
                else:
                    await message.reply(f"Произошла ошибка при кике: {e.description}")
            except Exception as e:
                await message.reply(f"Произошла непредвиденная ошибка: {e}")

            return True

        if command in ['szov', 'serverzov', 'сзов']:
            if await get_role_cached(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            reason = get_string(arguments, 1)
            if not reason:
                await message.reply("Укажите причину вызова!")
                return True

            if not await get_pull_chats(chat_id): return await message.reply("Сначала укажите сетку бесед!")

            for i in await get_pull_chats(chat_id):
                users = await bot.api.messages.get_conversation_members(peer_id=2000000000 + i,
                                                                        fields=["online_info", "online"])
                users = json.loads(users.json())
                user_f = []
                gi = 0
                for b in users["profiles"]:
                    if not b['id'] == user_id:
                        gi = gi + 1
                        if gi <= 100:
                            user_f.append(f"[id{b['id']}|🖤]")
                zov_users = ''.join(user_f)

                await bot.api.messages.send(peer_id=2000000000 + i,
                                            message=f"🔔 Вы были вызваны [id{user_id}|администратором] бесед!\n\n{zov_users}\n\n❗ Причина вызова: {reason}",
                                            random_id=0)

        if command in ['gszov', 'gserverzov', 'гсзов']:
            if await get_role_cached(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            reason = get_string(arguments, 1)
            if not reason:
                await message.reply("Укажите причину вызова!")
                return True

            if not await get_gpull_chats(chat_id): return await message.reply("Сначала укажите сетку бесед!")

            for i in await get_gpull_chats(chat_id):
                users = await bot.api.messages.get_conversation_members(peer_id=2000000000 + i,
                                                                        fields=["online_info", "online"])
                users = json.loads(users.json())
                user_f = []
                gi = 0
                for b in users["profiles"]:
                    if not b['id'] == user_id:
                        gi = gi + 1
                        if gi <= 100:
                            user_f.append(f"[id{b['id']}|🖤]")
                zov_users = ''.join(user_f)

                await bot.api.messages.send(peer_id=2000000000 + i,
                                            message=f"🔔 Вы были вызваны [id{user_id}|администратором] бесед!\n\n{zov_users}\n\n❗ Причина вызова: {reason}",
                                            random_id=0)

        if command in ['gban', 'гбан', 'глобалбан']:
            if await get_role_cached(user_id, chat_id) < 8:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user_to_gban_id = None
            arg_offset = 0

            if message.reply_message:
                user_to_gban_id = message.reply_message.from_id
                arg_offset = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user_to_gban_id = message.fwd_messages[0].from_id
                arg_offset = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user_to_gban_id = await getID(arguments[1])
                arg_offset = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if not isinstance(user_to_gban_id, int) or user_to_gban_id <= 0:
                await message.reply("Не удалось определить ID пользователя.", disable_mentions=1)
                return True

            gban_reason = get_string(arguments, arg_offset)
            if not gban_reason:
                await message.reply("Укажите причину!", disable_mentions=1)
                return True

            all_peer_ids = await get_all_peerids()
            if not all_peer_ids:
                await message.reply("Нет чатов для глобального бана.", disable_mentions=1)
                return True

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user_to_gban_id)
            
            await message.reply(
                f"Идет блокировка пользователя во всех беседах. Ожидайте...",
                disable_mentions=1)

            successful_gans_count = 0
            for peer_id_to_ban_in in all_peer_ids:
                if peer_id_to_ban_in < 2000000000:
                    continue
                current_chat_id = peer_id_to_ban_in - 2000000000

                try:
                    await gban(user_to_gban_id, user_id, current_chat_id, gban_reason)
                    await bot.api.messages.remove_chat_user(chat_id=current_chat_id, member_id=user_to_gban_id)
                    await add_punishment(current_chat_id, user_id)
                    successful_gans_count += 1
                except Exception as e:
                    print(f"Ошибка в чате {current_chat_id}: {e}")
                    continue

            await message.reply(
                f"{user_display} заблокировал(-а) {target_display} во всех чатах бота\nПричина: {gban_reason}",
                disable_mentions=1)
            return True

        if command in ['ungban', 'унгбан', 'гунбан', 'gunban']:
            if await get_role_cached(user_id, chat_id) < 8:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user_to_ungban_id = None
            arg_offset = 0

            if message.reply_message:
                user_to_ungban_id = message.reply_message.from_id
                arg_offset = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user_to_ungban_id = message.fwd_messages[0].from_id
                arg_offset = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user_to_ungban_id = await getID(arguments[1])
                arg_offset = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if not isinstance(user_to_ungban_id, int) or user_to_ungban_id <= 0:
                await message.reply("Не удалось определить ID пользователя.", disable_mentions=1)
                return True

            ungban_reason = get_string(arguments, arg_offset)
            if not ungban_reason:
                ungban_reason = "Глобальное разблокирование"

            getban = await gcheckban(user_to_ungban_id)
            if not getban:
                await message.reply("Пользователь не имеет глобального бана.", disable_mentions=1)
                return True

            await ungban(user_to_ungban_id)

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user_to_ungban_id)
            await message.reply(
                f"{user_display} глобально разблокировал {target_display}",
                disable_mentions=1)

        if command in ['zunban']:
            if await get_role_cached(user_id, chat_id) < 8:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user_to_ungban_id = None
            arg_offset = 0

            if message.reply_message:
                user_to_ungban_id = message.reply_message.from_id
                arg_offset = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user_to_ungban_id = message.fwd_messages[0].from_id
                arg_offset = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user_to_ungban_id = await getID(arguments[1])
                arg_offset = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if not isinstance(user_to_ungban_id, int) or user_to_ungban_id <= 0:
                await message.reply("Не удалось определить ID пользователя.", disable_mentions=1)
                return True

            ungban_reason = get_string(arguments, arg_offset)
            if not ungban_reason:
                ungban_reason = "Глобальное разблокирование"

            all_peer_ids = await get_all_peerids()

            if not all_peer_ids:
                await message.reply("Нет чатов для глобального разбана.", disable_mentions=1)
                return True

            successful_ungbans_count = 0

            for peer_id_to_ungban_in in all_peer_ids:
                if peer_id_to_ungban_in < 2000000000:
                    continue

                current_chat_id = peer_id_to_ungban_in - 2000000000

                try:
                    getban = await checkban(user_to_ungban_id, current_chat_id)
                    if getban:
                        await unban(user_to_ungban_id, current_chat_id, user_id, ungban_reason)
                        successful_ungbans_count += 1
                except:
                    continue

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user_to_ungban_id)
            await message.reply(
                f"{user_display} глобально разблокировал во всех беседах {target_display}",
                disable_mentions=1)

        # ========== Команды для Заместителя Руководителя (уровень 8) ==========
        # Список глобальных блокировок
        if command in ['gbanlist', 'гбанлист']:
            if await get_role_cached(user_id, chat_id) < 8:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            fetch = await db.fetchall("SELECT * FROM gbanlist ORDER BY rowid DESC")

            if not fetch:
                await message.reply("Список глобальных блокировок пуст!", disable_mentions=1)
                return True

            gbanlist_str = ""
            for i, row in enumerate(fetch, 1):
                uid, mod, reason, dt = row
                try:
                    user_name = await get_user_name(uid)
                except:
                    user_name = str(uid)
                try:
                    mod_name = await get_user_name(mod)
                except:
                    mod_name = str(mod)
                gbanlist_str += f"{i}. @id{uid} ({user_name}) | [id{mod}|{mod_name}] | Причина: {reason} | {dt}\n"

            await message.reply(
                f"📋 Список глобальных блокировок:\n\n{gbanlist_str}",
                disable_mentions=1
            )
            return True

        # КОМАНДА /stats С ДОБАВЛЕНИЕМ VIP СТАТУСА
        if command in ['stats', 'стата', 'статистика', 'stata', 'statistic']:
            user_id = message.from_id
            user = None
            if message.reply_message:
                user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                user = user_id
            if user < 0:
                await message.reply("Нельзя получать статистику сообщества!")
                return True
            print(f"Получение статистики для user_id: {user_id}, user: {user}")
            try:
                info = await bot.api.users.get(user_ids=[user], fields=['first_name', 'last_name', 'sex',
                                                                        'city'])
                if not info:
                    print("API вернул пустой список.")
                    await message.reply("Не удалось получить информацию о пользователе.")
                    return True
            except vk_api.exceptions.ApiError as e:
                print(f"Ошибка API: Код {e.code}, описание: {e}")
                await message.reply(f"Ошибка при получении информации о пользователе: {e}")
                return True

            # ПРОВЕРКА VIP СТАТУСА

            role = await get_role_cached(user, chat_id) or 0
            warns = await get_warns(user, chat_id)
            if await is_nick(user, chat_id):
                nick = await get_user_nam(user, chat_id)
            else:
                nick = "Нет"
            messages = await message_stats(user, chat_id)
            roles = {
                0: "Пользователь",
                1: "Модератор",
                2: "Старший модератор",
                3: "Администратор",
                4: "Старший администратор",
                5: "Заместитель специального администратора",
                6: "Специальный администратор",
                7: "Владелец беседы",
                8: "Заместитель Руководителя",
                9: "Основной Заместитель Руководителя",
                10: "Специальный Руководитель",
                11: "Разработчик",
                12: "Основной Заместитель Директора",
                13: "Директор",
                14: "Куратор Технических специалистов",
            }
            user_display = await get_user_or_group_mention(user)
            await message.reply(
                f"📊 Cтатистика {user_display}:\n\n"
                f"🎭 Роль: {roles.get(role, 'Пользователь')}\n"
                f"⚠️ Активные предупреждения: {warns}\n"
                f"👾 Ник: {nick}\n"
                f"💬 Всего сообщений: {messages['count']}\n"
                f"📆 Последнее сообщение: {messages['last']}",
                disable_mentions=1
            )
            print(f"DEBUG /stats: user={user}, role={role}, role_name={roles.get(role, 'Пользователь')}")
            return True

        if command in ['debug_ban_table']:
            # Только для разработчика
            if message.from_id not in [597064735, 574393629]:
                return True

            chat_id = message.chat_id
            table_name = f"bans_{chat_id}"

            # Проверяем структуру таблицы
            columns = await db.fetchall(f"PRAGMA table_info({table_name})")

            result = f"Структура таблицы {table_name}:\n"
            for col in columns:
                result += f"  {col[1]} ({col[2]})\n"

            # Проверяем последний бан
            last_ban = await db.fetchone(f"SELECT * FROM {table_name} ORDER BY date DESC LIMIT 1")

            if last_ban:
                result += f"\nПоследний бан:\n"
                if len(last_ban) >= 9:
                    result += f"  user_id: {last_ban[0]}\n"
                    result += f"  moder: {last_ban[1]}\n"
                    result += f"  reason: {last_ban[2]}\n"
                    result += f"  date: {last_ban[3]}\n"
                    result += f"  date_string: {last_ban[4]}\n"
                    result += f"  ban_time: {last_ban[6]}\n"
                    result += f"  ban_expire: {last_ban[7]}\n"
                    result += f"  ban_duration_text: {last_ban[8]}\n"
                else:
                    result += f"  Старая структура: {last_ban}\n"
            else:
                result += f"\nНет банов в этой таблице"

            await message.reply(result, disable_mentions=1)
            return True

        if command in ["infochat", "инфочат"]:
            if (await get_role_cached(user_id, chat_id) or 0) < 10:
                await message.reply('Недостаочно прав!')
                return True

        # Черный список бота
        if command in ['blacklist', 'черныйсписок', 'ЧСБ']:
            if await get_role_cached(user_id, chat_id) < 8:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            fetch = await db.fetchall("SELECT * FROM blacklist ORDER BY rowid DESC")

            if not fetch:
                await message.reply("Черный список бота пуст!", disable_mentions=1)
                return True

            blacklist_str = ""
            for i, row in enumerate(fetch, 1):
                uid, mod, reason, dt = row
                try:
                    user_name = await get_user_name(uid)
                except:
                    user_name = str(uid)
                try:
                    mod_name = await get_user_name(mod)
                except:
                    mod_name = str(mod)
                blacklist_str += f"{i}. @id{uid} ({user_name}) | [id{mod}|{mod_name}] | Причина: {reason} | {dt}\n"

            await message.reply(
                f"🚫 Черный список бота:\n\n{blacklist_str}",
                disable_mentions=1
            )
            return True

        # ========== Команды для Основного Заместителя Руководителя (уровень 12) ==========
        # Установить владельца беседы
        if command in ['setowner', 'установитьвладельца']:
            if await get_role_cached(user_id, chat_id) < 12:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if user == user_id:
                await message.reply("Вы не можете передать права самому себе!", disable_mentions=1)
                return True

            await set_owner(user, chat_id)
            await roleG(user, chat_id, 7)

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} установил(-а) владельца беседы: {target_display}",
                disable_mentions=1)
            return True

        # ========== Команды для Специального Руководителя (уровень 10) ==========
        # Рассылка по категориям бесед
        if command in ['sayall', 'news']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            reason = get_string(arguments, 1)
            if not reason:
                await message.reply("Укажите текст рассылки!", disable_mentions=1)
                return True

            peer_ids = await get_all_peerids()
            sent_count = 0
            for i in peer_ids:
                try:
                    await bot.api.messages.send(peer_id=i, message=reason, disable_mentions=1, random_id=0)
                    sent_count += 1
                except:
                    pass

            await message.reply(f"Рассылка отправлена в {sent_count} чатов.", disable_mentions=1)
            return True

        # Вызов всех участников в глобальном сервере
        if command in ['gzov', 'гзов']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            reason = get_string(arguments, 1)
            if not reason:
                await message.reply("Укажите причину вызова!", disable_mentions=1)
                return True

            # Получаем ВСЕ чаты где есть бот
            all_chats = await db.fetchall("SELECT chat_id FROM chats")

            if not all_chats:
                await message.reply("Бот не активирован ни в одном чате!", disable_mentions=1)
                return True

            sent_count = 0
            for chat_data in all_chats:
                i = chat_data[0]
                try:
                    users = await bot.api.messages.get_conversation_members(peer_id=2000000000 + i,
                                                                            fields=["online_info", "online"])
                    users = json.loads(users.json())
                    user_f = []
                    gi = 0
                    for b in users["profiles"]:
                        if not b['id'] == user_id:
                            gi += 1
                            if gi <= 100:
                                user_f.append(f"[id{b['id']}|🖤]")
                    zov_users = ''.join(user_f)

                    await bot.api.messages.send(
                        peer_id=2000000000 + i,
                        message=f"🔔 Вы были вызваны [id{user_id}|администратором] беседы!\n\n{zov_users}\n\n❗ Причина вызова: {reason}",
                        random_id=0
                    )
                    sent_count += 1
                except Exception as e:
                    print(f"Ошибка при вызове в чате {i}: {e}")
                    continue

            await message.reply(f"📣 Вызов успешно отправлен в {sent_count} чатов!", disable_mentions=1)
            return True

        if command in ['infoid', 'инфоайди']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 2:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            target = await getID(arguments[1])
            if not target:
                await message.reply("Не удалось определить пользователя.", disable_mentions=1)
                return True

            user_chats = await db.fetchall('SELECT chat_id FROM chats WHERE owner_id = $1', target,)

            if not user_chats:
                await message.reply("У пользователя нет зарегистрированных бесед.", disable_mentions=1)
                return True

            chats_text = ""
            for idx, (chat_id_val,) in enumerate(user_chats, start=1):
                try:
                    peer_id = 2000000000 + chat_id_val
                    info = await bot.api.messages.get_conversations_by_id(peer_ids=peer_id)
                    if info.items:
                        chat_title = info.items[0].chat_settings.title
                    else:
                        chat_title = "Без названия"
                except:
                    chat_title = "Не удалось получить название чата"

                chats_text += f"{idx}. {chat_title} | ID: {chat_id_val}\n"

            target_display = await get_user_or_group_mention(target)
            await message.reply(
                f"❗ Список бесед {target_display}:\n\n{chats_text}\n\n🗨️ Всего бесед: {len(user_chats)}",
                disable_mentions=1
            )
            return True

        if command in ['banid', 'банпоайди']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 3:
                await message.reply("Использование: /banid <chat_id> <user_id> [причина]", disable_mentions=1)
                return True

            try:
                target_chat = int(arguments[1])
            except:
                await message.reply("Неверный chat_id!", disable_mentions=1)
                return True

            user = await getID(arguments[2])
            if not user:
                await message.reply("Не удалось определить пользователя!", disable_mentions=1)
                return True

            reason = get_string(arguments, 3) if len(arguments) > 3 else "Бан по ID"

            try:
                await rnick(user, target_chat)
                await roleG(user, target_chat, 0)
                await ban(user, user_id, target_chat, reason)
                await bot.api.messages.remove_chat_user(target_chat, user)

                user_display = await get_user_or_group_mention(user_id)
                target_display = await get_user_or_group_mention(user)
                await message.answer(
                    f"{user_display} забанил(-а) {target_display} в чате {target_chat}",
                    disable_mentions=1)
            except Exception as e:
                await message.reply(f"Ошибка при бане: {e}", disable_mentions=1)
            return True

        if command in ['unbanid', 'унбанпоайди']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 3:
                await message.reply("Использование: /unbanid <chat_id> <user_id>", disable_mentions=1)
                return True

            try:
                target_chat = int(arguments[1])
            except:
                await message.reply("Неверный chat_id!", disable_mentions=1)
                return True

            user = await getID(arguments[2])
            if not user:
                await message.reply("Не удалось определить пользователя!", disable_mentions=1)
                return True

            try:
                await unban(user, target_chat)

                user_display = await get_user_or_group_mention(user_id)
                target_display = await get_user_or_group_mention(user)
                await message.answer(
                    f"{user_display} разблокировал(-а) {target_display} в чате {target_chat}",
                    disable_mentions=1)
            except Exception as e:
                await message.reply(f"Ошибка при разбане: {e}", disable_mentions=1)
            return True

        if command in ['say', 'сказать']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            reason = get_string(arguments, 1)
            if not reason:
                await message.reply("Укажите текст сообщения!", disable_mentions=1)
                return True

            try:
                await bot.api.messages.send(peer_id=message.peer_id, message=reason, disable_mentions=1, random_id=0)
            except Exception as e:
                await message.reply(f"Ошибка при отправке: {e}", disable_mentions=1)
                return True

            await message.answer("Сообщение отправлено!", disable_mentions=1)
            return True

        if command in ['addblack', 'добавитьвчерныйсписок']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            check = await db.fetchone('SELECT * FROM blacklist WHERE user_id = $1', user,)
            if check:
                await message.reply("Пользователь уже в черном списке!", disable_mentions=1)
                return True

            reason = get_string(arguments, 1) if len(arguments) > 1 else "Добавлен в ЧСБ"
            date_now = str(moscow_now()).split('.')[0]

            await db.execute("INSERT INTO blacklist (user_id, moderator_id, reason, datetime) VALUES ($1, $2, $3, $4)",
                        (user, user_id, reason, date_now))
            pass

            all_peer_ids = await get_all_peerids()
            kicked_count = 0
            for peer_id in all_peer_ids:
                if peer_id < 2000000000:
                    continue
                try:
                    await bot.api.messages.remove_chat_user(chat_id=peer_id - 2000000000, user_id=user)
                    kicked_count += 1
                except:
                    continue

            target_display = await get_user_or_group_mention(user)
            user_display = await get_user_or_group_mention(user_id)
            await message.reply(
                f"{user_display} добавил {target_display} в черный список бота.\nИсключён из {kicked_count} чатов.",
                disable_mentions=1)
            return True

        if command in ['unblack', 'удалитьизчерногосписка']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            check = await db.fetchone('SELECT * FROM blacklist WHERE user_id = $1', user,)
            if not check:
                await message.reply("Пользователь не в черном списке!", disable_mentions=1)
                return True

            await db.execute("DELETE FROM blacklist WHERE user_id = $1", (user,))
            pass

            await message.reply(f"Пользователь удален из черного списка бота!", disable_mentions=1)
            return True

        if command in ['clearchat', 'удалитьчат']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 2:
                await message.reply("Укажите chat_id!", disable_mentions=1)
                return True

            try:
                target_chat = int(arguments[1])
            except:
                await message.reply("Неверный chat_id!", disable_mentions=1)
                return True

            try:
                await bot.api.messages.send(
                    peer_id=2000000000 + target_chat,
                    message="Чат удален из базы данных бота! Работа бота в чате прекращена.",
                    disable_mentions=1,
                    random_id=0
                )
            except:
                pass

            await db.execute("DELETE FROM chats WHERE chat_id = $1", (target_chat,))
            pass

            user_display = await get_user_or_group_mention(user_id)
            await message.reply(f"{user_display} удалил(-а) чат №{target_chat} из базы данных", disable_mentions=1)
            return True

        if command in ['delchat', 'удалитьизбд']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 2:
                await message.reply("Укажите chat_id!", disable_mentions=1)
                return True

            try:
                target_chat = int(arguments[1])
            except:
                await message.reply("Неверный chat_id!", disable_mentions=1)
                return True

            # Добавляем в banschats чтобы бот не активировался
            await db.execute("INSERT INTO banschats (chat_id) VALUES ($1)", (target_chat,))
            await db.execute("DELETE FROM chats WHERE chat_id = $1", (target_chat,))
            pass

            user_display = await get_user_or_group_mention(user_id)
            await message.reply(f"{user_display} удалил(-а) чат №{target_chat} из базы данных и заблокировал активацию", disable_mentions=1)
            return True

        if command in ['listchats', 'списочатов']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            chats = await db.fetchall("SELECT chat_id FROM chats")

            if not chats:
                await message.reply("Нет зарегистрированных чатов!", disable_mentions=1)
                return True

            chats_text = ""
            for idx, (chat_id_val,) in enumerate(chats, start=1):
                try:
                    peer_id = 2000000000 + chat_id_val
                    info = await bot.api.messages.get_conversations_by_id(peer_ids=peer_id)
                    if info.items:
                        chat_title = info.items[0].chat_settings.title
                    else:
                        chat_title = "Без названия"
                except:
                    chat_title = "Не удалось получить название чата"

                chats_text += f"{idx}. {chat_title} | ID: {chat_id_val}\n"

            await message.reply(
                f"📋 Список чатов:\n\n{chats_text}\n\n🗨️ Всего чатов: {len(chats)}",
                disable_mentions=1
            )
            return True

        if command in ['infochat', 'инфочат']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 2:
                await message.reply("Укажите chat_id!", disable_mentions=1)
                return True

            try:
                target_chat = int(arguments[1])
            except:
                await message.reply("Неверный chat_id!", disable_mentions=1)
                return True

            chat_data = await db.fetchone('SELECT * FROM chats WHERE chat_id = $1', target_chat,)

            if not chat_data:
                await message.reply("Чат не найден в базе данных!", disable_mentions=1)
                return True

            await message.reply(
                f"ℹ️ Информация о чате №{target_chat}:\n\n"
                f"🆔 Chat ID: {chat_data[0]}\n"
                f"🔗 Peer ID: {chat_data[1]}\n"
                f"👑 Владелец: @id{chat_data[2]}",
                disable_mentions=1
            )
            return True

        if command in ['banwords', 'банворды', 'запрещенныеслова']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            banwords = await db.fetchall(f"SELECT * FROM banwords_{chat_id}")

            if not banwords:
                await message.reply("Список запрещенных слов пуст!", disable_mentions=1)
                return True

            words_text = "\n".join([f"{i+1}. {word}" for i, word in enumerate(banwords)])
            await message.reply(f"🚫 Запрещенные слова в чате:\n\n{words_text}", disable_mentions=1)
            return True

        if command in ['addbanwords', 'добавитьбанворд']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 2:
                await message.reply("Укажите слово!", disable_mentions=1)
                return True

            word = arguments[1].lower()
            check = await db.fetchone(f"SELECT * FROM banwords_{chat_id} WHERE banword = $1", (word,))

            if check:
                await message.reply("Это слово уже в списке!", disable_mentions=1)
                return True

            await db.execute(f"INSERT INTO banwords_{chat_id} VALUES ($1)", (word,))
            pass

            await message.reply(f"Слово «{word}» добавлено в список запрещенных!", disable_mentions=1)
            return True

        if command in ['removebanwords', 'удалитьбанворд']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 2:
                await message.reply("Укажите слово!", disable_mentions=1)
                return True

            word = arguments[1].lower()
            check = await db.fetchone(f"SELECT * FROM banwords_{chat_id} WHERE banword = $1", (word,))

            if not check:
                await message.reply("Это слово не в списке!", disable_mentions=1)
                return True

            await db.execute(f"DELETE FROM banwords_{chat_id} WHERE banword = $1", (word,))
            pass

            await message.reply(f"Слово «{word}» удалено из списка запрещенных!", disable_mentions=1)
            return True

        if command in ['give', 'выдать', 'монеты']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            amount_index = 0
            
            if message.reply_message:
                user = message.reply_message.from_id
                amount_index = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                amount_index = 2
            else:
                await message.reply("Укажите пользователя! (ответом или @упоминанием)", disable_mentions=1)
                return True

            if len(arguments) < amount_index + 1:
                await message.reply("Укажите сумму! Пример: /give @user 1000", disable_mentions=1)
                return True

            try:
                amount = int(arguments[amount_index])
            except:
                await message.reply("Сумма должна быть числом!", disable_mentions=1)
                return True

            if amount < 1:
                await message.reply("Сумма должна быть больше 0!", disable_mentions=1)
                return True

            balance = await db.fetchone('SELECT * FROM balance WHERE user_id = $1', user,)

            if balance:
                new_balance = balance[1] + amount
                await db.execute("UPDATE balance SET money = $1 WHERE user_id = $2", (new_balance, user))
            else:
                await db.execute("INSERT INTO balance (user_id, money, blago, bank) VALUES ($1, $2, $3, $4)",
                            (user, amount, 0, 0))

            pass

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) {amount:,} монет {target_display}",
                disable_mentions=1)
            return True

        # Выдать монеты в банк (уровень 10+)
        if command in ['выдатьбанк', 'givebank']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            amount_index = 0
            
            if message.reply_message:
                user = message.reply_message.from_id
                amount_index = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                amount_index = 2
            else:
                await message.reply("Укажите пользователя! (ответом или @упоминанием)", disable_mentions=1)
                return True

            if len(arguments) < amount_index + 1:
                await message.reply("Укажите сумму! Пример: /выдатьбанк @user 1000", disable_mentions=1)
                return True

            try:
                amount = int(arguments[amount_index])
            except:
                await message.reply("Сумма должна быть числом!", disable_mentions=1)
                return True

            if amount < 1:
                await message.reply("Сумма должна быть больше 0!", disable_mentions=1)
                return True

            balance = await db.fetchone('SELECT * FROM balance WHERE user_id = $1', user,)

            if balance:
                new_bank = balance[3] + amount
                await db.execute("UPDATE balance SET bank = $1 WHERE user_id = $2", (new_bank, user))
            else:
                await db.execute("INSERT INTO balance (user_id, money, blago, bank) VALUES ($1, $2, $3, $4)",
                            (user, 0, 0, amount))

            pass

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) {amount:,} монет в банк {target_display}",
                disable_mentions=1)
            return True

        # Выдать VIP (уровень 10+)
        if command in ['выдатьвип', 'givevip']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            days_index = 0
            
            if message.reply_message:
                user = message.reply_message.from_id
                days_index = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                days_index = 2
            else:
                await message.reply("Укажите пользователя! (ответом или @упоминанием)", disable_mentions=1)
                return True

            if len(arguments) < days_index + 1:
                await message.reply("Укажите количество дней! Пример: /выдатьвип @user 30", disable_mentions=1)
                return True

            try:
                days = int(arguments[days_index])
            except:
                await message.reply("Количество дней должно быть числом!", disable_mentions=1)
                return True

            if days < 1:
                await message.reply("Количество дней должно быть больше 0!", disable_mentions=1)
                return True

            # Получаем текущий VIP статус
            vip = await db.fetchone('SELECT * FROM vip_status WHERE user_id = $1', user,)

            current_time = int(time.time())
            if vip:
                # Если уже есть VIP, добавляем дни к текущему сроку
                new_expire = max(vip[1], current_time) + (days * 86400)
                await db.execute("UPDATE vip_status SET expire_time = $1 WHERE user_id = $2", (new_expire, user))
            else:
                # Если нет VIP, создаём новую запись
                new_expire = current_time + (days * 86400)
                await db.execute("INSERT INTO vip_status (user_id, expire_time) VALUES ($1, $2)", (user, new_expire))

            pass

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) VIP статус на {days} дн. {target_display}",
                disable_mentions=1)
            return True

        # Выдать дом (уровень 10+)
        if command in ['выдатьдом', 'givehouse']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            house_index = 0
            
            if message.reply_message:
                user = message.reply_message.from_id
                house_index = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                house_index = 2
            else:
                await message.reply("Укажите пользователя! (ответом или @упоминанием)", disable_mentions=1)
                return True

            if len(arguments) < house_index + 1:
                await message.reply("Укажите ID дома! Пример: /выдатьдом @user 1", disable_mentions=1)
                return True

            try:
                house_id = int(arguments[house_index])
            except:
                await message.reply("ID дома должен быть числом!", disable_mentions=1)
                return True

            # Проверяем существование дома в HOUSES_DATA
            if house_id not in HOUSES_DATA:
                await message.reply(f"❌ Дом с ID {house_id} не найден!", disable_mentions=1)
                return True

            # Проверяем, есть ли уже такой дом у пользователя
            if await db.fetchone("SELECT id FROM houses WHERE user_id = $1 AND house_id = $2", (user, house_id)):

                await message.reply(f"❌ У пользователя уже есть этот дом!", disable_mentions=1)
                return True

            # Добавляем дом пользователю
            current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')
            await db.execute("INSERT INTO houses (user_id, house_id, purchase_date) VALUES ($1, $2, $3)",
                        (user, house_id, current_time))
            pass

            house_name = HOUSES_DATA[house_id]['name']
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) дом '{house_name}' {target_display}",
                disable_mentions=1)
            return True

        # Выдать машину (уровень 10+)
        if command in ['выдатьмашину', 'givecar']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            car_index = 0
            
            if message.reply_message:
                user = message.reply_message.from_id
                car_index = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                car_index = 2
            else:
                await message.reply("Укажите пользователя! (ответом или @упоминанием)", disable_mentions=1)
                return True

            if len(arguments) < car_index + 1:
                await message.reply("Укажите ID машины! Пример: /выдатьмашину @user 1", disable_mentions=1)
                return True

            try:
                car_id = int(arguments[car_index])
            except:
                await message.reply("ID машины должен быть числом!", disable_mentions=1)
                return True

            # Проверяем существование машины в CARS_DATA
            if car_id not in CARS_DATA:
                await message.reply(f"❌ Машина с ID {car_id} не найдена!", disable_mentions=1)
                return True

            # Проверяем, есть ли уже такая машина у пользователя
            if await db.fetchone("SELECT id FROM cars WHERE user_id = $1 AND car_id = $2", (user, car_id)):

                await message.reply(f"❌ У пользователя уже есть эта машина!", disable_mentions=1)
                return True

            # Добавляем машину пользователю
            current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')
            await db.execute("INSERT INTO cars (user_id, car_id, purchase_date) VALUES ($1, $2, $3)",
                        (user, car_id, current_time))
            pass

            car_name = CARS_DATA[car_id]['name']
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) машину '{car_name}' {target_display}",
                disable_mentions=1)
            return True

        # Выдать бизнес (уровень 10+)
        if command in ['выдатьбиз', 'givebusiness']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            business_index = 0
            
            if message.reply_message:
                user = message.reply_message.from_id
                business_index = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                business_index = 2
            else:
                await message.reply("Укажите пользователя! (ответом или @упоминанием)", disable_mentions=1)
                return True

            if len(arguments) < business_index + 1:
                await message.reply("Укажите ID бизнеса! Пример: /выдатьбиз @user 1", disable_mentions=1)
                return True

            try:
                business_id = int(arguments[business_index])
            except:
                await message.reply("ID бизнеса должен быть числом!", disable_mentions=1)
                return True

            # Проверяем существование бизнеса в BUSINESS_TYPES
            if business_id not in BUSINESS_TYPES:
                await message.reply(f"❌ Бизнес с ID {business_id} не найден!", disable_mentions=1)
                return True

            # Проверяем, есть ли уже у пользователя этот бизнес
            existing = await db.fetchone('SELECT * FROM user_businesses WHERE user_id = $2 AND biz_id = $1', user, business_id)

            if existing:
                # Увеличиваем количество
                await db.execute("UPDATE user_businesses SET count = count + 1 WHERE user_id = $1 AND biz_id = $2",
                            (user, business_id))
            else:
                # Добавляем новый бизнес
                current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')
                await db.execute("INSERT INTO user_businesses (user_id, biz_id, count, last_collected, balance) VALUES ($1, $2, $3, $4, $5)",
                            (user, business_id, 1, current_time, 0))

            pass

            business_name = BUSINESS_TYPES[business_id]['name']
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) бизнес '{business_name}' {target_display}",
                disable_mentions=1)
            return True

        # Обнулить монеты пользователя (уровень 10+)
        if command in ['логиэко', 'logeco', 'logeconomy']:
            role = await get_role_cached(user_id, chat_id)
            if role < 9:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            target_id = None
            if message.reply_message:
                target_id = message.reply_message.from_id
            elif len(arguments) >= 2:
                target_id = await getID(arguments[1])
                if not target_id:
                    try:
                        target_id = int(arguments[1])
                    except ValueError:
                        target_id = None
            try:
                if target_id:
                    await db.execute("SELECT user_id, target_id, amount, log FROM economy WHERE user_id = $1 OR target_id = $2 ORDER BY rowid DESC LIMIT 25", (target_id, target_id))
                else:
                    rows = await db.fetchall("SELECT user_id, target_id, amount, log FROM economy ORDER BY rowid DESC LIMIT 25")

            except sqlite3.Error as e:
                await message.reply(f"❌ Не удалось прочитать логи экономики: {e}", disable_mentions=1)
                return True
            if not rows:
                await message.reply("Логи экономики не найдены.", disable_mentions=1)
                return True
            lines = []
            for idx, (actor, target, amount, log_text) in enumerate(rows, 1):
                actor_text = await get_user_or_group_mention(actor) if actor else "—"
                target_text = await get_user_or_group_mention(target) if target else "—"
                amount_text = format_number(amount) + "₽" if amount is not None else "—"
                lines.append(f"{idx}. {actor_text} → {target_text} | {amount_text}\n{log_text or '—'}")
            title = f"📊 Логи экономики пользователя {await get_user_or_group_mention(target_id)}" if target_id else "📊 Последние логи экономики"
            await message.reply(title + "\n\n" + "\n\n".join(lines), disable_mentions=1)
            return True

        if command in ['обнулить', 'resetbalance', 'сбросбаланса']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            balance = await db.fetchone('SELECT * FROM balance WHERE user_id = $1', user,)

            if balance and balance[1] > 0:
                old_balance = balance[1]
                await db.execute("UPDATE balance SET money = 0 WHERE user_id = $1", (user,))
                pass
                
                user_display = await get_user_or_group_mention(user_id)
                target_display = await get_user_or_group_mention(user)
                await message.answer(
                    f"{user_display} обнулил(-а) баланс {target_display} (было: {old_balance:,} монет)",
                    disable_mentions=1)
            else:
                user_display = await get_user_or_group_mention(user_id)
                target_display = await get_user_or_group_mention(user)
                await message.answer(
                    f"{user_display} у {target_display} и так баланс 0",
                    disable_mentions=1)
            return True

        # Исправить базу данных бизнесов (уровень 11+)
        if command in ['фиксбиз', 'fixbiz']:
            # Проверка прав (только разработчики, уровень 11+)
            if await get_role_cached(user_id, chat_id) < 11:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            # Проверяем и добавляем недостающие бизнесы
            missing_businesses = [
                (13, "Нефтяная вышка", "🛢️", 1500000000, 200000000, 250000000, "Добыча нефти"),
                (14, "Алмазная шахта", "💎", 2000000000, 280000000, 350000000, "Добыча драгоценных камней"),
                (15, "Завод по производству электроники", "📺", 2500000000, 350000000, 420000000, "Производство техники"),
                (16, "Авиакомпания", "✈️", 3500000000, 450000000, 550000000, "Пассажирские перевозки"),
                (17, "Телекоммуникационная компания", "📡", 5000000000, 600000000, 750000000, "Связь и интернет"),
                (18, "Сеть отелей", "🏨", 7000000000, 850000000, 1000000000, "Гостиничный бизнес"),
                (19, "Фармацевтическая корпорация", "💊", 10000000000, 1200000000, 1500000000, "Производство лекарств"),
                (20, "Международный финансовый холдинг", "🏦", 15000000000, 1800000000, 2200000000, "Финансовые услуги"),
            ]

            added_count = 0
            for biz in missing_businesses:
                try:
                    if not await db.fetchone("SELECT biz_id FROM business_types WHERE biz_id = $1", (biz[0],)):

                        await db.execute(
                            "INSERT INTO business_types (biz_id, name, emoji, price, min_profit, max_profit, description) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                            biz
                        )
                        added_count += 1
                except Exception as e:
                    print(f"Ошибка при добавлении бизнеса {biz[1]}: {e}")

            pass

            # Проверяем результат
            count = await db.fetchone("SELECT COUNT(*) FROM business_types")

            await message.reply(
                f"✅ База данных бизнесов обновлена!\n\n"
                f"📊 Всего бизнесов в БД: {count}\n"
                f"➕ Добавлено новых: {added_count}",
                disable_mentions=1
            )
            return True

        # Очистить все блокировки в чате
        if command in ['clearbans', 'очиститьбаны']:
            if await get_role_cached(user_id, chat_id) < 10:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            await db.execute(f"DELETE FROM bans_{chat_id}")
            pass

            user_display = await get_user_or_group_mention(user_id)
            await message.answer(
                f"{user_display} очистил(-а) все блокировки в чате",
                disable_mentions=1)
            return True

        if command in ['editowner', 'owner', 'setowner']:
            if await get_role_cached(user_id, chat_id) < 7:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
                arg_offset = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg_offset = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg_offset = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if user == user_id: return await message.reply("⛔️ Вы не можете передать права самому себе!")

            await set_owner(user, chat_id)
            await roleG(user, chat_id, 7)
            await roleG(user_id, chat_id, 6)
            owner = int(user_id)

            target_display = await get_user_or_group_mention(user)
            sender_display = await get_user_or_group_mention(user_id)

            await message.answer(
                f"{sender_display} успешно передал(-а) права владельца пользователю {target_display}\n"
                f"{sender_display} выданы права Специального администратора.",
                disable_mentions=1)

        if command in ['srole', 'setrole']:
            if await get_role_cached(user_id, chat_id) < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            arg = 2
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await get_role_cached(user_id, chat_id) <= await get_role_cached(user, chat_id): return await message.reply(
                "⛔️ Вы не можете взаимодействовать с данным пользователем!")

            if len(arguments) < arg + 1: return await message.reply("Укажите аргументы!")

            if not arguments[arg].isdigit(): return await message.reply("Укажите число!")

            level = int(arguments[arg])
            if level >= await get_role_cached(user_id, chat_id): return await message.reply(
                "⛔️ Вы не можете выдать роль, которая выше вашей!")

            if level < 0: return await message.reply("Нельзя выдать такую роль!"),
            await roleG(user, chat_id, level)
            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) уровень прав {level} пользователю {target_display}")

        if command in ['infobot', 'инфобот']:
            await message.reply(
                f"📢 Официальные ресурсы бота:\n\nЕсли вы нашли какой-то баг или проблему в работе бота, пожалуйста, обратитесь:\n\n🔧 Разработчик бота —\nhttps://vk.ru/id574393629\nhttps://vk.ru/id597064735\n\n🎮 Игровая площадка —\nhttps://vk.me/join/AZQ1d967ZCaDrxOM0rSZhPOz",
                disable_mentions=1)

        if command in ['id', 'ид', 'getid', 'гетид', 'получитьид', 'giveid']:
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                user = user_id
            if user < 0:
                await message.reply(
                    f"Оригинальная ссылка [club{abs(user)}|{await get_group_name(user)}]:\nhttps://vk.com/club{abs(user)}",
                    disable_mentions=1)
                return True
            target_display = await get_user_or_group_mention(user)
            await message.reply(f"Оригинальная ссылка {target_display}:\nhttps://vk.com/id{user}",
                                disable_mentions=1)

        if message.reply_message and message.reply_message.from_id < 0:
            return True

        if command in ['ssnick', 'ссник']:
            if await get_role_cached(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await get_role_cached(user_id, chat_id) <= await get_role_cached(user, chat_id): return await message.reply(
                "⛔️ Вы не можете взаимодействовать с данным пользователем!")

            if await get_pull_id(chat_id) == 0: return await message.reply(
                "Сначала укажите сетку бесед, используя /server")

            chats = await get_pull_chats(chat_id)

            new_nick = get_string(arguments, arg)

            for i in chats:
                await setnick(user, i, new_nick)

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) ник {new_nick} в сетке бесед пользователю {target_display}")

        if command in ['gssnick', 'гссник']:
            if await get_role_cached(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await get_role_cached(user_id, chat_id) <= await get_role_cached(user, chat_id): return await message.reply(
                "⛔️ Вы не можете взаимодействовать с данным пользователем!")

            if await get_gpull_id(chat_id) == 0: return await message.reply(
                "Сначала укажите сетку бесед, используя /server")

            chats = await get_gpull_chats(chat_id)

            new_nick = get_string(arguments, arg)

            for i in chats:
                await setnick(user, i, new_nick)

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) ник {new_nick} в глобальной сетке бесед пользователю {target_display}")

        if command in ['ssrole', 'prole', 'pullrole']:
            if await get_role_cached(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            arg = 2
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await get_role_cached(user_id, chat_id) <= await get_role_cached(user, chat_id): return await message.reply(
                "⛔️ Вы не можете взаимодействовать с данным пользователем!")

            if len(arguments) < arg + 1: return await message.reply("Укажите аргументы!")

            if not arguments[arg].isdigit(): return await message.reply("Укажите число!")

            level = int(arguments[arg])
            if level >= await get_role_cached(user_id, chat_id): return await message.reply(
                "⛔️ Вы не можете выдать роль, которая выше вашей!")

            if level < 0: return await message.reply("Нельзя выдать такую роль!")

            if await get_pull_id(chat_id) == 0: return await message.reply(
                "Сначала укажите сетку бесед, используя /server")

            chats = await get_pull_chats(chat_id)

            for i in chats:
                await roleG(user, i, level)

            user_display = await get_user_or_group_mention(user_id)
            target_display = await get_user_or_group_mention(user)
            await message.answer(
                f"{user_display} выдал(-а) уровень прав {level} в сетке бесед пользователю {target_display}")

    if command in ['settingsphoto', 'настройкифото']:
        if await get_role_cached(user_id, chat_id) < 7:
            await message.reply("Недостаточно прав!", disable_mentions=1)
            return True

        row = await db.fetchone('SELECT * FROM photosettings WHERE chat_id = $1', chat_id,)
        if row is None:
            await db.execute("INSERT INTO photosettings (chat_id, mode) VALUES ($1, $2)", (chat_id, 1))
            pass
            user_display = await get_user_or_group_mention(user_id)
            await message.reply(
                f"{user_display}, включил(-а) систему удаления фотографий!",
                disable_mentions=1)
        else:
            new_mode = 0 if row[1] == 1 else 1
            await db.execute("UPDATE photosettings SET mode = $1 WHERE chat_id = $2", (new_mode, chat_id))
            pass
            user_display = await get_user_or_group_mention(user_id)
            if new_mode == 0:
                await message.reply(
                    f"{user_display}, выключил(-а) систему удаления фотографий!",
                    disable_mentions=1)
            else:
                await message.reply(
                    f"{user_display}, включил(-а) систему удаления фотографий!",
                    disable_mentions=1)

        return True

    if command in ['gssrole', 'gprole', 'gpullrole']:
        if await get_role_cached(user_id, chat_id) < 5:
            await message.reply("Недостаточно прав!", disable_mentions=1)
            return True

        user = int
        arg = 2
        if message.reply_message:
            user = message.reply_message.from_id
            arg = 1
        elif len(arguments) >= 2 and await getID(arguments[1]):
            user = await getID(arguments[1])
        else:
            await message.reply("Укажите пользователя!", disable_mentions=1)
            return True

        if await get_role_cached(user_id, chat_id) <= await get_role_cached(user, chat_id): return await message.reply(
            "⛔️ Вы не можете взаимодействовать с данным пользователем!")

        if len(arguments) < arg + 1: return await message.reply("Укажите аргументы!")

        if not arguments[arg].isdigit(): return await message.reply("Укажите число!")

        level = int(arguments[arg])
        if level >= await get_role_cached(user_id, chat_id): return await message.reply(
            "⛔️ Вы не можете выдать роль, которая выше вашей!")

        if level < 0: return await message.reply("Нельзя выдать такую роль!")

        if await get_gpull_id(chat_id) == 0: return await message.reply(
            "Сначала укажите глобальную сетку бесед, используя /gserver")

        chats = await get_gpull_chats(chat_id)

        for i in chats:
            await roleG(user, i, level)

        user_display = await get_user_or_group_mention(user_id)
        target_display = await get_user_or_group_mention(user)
        await message.answer(
            f"{user_display} выдал(-а) уровень прав {level} в глобальной сетке бесед пользователю {target_display}")

    else:
        if user_id < 1:
            return True

        if await check_chat(chat_id):
            # Проверка мута для обычных сообщений (не команд)
            if await is_muted(user_id, chat_id):
                try:
                    await bot.api.messages.delete(
                        group_id=message.group_id,
                        peer_id=message.peer_id,
                        delete_for_all=True,
                        cmids=message.conversation_message_id
                    )
                    return True  # Прерываем обработку, чтобы сообщение не пошло дальше
                except Exception as e:
                    print(f"Ошибка при удалении сообщения: {e}")

            # Проверка режима тишины
            elif await check_quit(chat_id) and await get_role_cached(user_id, chat_id) < 1:
                try:
                    await bot.api.messages.delete(group_id=message.group_id, peer_id=message.peer_id,
                                                  delete_for_all=True, cmids=message.conversation_message_id)
                except:
                    pass

            # Фильтр запрещенных слов
            if await get_filter(chat_id):
                bws = await get_banwords(chat_id)
                for i in bws:
                    if i in message.text.lower() and await get_role_cached(user_id, chat_id) < 1:
                        await mute(user_id, chat_id, 'Бот', 'Написание запрещенных слов', 30)
                        keyboard = (
                            Keyboard(inline=True)
                            .add(Callback("Снять мут",
                                          {"command": "unmute", "chatId": chat_id, "user": user_id}),
                                 color=KeyboardButtonColor.POSITIVE)
                        )
                        user_display = await get_user_or_group_mention(user_id)
                        await message.reply(
                            f"{user_display} получил(-а) мут на 30 минут за написание запрещенного слова!",
                            disable_mentions=1, keyboard=keyboard)
                        try:
                            await bot.api.messages.delete(group_id=message.group_id,
                                                          peer_id=message.peer_id,
                                                          delete_for_all=True,
                                                          cmids=message.conversation_message_id)
                        except:
                            pass
                        return True

            # Записываем сообщение в статистику
            await new_message(user_id, message.message_id, message.conversation_message_id, chat_id)

            # Антифлуд
            if await get_antiflood(chat_id):
                if await get_spam(user_id, chat_id) and await get_role_cached(user_id, chat_id) < 1:
                    keyboard = (
                        Keyboard(inline=True)
                        .add(Callback("Снять мут",
                                      {"command": "unmute", "chatId": chat_id, "user": user_id}),
                             color=KeyboardButtonColor.POSITIVE)
                    )
                    user_display = await get_user_or_group_mention(user_id)
                    await message.reply(f"{user_display} получил(-а) мут на 30 минут за спам!",
                                        disable_mentions=1, keyboard=keyboard)
                    await mute(user_id, chat_id, 'Bot', 'Спам', 30)
                    try:
                        await bot.api.messages.delete(group_id=message.group_id, peer_id=message.peer_id,
                                                      delete_for_all=True,
                                                      cmids=message.conversation_message_id)
                    except:
                        pass

# Обновляем таблицы мутов при старте
async def init_mute_system():
    await update_mutes_tables()
    # Загружаем существующие муты из БД в кэш
    try:
        tables = await db.fetchall("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'mutes_%'")

        for table in tables:
            table_name = table[0]
            chat_id = int(table_name.replace('mutes_', ''))

            try:
                rows = await db.fetchall(f"SELECT user_id, moder, reason, date, time, expire_time FROM {table_name}")

                for row in rows:
                    user_id, moder, reason, mute_date, duration, expire_time = row

                    # Если нет expire_time, рассчитываем
                    if expire_time is None:
                        if duration > 0:
                            expire_time = mute_date + (duration * 60)
                        else:
                            expire_time = 0

                    # Проверяем, не истек ли мут
                    if expire_time > 0 and time.time() > expire_time:
                        await unmute(user_id, chat_id, auto=True)
                    else:
                        cache_key = f"{chat_id}_{user_id}"
                        muted_users_cache[cache_key] = {
                            "expire_time": expire_time,
                            "moder": moder,
                            "reason": reason,
                            "date": mute_date
                        }
            except Exception as e:
                print(f"Ошибка при загрузке мутов из {table_name}: {e}")
    except Exception as e:
        print(f"Ошибка при инициализации системы мутов: {e}")

    print(f"Загружено {len(muted_users_cache)} активных мутов в кэш")

async def update_all_bans_tables():
    """Обновляет все таблицы банов, добавляя колонки для времени"""
    try:
        # Получаем все таблицы банов
        tables = await db.fetchall("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'bans_%'")

        for table in tables:
            table_name = table[0]

            # Пропускаем таблицу banschats
            if table_name == 'banschats':
                continue

            # Извлекаем chat_id
            try:
                chat_id = int(table_name.replace('bans_', ''))
                print(f"Обновление таблицы: {table_name} (чат {chat_id})")
            except ValueError:
                print(f"Пропущена таблица: {table_name}")
                continue

            # Проверяем текущую структуру
            columns = await db.fetchall(f"PRAGMA table_info({table_name})")

            column_names = [col[1] for col in columns]

            # Добавляем недостающие колонки
            if 'ban_time' not in column_names:
                await db.execute(f"ALTER TABLE {table_name} ADD COLUMN ban_time INTEGER DEFAULT 0")
                pass
                print(f"  + Добавлена колонка ban_time")

            if 'ban_expire' not in column_names:
                await db.execute(f"ALTER TABLE {table_name} ADD COLUMN ban_expire REAL DEFAULT 0")
                pass
                print(f"  + Добавлена колонка ban_expire")

            if 'ban_duration_text' not in column_names:
                await db.execute(f"ALTER TABLE {table_name} ADD COLUMN ban_duration_text TEXT DEFAULT 'навсегда'")
                pass
                print(f"  + Добавлена колонка ban_duration_text")

        print("✅ Все таблицы банов успешно обновлены!")

    except Exception as e:
        print(f"Ошибка при обновлении таблиц: {e}")

async def start_background_tasks():
    await update_mutes_tables()
    await update_all_bans_tables()
    await fix_old_bans()  # Добавьте эту строку
    await cleanup_expired_bans_on_start()
    asyncio.create_task(cleanup_mutes())
    asyncio.create_task(cleanup_bans())
    print("✅ Система мутов и банов запущена")

# Создаем цикл событий и запускаем задачи
loop = asyncio.get_event_loop()
loop.create_task(start_background_tasks())

print("🚀 Бот запускается...")
bot.run_forever()