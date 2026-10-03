from vkbottle.exception_factory import VKAPIError
import os, re
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
from typing import Optional
from vkbottle import Keyboard, Callback, CtxStorage, KeyboardButtonColor, Text, GroupEventType, GroupTypes, User, \
    VKAPIError
import json
import sqlite3
import locale
import dateparser

MOSCOW_TZ = timezone(timedelta(hours=3))

def moscow_now():
    return datetime.now(MOSCOW_TZ).replace(tzinfo=None)

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
with open("config3.json", "r") as js:
    open_file = json.load(js)
current_duel = {}
api = API(open_file['bot-token'])
api.api_version = "5.131"
bot = Bot(api=api)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
SUBS_FILE = "SUBS_FILE.json"

current_duel = {}

# ================== СИСТЕМА МАФИИ ==================
active_mafia_games = {}
MAFIA_INACTIVE_TIMEOUT = 600  # 10 минут
MAFIA_MIN_PLAYERS = 4
MAFIA_ACTION_TIMEOUT = 20
mafia_game_locks = {}

class MafiaGame:
    def __init__(self, chat_id: int, creator_id: int):
        self.chat_id = chat_id
        self.creator_id = creator_id
        self.players = []
        self.roles = {}
        self.alive = {}
        self.status = "waiting"
        self.day = 1
        self.phase = "night"
        self.current_action = None
        self.waiting_for_action = set()
        self.last_kill = None
        self.last_lynch = None
        self.votes = {}
        self.mafia_votes = {}
        self.commissar_checked = {}
        self.doctor_saved = None
        self.mafia_count = 0
        self.civilians_count = 0
        self.action_messages = {}
        self.phase_message_id = None
        self.created_at = time.time()
        self.last_action_time = time.time()
        self.phase_token = 0
        self.phase_timer_task = None

MAFIA_ROLES = {
    "mafia": {
        "name": "Мафия",
        "emoji": "🔪",
        "team": "mafia",
        "order": 3,
        "description": "Каждую ночь убивает одного игрока"
    },
    "civilian": {
        "name": "Мирный житель",
        "emoji": "👨‍🌾",
        "team": "civilian",
        "order": 4,
        "description": "Голосует днём за подозреваемых"
    },
    "commissar": {
        "name": "Комиссар",
        "emoji": "👮",
        "team": "civilian",
        "order": 2,
        "description": "Ночью может проверить одного игрока"
    },
    "doctor": {
        "name": "Доктор",
        "emoji": "👨‍⚕️",
        "team": "civilian",
        "order": 1,
        "description": "Ночью может спасти одного игрока"
    }
}



def get_mafia_lock(chat_id: int) -> asyncio.Lock:
    lock = mafia_game_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        mafia_game_locks[chat_id] = lock
    return lock


def ensure_mafia_mutes_table():
    sql.execute("""
        CREATE TABLE IF NOT EXISTS mafia_mutes (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (chat_id, user_id)
        )
    """)
    database.commit()


async def set_mafia_muted(chat_id: int, user_id: int, muted: bool = True):
    ensure_mafia_mutes_table()
    if muted:
        sql.execute("INSERT OR IGNORE INTO mafia_mutes (chat_id, user_id) VALUES (?, ?)", (chat_id, user_id))
    else:
        sql.execute("DELETE FROM mafia_mutes WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    database.commit()


async def sync_mafia_phase_mutes(game):
    ensure_mafia_mutes_table()
    # Мёртвые остаются в муте до конца игры. Ночью также молчат все живые.
    muted_ids = [p for p in game.players if not game.alive.get(p, False) or game.phase == "night"]
    sql.execute("DELETE FROM mafia_mutes WHERE chat_id = ?", (game.chat_id,))
    sql.executemany("INSERT OR IGNORE INTO mafia_mutes (chat_id, user_id) VALUES (?, ?)",
                    [(game.chat_id, p) for p in muted_ids])
    database.commit()


async def clear_mafia_mutes(chat_id: int):
    ensure_mafia_mutes_table()
    sql.execute("DELETE FROM mafia_mutes WHERE chat_id = ?", (chat_id,))
    database.commit()


def cancel_mafia_timer(game):
    task = getattr(game, "phase_timer_task", None)
    if task and not task.done() and task is not asyncio.current_task():
        task.cancel()
    game.phase_timer_task = None


def schedule_mafia_timeout(chat_id: int, game, expected_phase: str, expected_action=None):
    cancel_mafia_timer(game)
    game.phase_token += 1
    token = game.phase_token

    async def timeout_worker():
        try:
            await asyncio.sleep(MAFIA_ACTION_TIMEOUT)
            if active_mafia_games.get(chat_id) is not game or game.phase_token != token:
                return
            if game.phase != expected_phase:
                return
            if expected_action is not None and game.current_action != expected_action:
                return
            game.waiting_for_action.clear()
            if expected_phase == "night":
                if expected_action == "mafia":
                    votes_count = {}
                    for target in game.mafia_votes.values():
                        votes_count[target] = votes_count.get(target, 0) + 1
                    if votes_count:
                        max_votes = max(votes_count.values())
                        targets = [target for target, count in votes_count.items() if count == max_votes]
                        game.last_kill = targets[0] if len(targets) == 1 else None
                    else:
                        game.last_kill = None
                await next_night_action(chat_id, game)
            else:
                # Не проголосовавшие автоматически воздерживаются.
                await resolve_day_votes_timeout(chat_id, game)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Ошибка таймера мафии: {e}")

    game.phase_timer_task = asyncio.create_task(timeout_worker())

# ================== ФУНКЦИИ ДЛЯ РАБОТЫ С СООБЩЕСТВАМИ ==================
async def get_group_name(group_id: int) -> str:
    try:
        abs_id = abs(group_id)
        response = await bot.api.groups.get_by_id(group_ids=[abs_id])
        if hasattr(response, 'groups'):
            groups_list = response.groups
            if groups_list and len(groups_list) > 0:
                return groups_list[0].name
        return f"ID{abs_id}"
    except Exception as e:
        print(f"Ошибка получения названия сообщества {group_id}: {e}")
        return f"ID{abs(group_id)}"

async def get_user_or_group_name(user_id: int) -> str:
    if user_id < 0:
        return await get_group_name(user_id)
    else:
        return await get_user_name(user_id)

async def get_user_or_group_mention(user_id: int) -> str:
    if user_id < 0:
        name = await get_group_name(user_id)
        return f"[club{abs(user_id)}|{name}]"
    else:
        return f"@id{user_id} ({await get_user_name(user_id)})"

# ================== МАФИЯ - ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================
async def update_mafia_activity(chat_id: int):
    if chat_id in active_mafia_games:
        active_mafia_games[chat_id].last_action_time = time.time()

async def get_alive_players_keyboard(game: MafiaGame, action: str, current_player_id: int = None):
    keyboard = Keyboard(inline=True)
    alive_players = [p for p in game.players if game.alive.get(p, False)]
    if current_player_id:
        alive_players = [p for p in alive_players if p != current_player_id]
    for i, player in enumerate(alive_players):
        name = await get_user_or_group_name(player)
        display_name = name[:20] + "..." if len(name) > 20 else name
        keyboard.add(Callback(display_name, payload={"cmd": f"mafia_{action}", "target": player, "target_name": name}), color=KeyboardButtonColor.PRIMARY)
        if (i + 1) % 2 == 0:
            keyboard.row()
    if not alive_players:
        keyboard.add(Callback("❌ Нет игроков", payload={"cmd": "mafia_none"}), color=KeyboardButtonColor.NEGATIVE)
    return keyboard

async def send_phase_message(chat_id: int, game: MafiaGame, text: str, keyboard=None):
    peer_id = 2000000000 + chat_id
    try:
        if game.phase_message_id:
            await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=game.phase_message_id, message=text, keyboard=keyboard)
        else:
            msg = await bot.api.messages.send(peer_id=peer_id, message=text, keyboard=keyboard, random_id=0)
            game.phase_message_id = msg.conversation_message_id
    except Exception as e:
        print(f"Ошибка при отправке сообщения фазы: {e}")

async def send_action_request(player_id: int, game: MafiaGame, action: str):
    role = game.roles.get(player_id)
    role_name = MAFIA_ROLES[role]["name"] if role in MAFIA_ROLES else "Игрок"
    keyboard = await get_alive_players_keyboard(game, action, player_id)
    if action == "kill":
        text = f"🔪 {role_name}, наступила ночь!\n\nВыберите игрока для убийства:"
    elif action == "check":
        text = f"👮 {role_name}, наступила ночь!\n\nВыберите игрока для проверки:"
    elif action == "save":
        text = f"👨‍⚕️ {role_name}, наступила ночь!\n\nВыберите игрока для спасения:"
    else:
        text = f"☀️ Наступил день!\n\nВыберите игрока для казни:"
    try:
        await bot.api.messages.send(user_id=player_id, message=text, keyboard=keyboard, random_id=0)
    except Exception as e:
        print(f"Не удалось отправить запрос игроку {player_id}: {e}")

async def check_mafia_winner(game: MafiaGame) -> str:
    if game.mafia_count <= 0:
        return "civilian"
    if game.mafia_count >= game.civilians_count:
        return "mafia"
    return None

async def end_game_and_cleanup(chat_id: int, game: MafiaGame, winner: str):
    winner_name = "Мирные жители" if winner == "civilian" else "Мафия"
    mafia_players = [p for p in game.players if game.roles.get(p) == "mafia"]
    civilian_players = [p for p in game.players if game.roles.get(p) != "mafia"]
    mafia_list = [f"🔪 {await get_user_or_group_mention(p)}" for p in mafia_players]
    civilian_list = [f"👨‍🌾 {await get_user_or_group_mention(p)}" for p in civilian_players]
    final_text = (f"🏆 ИГРА ЗАВЕРШЕНА! 🏆\n\n🥇 ПОБЕДИЛИ: {winner_name.upper()}!\n\n🔪 МАФИЯ ({len(mafia_players)}):\n" + ("\n".join(mafia_list) if mafia_list else "Нет") + "\n\n👨‍🌾 МИРНЫЕ:\n" + ("\n".join(civilian_list) if civilian_list else "Нет"))
    cancel_mafia_timer(game)
    await clear_mafia_mutes(chat_id)
    await send_phase_message(chat_id, game, final_text, None)
    if chat_id in active_mafia_games:
        del active_mafia_games[chat_id]

async def parse_target(target_input: str, current_user_id: int) -> int:
    target_input = target_input.strip()
    try:
        return int(target_input)
    except:
        pass
    if target_input.startswith('@'):
        screen_name = target_input[1:]
        try:
            resolved = await bot.api.utils.resolve_screen_name(screen_name)
            if resolved:
                return resolved.object_id
        except:
            pass
    if target_input.startswith('[id') and '|' in target_input:
        try:
            id_part = target_input.split('|')[0].replace('[id', '')
            return int(id_part)
        except:
            pass
    return None

async def check_bot_dialog(user_id: int) -> bool:
    try:
        await bot.api.messages.send(user_id=user_id, random_id=0, message="🔍")
        return True
    except Exception as e:
        return False

async def ensure_bot_dialog(user_id: int, chat_id: int) -> tuple:
    if await check_bot_dialog(user_id):
        return True, None
    return False, "❌ У вас не начат диалог с ботом! Напишите боту любое сообщение в личные сообщения, чтобы начать диалог, затем попробуйте снова."

# ================== МАФИЯ - ОСНОВНЫЕ ФУНКЦИИ ==================
async def create_mafia_game(chat_id: int, creator_id: int) -> dict:
    if chat_id in active_mafia_games:
        return {"success": False, "message": "В этом чате уже идёт игра в мафию!"}
    has_dialog, error_msg = await ensure_bot_dialog(creator_id, chat_id)
    if not has_dialog:
        return {"success": False, "message": error_msg}
    game = MafiaGame(chat_id, creator_id)
    active_mafia_games[chat_id] = game
    return {"success": True, "game": game}

async def join_mafia_game(chat_id: int, player_id: int) -> dict:
    if chat_id not in active_mafia_games:
        return {"success": False, "message": "Игра не найдена! Создайте игру: /мафия создать"}
    game = active_mafia_games[chat_id]
    if game.status != "waiting":
        return {"success": False, "message": "Игра уже началась! Дождитесь следующей игры."}
    if player_id in game.players:
        return {"success": False, "message": "Вы уже в игре!"}
    has_dialog, error_msg = await ensure_bot_dialog(player_id, chat_id)
    if not has_dialog:
        return {"success": False, "message": error_msg}
    game.players.append(player_id)
    game.alive[player_id] = True
    game.last_action_time = time.time()
    return {"success": True, "players_count": len(game.players)}

async def leave_mafia_game(chat_id: int, player_id: int) -> dict:
    if chat_id not in active_mafia_games:
        return {"success": False, "message": "Игра не найдена!"}
    game = active_mafia_games[chat_id]
    if game.status != "waiting":
        return {"success": False, "message": "Игра уже началась, выйти нельзя!"}
    if player_id not in game.players:
        return {"success": False, "message": "Вы не в игре!"}
    game.players.remove(player_id)
    if player_id in game.alive:
        del game.alive[player_id]
    game.last_action_time = time.time()
    if player_id == game.creator_id and len(game.players) == 0:
        del active_mafia_games[chat_id]
        return {"success": True, "message": "Игра удалена"}
    return {"success": True, "players_count": len(game.players)}

async def start_mafia_game(chat_id: int, creator_id: int):
    if chat_id not in active_mafia_games:
        return {"success": False, "message": "Игра не найдена!"}
    game = active_mafia_games[chat_id]
    if game.creator_id != creator_id:
        return {"success": False, "message": "Только создатель может начать игру!"}
    if game.status != "waiting":
        return {"success": False, "message": "Игра уже началась!"}
    players_count = len(game.players)
    if players_count < MAFIA_MIN_PLAYERS:
        return {"success": False, "message": f"Минимум {MAFIA_MIN_PLAYERS} игрока! Сейчас {players_count}"}
    mafia_count = max(1, players_count // 3)
    if players_count >= 6:
        roles = ["mafia"] * mafia_count + ["civilian"] * (players_count - mafia_count - 2) + ["commissar", "doctor"]
    else:
        roles = ["mafia"] * mafia_count + ["civilian"] * (players_count - mafia_count - 1) + ["commissar"]
    random.shuffle(roles)
    for i, player_id in enumerate(game.players):
        role = roles[i] if i < len(roles) else "civilian"
        game.roles[player_id] = role
        game.alive[player_id] = True
        if role == "mafia":
            game.mafia_count += 1
        else:
            game.civilians_count += 1
    game.status = "active"
    game.day = 1
    game.last_action_time = time.time()
    for player in game.players:
        role = game.roles[player]
        role_data = MAFIA_ROLES.get(role, MAFIA_ROLES["civilian"])
        allies_text = ""
        if role == "mafia":
            mafia_allies = [p for p in game.players if game.roles.get(p) == "mafia" and p != player]
            if mafia_allies:
                allies_list = [await get_user_or_group_mention(a) for a in mafia_allies]
                allies_text = f"\n\n👥 ВАШИ СОЮЗНИКИ:\n" + "\n".join(allies_list)
        role_msg = f"🎭 ВАША РОЛЬ: {role_data['emoji']} {role_data['name']}\n📝 {role_data['description']}{allies_text}\n\n🌙 Скоро начнется ночь..."
        try:
            await bot.api.messages.send(user_id=player, message=role_msg, random_id=0)
        except Exception as e:
            print(f"Не удалось отправить роль {player}: {e}")
    await start_night_phase(chat_id, game)
    return {"success": True}

async def start_night_phase(chat_id: int, game: MafiaGame):
    cancel_mafia_timer(game)
    game.phase = "night"
    game.doctor_saved = None
    game.last_kill = None
    game.mafia_votes = {}
    game.commissar_checked = {}
    game.waiting_for_action = set()
    actions_order = ["doctor", "commissar", "mafia"]
    game.current_action = actions_order[0]
    await sync_mafia_phase_mutes(game)
    players_with_action = [p for p in game.players if game.roles.get(p) == game.current_action and game.alive.get(p, False)]
    if players_with_action:
        game.waiting_for_action = set(players_with_action)
        night_text = f"🌙 НАСТУПИЛА НОЧЬ (День {game.day}) 🌙\n\n👨‍⚕️ Сейчас ход ДОКТОРА!"
        await send_phase_message(chat_id, game, night_text)
        for player in players_with_action:
            await send_action_request(player, game, "save")
        schedule_mafia_timeout(chat_id, game, "night", game.current_action)
    else:
        await next_night_action(chat_id, game)

async def next_night_action(chat_id: int, game: MafiaGame):
    cancel_mafia_timer(game)
    actions_order = ["doctor", "commissar", "mafia"]
    if game.current_action not in actions_order:
        game.current_action = actions_order[0]
    current_index = actions_order.index(game.current_action)
    if current_index + 1 < len(actions_order):
        game.current_action = actions_order[current_index + 1]
        players_with_action = [p for p in game.players if game.roles.get(p) == game.current_action and game.alive.get(p, False)]
        if players_with_action:
            game.waiting_for_action = set(players_with_action)
            action_names = {"doctor": "ДОКТОРА", "commissar": "КОМИССАРА", "mafia": "МАФИИ"}
            night_text = f"🌙 Ночь (День {game.day}) 🌙\n\n🔪 Сейчас ход {action_names.get(game.current_action, game.current_action.upper())}!"
            await send_phase_message(chat_id, game, night_text)
            for player in players_with_action:
                action_type = "save" if game.current_action == "doctor" else "check" if game.current_action == "commissar" else "kill"
                await send_action_request(player, game, action_type)
            schedule_mafia_timeout(chat_id, game, "night", game.current_action)
        else:
            await next_night_action(chat_id, game)
    else:
        await resolve_night_phase(chat_id, game)

async def handle_night_action(game: MafiaGame, player_id: int, target_id: int, action: str):
    if game.phase != "night":
        return {"success": False, "message": "Сейчас не ночь!"}
    if player_id not in game.waiting_for_action:
        return {"success": False, "message": "Сейчас не ваш ход!"}
    role = game.roles.get(player_id)
    if action == "kill" and role == "mafia":
        game.mafia_votes[player_id] = target_id
        game.waiting_for_action.discard(player_id)
        all_mafia = [p for p in game.players if game.roles.get(p) == "mafia" and game.alive.get(p, False)]
        if len(game.mafia_votes) >= len(all_mafia):
            votes_count = {}
            for target in game.mafia_votes.values():
                votes_count[target] = votes_count.get(target, 0) + 1
            max_votes = max(votes_count.values()) if votes_count else 0
            targets = [t for t, v in votes_count.items() if v == max_votes]
            if len(targets) == 1:
                game.last_kill = targets[0]
            else:
                game.last_kill = None
            await next_night_action(game.chat_id, game)
        game.last_action_time = time.time()
        return {"success": True, "message": "Ваш голос учтён!"}
    elif action == "check" and role == "commissar":
        target_role = game.roles.get(target_id)
        is_mafia = target_role == "mafia"
        game.commissar_checked[player_id] = target_id
        game.waiting_for_action.discard(player_id)
        result_text = f"🔍 РЕЗУЛЬТАТ ПРОВЕРКИ:\n\nИгрок: {await get_user_or_group_mention(target_id)}\n{'🔪 МАФИЯ!' if is_mafia else '👨‍🌾 МИРНЫЙ ЖИТЕЛЬ!'}"
        try:
            await bot.api.messages.send(user_id=player_id, message=result_text, random_id=0)
        except:
            pass
        if not game.waiting_for_action:
            await next_night_action(game.chat_id, game)
        game.last_action_time = time.time()
        return {"success": True, "message": "Проверка выполнена!"}
    elif action == "save" and role == "doctor":
        game.doctor_saved = target_id
        game.waiting_for_action.discard(player_id)
        if not game.waiting_for_action:
            await next_night_action(game.chat_id, game)
        game.last_action_time = time.time()
        return {"success": True, "message": f"Вы спасаете {await get_user_or_group_mention(target_id)}!"}
    return {"success": False, "message": "Неверное действие!"}

async def resolve_night_phase(chat_id: int, game: MafiaGame):
    cancel_mafia_timer(game)
    killed = game.last_kill
    if game.doctor_saved and game.doctor_saved == killed:
        killed = None
    if killed:
        game.alive[killed] = False
        if game.roles.get(killed) == "mafia":
            game.mafia_count -= 1
        else:
            game.civilians_count -= 1
    winner = await check_mafia_winner(game)
    if winner:
        await end_game_and_cleanup(chat_id, game, winner)
        return
    night_result = f"🌙 НОЧЬ ЗАКОНЧИЛАСЬ 🌙\n\n{'💀 Убит: ' + await get_user_or_group_mention(killed) if killed else '💀 Никто не убит'}\n\n☀️ НАСТУПАЕТ ДЕНЬ! ☀️"
    await send_phase_message(chat_id, game, night_result)
    await start_day_phase(chat_id, game)

async def start_day_phase(chat_id: int, game: MafiaGame):
    cancel_mafia_timer(game)
    game.phase = "day"
    game.votes = {}
    await sync_mafia_phase_mutes(game)
    game.waiting_for_action = set()
    alive_players = [p for p in game.players if game.alive.get(p, False)]
    if len(alive_players) <= 1:
        winner = "mafia" if game.mafia_count > 0 else "civilian"
        await end_game_and_cleanup(chat_id, game, winner)
        return
    day_text = f"☀️ ДЕНЬ {game.day} ☀️\n\n👥 Живых игроков: {len(alive_players)}\n\n🗳️ Начинается голосование!\nКаждый игрок должен проголосовать за казнь подозреваемого."
    await send_phase_message(chat_id, game, day_text)
    game.waiting_for_action = set(alive_players)
    for player in alive_players:
        await send_action_request(player, game, "vote")
    schedule_mafia_timeout(chat_id, game, "day")

async def handle_day_vote(game: MafiaGame, voter_id: int, target_id: int):
    if game.phase != "day":
        return {"success": False, "message": "Сейчас не день!"}
    if voter_id not in game.waiting_for_action:
        return {"success": False, "message": "Вы уже проголосовали!"}
    if not game.alive.get(target_id, False):
        return {"success": False, "message": "Этот игрок уже мёртв!"}
    if target_id == voter_id:
        return {"success": False, "message": "Нельзя голосовать за себя!"}
    game.votes[voter_id] = target_id
    game.waiting_for_action.discard(voter_id)
    alive_players = [p for p in game.players if game.alive.get(p, False)]
    if len(game.votes) >= len(alive_players):
        votes_count = {}
        for target in game.votes.values():
            votes_count[target] = votes_count.get(target, 0) + 1
        max_votes = max(votes_count.values()) if votes_count else 0
        targets = [t for t, v in votes_count.items() if v == max_votes]
        if len(targets) == 1:
            game.last_lynch = targets[0]
        else:
            game.last_lynch = None
        await resolve_day_phase(game.chat_id, game)
    game.last_action_time = time.time()
    return {"success": True, "message": "Ваш голос учтён!"}

async def resolve_day_votes_timeout(chat_id: int, game: MafiaGame):
    votes_count = {}
    for target in game.votes.values():
        votes_count[target] = votes_count.get(target, 0) + 1
    if votes_count:
        max_votes = max(votes_count.values())
        targets = [target for target, count in votes_count.items() if count == max_votes]
        game.last_lynch = targets[0] if len(targets) == 1 else None
    else:
        game.last_lynch = None
    await resolve_day_phase(chat_id, game)


async def resolve_day_phase(chat_id: int, game: MafiaGame):
    cancel_mafia_timer(game)
    lynched = game.last_lynch
    if lynched:
        game.alive[lynched] = False
        if game.roles.get(lynched) == "mafia":
            game.mafia_count -= 1
        else:
            game.civilians_count -= 1
    winner = await check_mafia_winner(game)
    if winner:
        await end_game_and_cleanup(chat_id, game, winner)
        return
    day_result = f"☀️ ДЕНЬ {game.day} ЗАКОНЧИЛСЯ ☀️\n\n{'⚖️ Казнён: ' + await get_user_or_group_mention(lynched) if lynched else '⚖️ Никто не казнён'}\n\n🌙 НАСТУПАЕТ НОЧЬ! 🌙"
    await send_phase_message(chat_id, game, day_result)
    game.day += 1
    await start_night_phase(chat_id, game)

async def cleanup_inactive_mafia_games():
    while True:
        try:
            current_time = time.time()
            inactive_games = []
            for chat_id, game in active_mafia_games.items():
                if current_time - game.last_action_time > MAFIA_INACTIVE_TIMEOUT:
                    inactive_games.append(chat_id)
                    try:
                        peer_id = 2000000000 + chat_id
                        await bot.api.messages.send(peer_id=peer_id, message=f"⏰ ИГРА В МАФИЮ АВТОМАТИЧЕСКИ ЗАВЕРШЕНА! ⏰\n\nИгра была удалена из-за длительной неактивности (более {MAFIA_INACTIVE_TIMEOUT // 60} минут).\n\nЧтобы начать новую игру, используйте:\n/мафия создать", random_id=0)
                    except:
                        pass
            for chat_id in inactive_games:
                if chat_id in active_mafia_games:
                    game = active_mafia_games[chat_id]
                    cancel_mafia_timer(game)
                    await clear_mafia_mutes(chat_id)
                    del active_mafia_games[chat_id]
                    print(f"Игра в мафию в чате {chat_id} удалена из-за неактивности")
            await asyncio.sleep(60)
        except Exception as e:
            print(f"Ошибка в cleanup_inactive_mafia_games: {e}")
            await asyncio.sleep(60)

# ================== ОБРАБОТЧИК ЛИЧНЫХ СООБЩЕНИЙ ДЛЯ МАФИИ ==================
@bot.on.private_message()
async def on_private_message_mafia(message: Message):
    user_id = message.from_id
    text = message.text.lower().strip() if message.text else ""
    active_game = None
    active_chat_id = None
    for chat_id, game in active_mafia_games.items():
        if user_id in game.players and game.status == "active" and game.alive.get(user_id, False):
            active_game = game
            active_chat_id = chat_id
            break
    if active_game:
        parts = text.split()
        if not parts:
            return True
        command = parts[0]
        role = active_game.roles.get(user_id)
        if command in ['убить', 'kill']:
            if active_game.phase != "night":
                await message.reply("🌙 Убивать можно только ночью!")
                return True
            if active_game.current_action != "mafia":
                await message.reply("⏳ Сейчас не ход мафии!")
                return True
            if role != "mafia":
                await message.reply("🔪 Только мафия может убивать!")
                return True
            if len(parts) < 2:
                keyboard = await get_alive_players_keyboard(active_game, "kill", user_id)
                await message.reply("🔪 Выберите жертву:", keyboard=keyboard)
                return True
            target_id = await parse_target(parts[1], user_id)
            if not target_id:
                await message.reply("❌ Не удалось определить игрока!")
                return True
            result = await handle_night_action(active_game, user_id, target_id, "kill")
            await message.reply(result["message"])
            return True
        elif command in ['проверить', 'check']:
            if active_game.phase != "night":
                await message.reply("🌙 Проверять можно только ночью!")
                return True
            if active_game.current_action != "commissar":
                await message.reply("⏳ Сейчас не ход комиссара!")
                return True
            if role != "commissar":
                await message.reply("👮 Только комиссар может проверять!")
                return True
            if len(parts) < 2:
                keyboard = await get_alive_players_keyboard(active_game, "check", user_id)
                await message.reply("👮 Выберите игрока для проверки:", keyboard=keyboard)
                return True
            target_id = await parse_target(parts[1], user_id)
            if not target_id:
                await message.reply("❌ Не удалось определить игрока!")
                return True
            result = await handle_night_action(active_game, user_id, target_id, "check")
            await message.reply(result["message"])
            return True
        elif command in ['спасти', 'save']:
            if active_game.phase != "night":
                await message.reply("🌙 Лечить можно только ночью!")
                return True
            if active_game.current_action != "doctor":
                await message.reply("⏳ Сейчас не ход доктора!")
                return True
            if role != "doctor":
                await message.reply("👨‍⚕️ Только доктор может лечить!")
                return True
            if len(parts) < 2:
                keyboard = await get_alive_players_keyboard(active_game, "save", user_id)
                await message.reply("👨‍⚕️ Выберите игрока для спасения:", keyboard=keyboard)
                return True
            target_id = await parse_target(parts[1], user_id)
            if not target_id:
                await message.reply("❌ Не удалось определить игрока!")
                return True
            result = await handle_night_action(active_game, user_id, target_id, "save")
            await message.reply(result["message"])
            return True
        elif command in ['казнить', 'lynch']:
            if active_game.phase != "day":
                await message.reply("☀️ Голосовать можно только днём!")
                return True
            if not active_game.alive.get(user_id, False):
                await message.reply("💀 Вы мертвы и не можете голосовать!")
                return True
            if len(parts) < 2:
                keyboard = await get_alive_players_keyboard(active_game, "vote", user_id)
                await message.reply("🗳️ Выберите игрока для казни:", keyboard=keyboard)
                return True
            target_id = await parse_target(parts[1], user_id)
            if not target_id:
                await message.reply("❌ Не удалось определить игрока!")
                return True
            result = await handle_day_vote(active_game, user_id, target_id)
            await message.reply(result["message"])
            return True
        else:
            await message.reply("🎭 КОМАНДЫ МАФИИ:\n\nНочью:\n• убить @игрок - убить (мафия)\n• проверить @игрок - проверить (комиссар)\n• спасти @игрок - спасти (доктор)\n\nДнём:\n• казнить @игрок - голосовать\n\nИспользуйте @упоминание или ID")
            return True




async def parse_target(target_input: str, current_user_id: int) -> int:
    """Распарсить цель из текста"""
    # Убираем @ если есть
    target_input = target_input.strip()

    # Проверяем, может это ID
    try:
        return int(target_input)
    except:
        pass

    # Проверяем упоминание @username
    if target_input.startswith('@'):
        screen_name = target_input[1:]
        try:
            # Пробуем получить ID через API
            resolved = await bot.api.utils.resolve_screen_name(screen_name)
            if resolved:
                return resolved.object_id
        except:
            pass

    # Проверяем формат [id123|name]
    if target_input.startswith('[id') and '|' in target_input:
        try:
            id_part = target_input.split('|')[0].replace('[id', '')
            return int(id_part)
        except:
            pass

    return None


# ================== КОМАНДЫ МАФИИ В ЧАТЕ ==================
# Добавьте эти команды в функцию on_chat_message в соответствующий раздел
# Для отладки можно добавить функцию
async def print_active_duels():
    print(f"Активные дуэли: {current_duel}")


# ================== СИСТЕМА БИЗНЕСОВ ==================

BUSINESS_TYPES = {
    1: {"name": "Комиссионка", "emoji": "📱", "price": 1000000, "min_profit": 250000, "max_profit": 300000},
    2: {"name": "Забегаловка", "emoji": "🥙", "price": 3000000, "min_profit": 300000, "max_profit": 500000},
    3: {"name": "Магазин брендовой одежды", "emoji": "👔", "price": 6000000, "min_profit": 500000, "max_profit": 600000},
    4: {"name": "Ресторан", "emoji": "🍽️", "price": 13000000, "min_profit": 1000000, "max_profit": 2000000},
    5: {"name": "Магазин 24/7", "emoji": "🛍️", "price": 20000000, "min_profit": 2000000, "max_profit": 3000000},
    6: {"name": "АЗС", "emoji": "⛽️", "price": 75000000, "min_profit": 8000000, "max_profit": 11000000},
    7: {"name": "Строительная компания", "emoji": "🏬", "price": 200000000, "min_profit": 20000000,
        "max_profit": 25000000},
    8: {"name": "Казино", "emoji": "🎰", "price": 300000000, "min_profit": 35000000, "max_profit": 40000000},
    9: {"name": "Крупнейший холдинг в СНГ", "emoji": "📈", "price": 500000000, "min_profit": 70000000,
        "max_profit": 85000000},
    10: {"name": "Банк генетического кода и биодизайна", "emoji": "🧪", "price": 650000000, "min_profit": 90000000,
         "max_profit": 100000000},
    11: {"name": "Высокотехнологичные ниши судостроения", "emoji": "🚢", "price": 750000000, "min_profit": 110000000,
         "max_profit": 130000000},
    12: {"name": "SPACE X | Ракетостроение", "emoji": "🚀", "price": 1000000000, "min_profit": 150000000,
         "max_profit": 180000000},
    13: {"name": "Нефтяная вышка", "emoji": "🛢️", "price": 1500000000, "min_profit": 200000000,
         "max_profit": 250000000},
    14: {"name": "Алмазная шахта", "emoji": "💎", "price": 2000000000, "min_profit": 280000000,
         "max_profit": 350000000},
    15: {"name": "Завод по производству электроники", "emoji": "📺", "price": 2500000000, "min_profit": 350000000,
         "max_profit": 420000000},
    16: {"name": "Авиакомпания", "emoji": "✈️", "price": 3500000000, "min_profit": 450000000,
         "max_profit": 550000000},
    17: {"name": "Телекоммуникационная компания", "emoji": "📡", "price": 5000000000, "min_profit": 600000000,
         "max_profit": 750000000},
    18: {"name": "Сеть отелей", "emoji": "🏨", "price": 7000000000, "min_profit": 850000000,
         "max_profit": 1000000000},
    19: {"name": "Фармацевтическая корпорация", "emoji": "💊", "price": 10000000000, "min_profit": 1200000000,
         "max_profit": 1500000000},
    20: {"name": "Международный финансовый холдинг", "emoji": "🏦", "price": 15000000000, "min_profit": 1800000000,
         "max_profit": 2200000000},
}


async def get_user_businesses(user_id: int) -> list:
    """Получить список бизнесов пользователя"""
    try:
        sql.execute("""
            SELECT ub.*, 
                   COALESCE(bt.name, 'Неизвестный бизнес') as name,
                   COALESCE(bt.emoji, '🏢') as emoji,
                   COALESCE(bt.min_profit, 0) as min_profit,
                   COALESCE(bt.max_profit, 0) as max_profit
            FROM user_businesses ub
            LEFT JOIN business_types bt ON ub.biz_id = bt.biz_id
            WHERE ub.user_id = ?
            ORDER BY ub.biz_id
        """, (user_id,))
        return sql.fetchall()
    except Exception as e:
        print(f"Ошибка в get_user_businesses: {e}")
        return []


async def get_business_by_id(user_id: int, biz_id: int) -> tuple:
    """Получить конкретный бизнес пользователя"""
    sql.execute("""
        SELECT ub.*, bt.name, bt.emoji, bt.min_profit, bt.max_profit 
        FROM user_businesses ub
        JOIN business_types bt ON ub.biz_id = bt.biz_id
        WHERE ub.user_id = ? AND ub.biz_id = ?
    """, (user_id, biz_id))
    return sql.fetchone()


async def buy_business(user_id: int, biz_id: int) -> dict:
    """Купить бизнес"""
    # Проверяем, существует ли такой тип бизнеса
    if biz_id not in BUSINESS_TYPES:
        return {"success": False, "message": "Такого бизнеса не существует!"}

    # Проверяем, не куплен ли уже этот бизнес
    sql.execute("SELECT id FROM user_businesses WHERE user_id = ? AND biz_id = ?", (user_id, biz_id))
    if sql.fetchone():
        return {"success": False,
                "message": f"У вас уже есть {BUSINESS_TYPES[biz_id]['emoji']} {BUSINESS_TYPES[biz_id]['name']}!"}

    # Проверяем баланс
    price = BUSINESS_TYPES[biz_id]["price"]
    balance = await get_balance(user_id)
    if balance < price:
        return {"success": False, "message": f"Недостаточно средств! Нужно: {price:,}₽"}

    # Покупаем
    current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')
    await setmoney(user_id, -price)

    sql.execute("""
        INSERT INTO user_businesses (user_id, biz_id, purchase_date, last_collected, balance)
        VALUES (?, ?, ?, ?, 0)
    """, (user_id, biz_id, current_time, current_time))

    database.commit()

    await log_economy(user_id=user_id, target_id=None, amount=price,
                      log=f"купил бизнес {BUSINESS_TYPES[biz_id]['name']}")

    return {"success": True,
            "message": f"✅ Вы успешно купили {BUSINESS_TYPES[biz_id]['emoji']} {BUSINESS_TYPES[biz_id]['name']}!"}


async def sell_business(user_id: int, biz_id: int) -> dict:
    """Продать бизнес (получить 70% от стоимости)"""
    business = await get_business_by_id(user_id, biz_id)
    if not business:
        return {"success": False, "message": "У вас нет такого бизнеса!"}

    price = BUSINESS_TYPES[biz_id]["price"]
    refund = int(price * 0.7)  # Возвращаем 70%
    balance = business[5]  # текущий баланс бизнеса

    # Удаляем бизнес
    sql.execute("DELETE FROM user_businesses WHERE user_id = ? AND biz_id = ?", (user_id, biz_id))

    # Возвращаем деньги за продажу + баланс бизнеса
    total_return = refund + balance
    await setmoney(user_id, total_return)

    database.commit()

    await log_economy(user_id=user_id, target_id=None, amount=total_return,
                      log=f"продал бизнес {BUSINESS_TYPES[biz_id]['name']} за {refund}₽ + баланс {balance}₽")

    return {"success": True,
            "message": f"✅ Вы продали {BUSINESS_TYPES[biz_id]['emoji']} {BUSINESS_TYPES[biz_id]['name']} и получили {refund:,}₽ + баланс {balance:,}₽"}


async def collect_business_profit(user_id: int, biz_id: int) -> dict:
    """Собрать прибыль с бизнеса"""
    business = await get_business_by_id(user_id, biz_id)
    if not business:
        return {"success": False, "message": "У вас нет такого бизнеса!"}

    # Распаковываем данные
    # id, user_id, biz_id, purchase_date, last_collected, balance, name, emoji, min_profit, max_profit
    last_collected = business[4]
    current_balance = business[5]
    biz_name = business[6]
    biz_emoji = business[7]
    min_profit = business[8]
    max_profit = business[9]

    # Проверяем, можно ли собрать прибыль (раз в 24 часа)
    last_time = datetime.strptime(last_collected, '%Y-%m-%d %H:%M:%S.%f')
    current_time = moscow_now()
    time_diff = current_time - last_time

    hours_passed = time_diff.total_seconds() / 3600

    if hours_passed < 24:
        hours_left = 24 - hours_passed
        hours = int(hours_left)
        minutes = int((hours_left - hours) * 60)
        return {
            "success": False,
            "message": f"⏰ До следующего сбора прибыли осталось: {hours} ч {minutes} мин!",
            "balance": current_balance
        }

    # Рассчитываем прибыль за прошедшие дни
    days_passed = int(hours_passed // 24)
    if days_passed < 1:
        days_passed = 1

    total_profit = 0
    for _ in range(days_passed):
        profit = random.randint(min_profit, max_profit)
        total_profit += profit

    # Обновляем баланс бизнеса и время последнего сбора
    new_balance = current_balance + total_profit
    current_time_str = current_time.strftime('%Y-%m-%d %H:%M:%S.%f')

    sql.execute("""
        UPDATE user_businesses 
        SET balance = ?, last_collected = ? 
        WHERE user_id = ? AND biz_id = ?
    """, (new_balance, current_time_str, user_id, biz_id))

    database.commit()

    return {
        "success": True,
        "message": f"✅ Прибыль с {biz_emoji} {biz_name} за {days_passed} дн.: +{total_profit:,}₽",
        "new_balance": new_balance,
        "profit": total_profit
    }


async def withdraw_business_profit(user_id: int, biz_id: int, amount: int = None) -> dict:
    """Снять деньги с бизнеса"""
    business = await get_business_by_id(user_id, biz_id)
    if not business:
        return {"success": False, "message": "У вас нет такого бизнеса!"}

    current_balance = business[5]

    if current_balance <= 0:
        return {"success": False, "message": "На счету бизнеса нет денег!"}

    # Если сумма не указана, снимаем всё
    if amount is None or amount <= 0:
        amount = current_balance
    else:
        if amount > current_balance:
            return {"success": False, "message": f"На счету бизнеса только {current_balance:,}₽!"}

    # Снимаем деньги
    new_balance = current_balance - amount
    sql.execute("""
        UPDATE user_businesses SET balance = ? 
        WHERE user_id = ? AND biz_id = ?
    """, (new_balance, user_id, biz_id))

    # Начисляем пользователю
    await setmoney(user_id, amount)

    database.commit()

    biz_emoji = business[7]
    biz_name = business[6]

    await log_economy(user_id=user_id, target_id=None, amount=amount,
                      log=f"снял {amount}₽ с бизнеса {biz_name}")

    return {
        "success": True,
        "message": f"✅ Вы сняли {amount:,}₽ с {biz_emoji} {biz_name}",
        "withdrawn": amount,
        "new_balance": new_balance
    }


# ================== СИСТЕМА РАБОТ ==================

JOBS_DATA = {
    1: {
        "name": "Механик",
        "description": "Ремонтируешь автомобили в местном автосервисе",
        "min_skill": 0,
        "salary": 15000,
        "skill_gain": 3,
        "cooldown_hours": 3
    },
    2: {
        "name": "Продавец",
        "description": "Работаешь в супермаркете, обслуживаешь покупателей",
        "min_skill": 15,
        "salary": 30000,
        "skill_gain": 5,
        "cooldown_hours": 3
    },
    3: {
        "name": "Строитель",
        "description": "Работаешь на стройке, возводишь новые здания",
        "min_skill": 30,
        "salary": 45000,
        "skill_gain": 7,
        "cooldown_hours": 3
    },
    4: {
        "name": "Водитель такси",
        "description": "Возить людей по городу, хороший заработок",
        "min_skill": 50,
        "salary": 55000,
        "skill_gain": 10,
        "cooldown_hours": 3
    },
    5: {
        "name": "Прокурор",
        "description": "Выдвигаешь обвинение в суде против обвиняемого",
        "min_skill": 100,
        "salary": 100000,
        "skill_gain": 13,
        "cooldown_hours": 3
    },
    6: {
        "name": "Программист",
        "description": "Пишешь код для крупного IT-проекта",
        "min_skill": 250,
        "salary": 150000,
        "skill_gain": 25,
        "cooldown_hours": 3
    },
    7: {
        "name": "Риелтор",
        "description": "Занимаешься подбором и продажей квартир и домов",
        "min_skill": 450,
        "salary": 300000,
        "skill_gain": 30,
        "cooldown_hours": 3
    },
    8: {
        "name": "Менеджер",
        "description": "Управляешь отделом в крупной компании",
        "min_skill": 600,
        "salary": 350000,
        "skill_gain": 40,
        "cooldown_hours": 3
    },
    9: {
        "name": "Директор",
        "description": "Управляешь собственной компанией",
        "min_skill": 750,
        "salary": 500000,
        "skill_gain": 50,
        "cooldown_hours": 3
    },
    10: {
        "name": "Депутат",
        "description": "Представитель Государственной Думы, решает проблемы граждан",
        "min_skill": 1000,
        "salary": 1000000,
        "skill_gain": 80,
        "cooldown_hours": 3
    },
    11: {
        "name": "Судья",
        "description": "Рассматриваешь сложные дела и выносишь судебные решения",
        "min_skill": 1400,
        "salary": 1400000,
        "skill_gain": 100,
        "cooldown_hours": 3
    },
    12: {
        "name": "Главный врач",
        "description": "Руководишь крупной больницей и отвечаешь за работу персонала",
        "min_skill": 1900,
        "salary": 1900000,
        "skill_gain": 125,
        "cooldown_hours": 3
    },
    13: {
        "name": "Пилот",
        "description": "Управляешь пассажирским самолётом на международных рейсах",
        "min_skill": 2500,
        "salary": 2600000,
        "skill_gain": 155,
        "cooldown_hours": 3
    },
    14: {
        "name": "Архитектор",
        "description": "Проектируешь крупные жилые комплексы и деловые центры",
        "min_skill": 3300,
        "salary": 3500000,
        "skill_gain": 190,
        "cooldown_hours": 3
    },
    15: {
        "name": "Инженер космических систем",
        "description": "Разрабатываешь оборудование для ракет и орбитальных станций",
        "min_skill": 4300,
        "salary": 4700000,
        "skill_gain": 230,
        "cooldown_hours": 3
    },
    16: {
        "name": "Министр",
        "description": "Руководишь государственным ведомством и крупными проектами",
        "min_skill": 5600,
        "salary": 6200000,
        "skill_gain": 280,
        "cooldown_hours": 3
    },
    17: {
        "name": "Генеральный директор",
        "description": "Управляешь международной корпорацией и тысячами сотрудников",
        "min_skill": 7200,
        "salary": 8000000,
        "skill_gain": 340,
        "cooldown_hours": 3
    },
    18: {
        "name": "Инвестбанкир",
        "description": "Проводишь многомиллиардные сделки и управляешь капиталом клиентов",
        "min_skill": 9200,
        "salary": 10500000,
        "skill_gain": 410,
        "cooldown_hours": 3
    },
    19: {
        "name": "Владелец корпорации",
        "description": "Развиваешь собственную международную бизнес-империю",
        "min_skill": 11800,
        "salary": 14000000,
        "skill_gain": 500,
        "cooldown_hours": 3
    },
    20: {
        "name": "Космонавт",
        "description": "Участвуешь в межпланетных экспедициях и научных миссиях",
        "min_skill": 15000,
        "salary": 20000000,
        "skill_gain": 650,
        "cooldown_hours": 3
    }
}


def load_data(file):
    if os.path.exists(file):
        try:
            with open(file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


balances = load_data(BALANCES_FILE)


def get_balanc(user_id: int):
    uid = str(user_id)
    if uid not in balances:
        balances[uid] = {
            "won": 0,
            "lost": 0,
            "won_total": 0,
            "lost_total": 0,
            "received_total": 0,
            "sent_total": 0,

        }
    return balances[uid]


async def delete_clan(clan_id: int) -> dict:
    """Полностью удалить клан"""
    try:
        # Удаляем все связанные данные
        sql.execute("DELETE FROM clan_members WHERE clan_id = ?", (clan_id,))
        sql.execute("DELETE FROM clan_invites WHERE clan_id = ?", (clan_id,))
        sql.execute(
            "DELETE FROM clan_battles WHERE war_id IN (SELECT war_id FROM clan_wars WHERE clan1_id = ? OR clan2_id = ?)",
            (clan_id, clan_id))
        sql.execute("DELETE FROM clan_wars WHERE clan1_id = ? OR clan2_id = ?", (clan_id, clan_id))
        sql.execute("DELETE FROM clans WHERE clan_id = ?", (clan_id,))

        database.commit()
        return {"success": True, "message": "Клан успешно удалён"}
    except Exception as e:
        print(f"Ошибка при удалении клана: {e}")
        return {"success": False, "message": f"Ошибка при удалении клана: {e}"}


async def get_logic(number=int):
    if number < 1:
        return False
    else:
        return True


# Добавьте эту функцию для проверки
def check_table_structure():
    sql.execute("PRAGMA table_info(users)")
    columns = sql.fetchall()
    print("Структура таблицы users:")
    for col in columns:
        print(f"  {col[1]} ({col[2]})")


for f in [BALANCES_FILE]:
    if not os.path.exists(f):
        with open(f, "w", encoding="utf-8") as fp:
            json.dump({}, fp)


async def can_work(user_id: int) -> tuple:
    """Алиас для check_work"""
    return await check_work(user_id)


async def get_role_appointment_date(user_id=int, chat_id=int):
    """Получить дату назначения на роль модератора"""
    try:
        sql.execute(f"SELECT appointment_date FROM role_appointments WHERE user_id = ? AND chat_id = ?",
                    (user_id, chat_id))
        fetch = sql.fetchone()
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


async def create_role_appointments_table():
    """Создать таблицу для хранения дат назначения ролей"""
    sql.execute("""
        CREATE TABLE IF NOT EXISTS role_appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id BIGINT NOT NULL,
            chat_id BIGINT NOT NULL,
            role_level INTEGER NOT NULL,
            appointment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, chat_id)
        )
    """)
    database.commit()
    print("Таблица role_appointments создана/проверена")


async def set_role_appointment_date(user_id=int, chat_id=int, role_level=int):
    """Установить/обновить дату назначения роли"""
    try:
        # Проверяем, есть ли уже запись
        sql.execute(f"SELECT * FROM role_appointments WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        existing = sql.fetchone()

        current_time = moscow_now().strftime('%Y-%m-%d')

        if existing:
            # Обновляем существующую запись
            sql.execute("""
                UPDATE role_appointments 
                SET role_level = ?, appointment_date = ?
                WHERE user_id = ? AND chat_id = ?
            """, (role_level, current_time, user_id, chat_id))
        else:
            # Создаем новую запись
            sql.execute("""
                INSERT INTO role_appointments (user_id, chat_id, role_level, appointment_date)
                VALUES (?, ?, ?, ?)
            """, (user_id, chat_id, role_level, current_time))

        database.commit()
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
            else:
                return False
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


async def find_clans_by_name(query: str, limit: int = 5) -> list:
    """Найти кланы по названию"""
    sql.execute(
        "SELECT clan_id, name, tag, level, members_count FROM clans WHERE name LIKE ? ORDER BY level DESC LIMIT ?",
        (f"%{query}%", limit))
    return sql.fetchall()


def get_string(words_list, start_index=0):
    result = " ".join(words_list[start_index:])
    return result if result else False


database = sqlite3.connect('database1.db')
sql = database.cursor()


# ================== СИСТЕМА КЛАНОВ ==================
async def create_clan(leader_id: int, name: str, tag: str) -> dict:
    """Создать новый клан"""
    # Проверяем, не состоит ли пользователь уже в клане
    if await get_user_clan(leader_id):
        return {"success": False, "message": "Вы уже состоите в клане!"}

    # Проверяем уникальность названия и тега
    sql.execute("SELECT clan_id FROM clans WHERE name = ? OR tag = ?", (name, tag))
    if sql.fetchone():
        return {"success": False, "message": "Клан с таким названием или тегом уже существует!"}

    current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')

    # Создаём клан
    sql.execute("INSERT INTO clans (name, tag, leader_id, bank, created_date) VALUES (?, ?, ?, 0, ?)",
                (name, tag, leader_id, current_time))

    # Получаем ID последней вставленной записи
    clan_id = sql.lastrowid

    # Добавляем лидера
    sql.execute("INSERT INTO clan_members (user_id, clan_id, role, joined_date, donated) VALUES (?, ?, 'leader', ?, 0)",
                (leader_id, clan_id, current_time))

    database.commit()

    return {"success": True, "clan_id": clan_id, "message": f"Клан '{name}' успешно создан!"}


async def get_user_clan(user_id: int) -> dict:
    """Получить информацию о клане пользователя"""
    sql.execute("""
        SELECT c.*, cm.role, cm.joined_date, cm.donated 
        FROM clans c 
        JOIN clan_members cm ON c.clan_id = cm.clan_id 
        WHERE cm.user_id = ?
    """, (user_id,))

    row = sql.fetchone()
    if not row:
        return None

    # Получаем названия колонок
    columns = [description[0] for description in sql.description]
    clan_data = dict(zip(columns, row))

    return clan_data


async def get_clan_by_id(clan_id: int) -> dict:
    """Получить информацию о клане по ID"""
    sql.execute("SELECT * FROM clans WHERE clan_id = ?", (clan_id,))
    row = sql.fetchone()
    if not row:
        return None

    columns = [description[0] for description in sql.description]
    return dict(zip(columns, row))


async def get_clan_members(clan_id: int) -> list:
    """Получить список участников клана"""
    sql.execute("""
        SELECT user_id, role, joined_date, donated 
        FROM clan_members 
        WHERE clan_id = ? 
        ORDER BY 
            CASE role 
                WHEN 'leader' THEN 1 
                WHEN 'deputy' THEN 2 
                ELSE 3 
            END, donated DESC
    """, (clan_id,))

    return sql.fetchall()


async def add_clan_member(clan_id: int, user_id: int, inviter_id: int) -> dict:
    """Добавить участника в клан"""
    # Проверяем, не в клане ли уже пользователь
    if await get_user_clan(user_id):
        return {"success": False, "message": "Пользователь уже состоит в клане!"}

    # Проверяем лимит участников (уровень клана влияет на лимит)
    clan = await get_clan_by_id(clan_id)
    max_members = 10 + (clan["level"] * 5)  # 1 уровень - 15, 2 - 20 и т.д.

    sql.execute("SELECT COUNT(*) FROM clan_members WHERE clan_id = ?", (clan_id,))
    current_members = sql.fetchone()[0]

    if current_members >= max_members:
        return {"success": False, "message": f"Достигнут лимит участников клана ({max_members})!"}

    current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')

    sql.execute("INSERT INTO clan_members (user_id, clan_id, role, joined_date, donated) VALUES (?, ?, 'member', ?, 0)",
                (user_id, clan_id, current_time))

    # Обновляем счетчик участников
    sql.execute("UPDATE clans SET members_count = members_count + 1 WHERE clan_id = ?", (clan_id,))

    database.commit()

    return {"success": True, "message": "Пользователь добавлен в клан!"}


async def remove_clan_member(user_id: int, clan_id: int) -> dict:
    """Удалить участника из клана"""
    # Проверяем, не лидер ли
    sql.execute("SELECT role FROM clan_members WHERE user_id = ? AND clan_id = ?", (user_id, clan_id))
    role = sql.fetchone()

    if role and role[0] == 'leader':
        return {"success": False, "message": "Нельзя удалить лидера клана! Передайте права другому участнику."}

    sql.execute("DELETE FROM clan_members WHERE user_id = ? AND clan_id = ?", (user_id, clan_id))
    sql.execute("UPDATE clans SET members_count = members_count - 1 WHERE clan_id = ?", (clan_id,))

    database.commit()

    return {"success": True, "message": "Участник удалён из клана!"}


async def transfer_leadership(clan_id: int, new_leader_id: int, old_leader_id: int) -> dict:
    """Передать права лидера"""
    # Проверяем, что новый лидер в клане
    sql.execute("SELECT role FROM clan_members WHERE user_id = ? AND clan_id = ?", (new_leader_id, clan_id))
    if not sql.fetchone():
        return {"success": False, "message": "Новый лидер не состоит в клане!"}

    # Меняем роли
    sql.execute("UPDATE clan_members SET role = 'member' WHERE user_id = ? AND clan_id = ?", (old_leader_id, clan_id))
    sql.execute("UPDATE clan_members SET role = 'leader' WHERE user_id = ? AND clan_id = ?", (new_leader_id, clan_id))
    sql.execute("UPDATE clans SET leader_id = ? WHERE clan_id = ?", (new_leader_id, clan_id))

    database.commit()

    return {"success": True, "message": "Права лидера успешно переданы!"}


async def add_clan_exp(clan_id: int, exp: int):
    """Добавить опыт клану и проверить повышение уровня"""
    # Получаем текущие данные клана
    clan = await get_clan_by_id(clan_id)
    if not clan:
        return False
    
    current_exp = clan["exp"] + exp
    level = clan["level"]
    
    # Формула: каждый уровень требует (level * 1000) опыта
    # Но опыт накапливается между уровнями
    exp_needed_for_next_level = level * 1000
    
    # Обновляем опыт
    sql.execute("UPDATE clans SET exp = ? WHERE clan_id = ?", (current_exp, clan_id))
    
    # Проверяем повышение уровня
    if current_exp >= exp_needed_for_next_level:
        # Повышаем уровень и переносим лишний опыт
        excess_exp = current_exp - exp_needed_for_next_level
        new_level = level + 1
        sql.execute("UPDATE clans SET level = ?, exp = ? WHERE clan_id = ?",
                    (new_level, excess_exp, clan_id))
        database.commit()
        return True  # Повысили уровень
    
    database.commit()
    return False


async def create_clan_invite(clan_id: int, inviter_id: int, target_id: int) -> dict:
    """Создать приглашение в клан"""
    # Проверяем, не приглашали ли уже
    sql.execute("SELECT * FROM clan_invites WHERE clan_id = ? AND user_id = ?", (clan_id, target_id))
    if sql.fetchone():
        return {"success": False, "message": "Приглашение уже отправлено!"}

    current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')

    sql.execute("INSERT INTO clan_invites (clan_id, user_id, inviter_id, date) VALUES (?, ?, ?, ?)",
                (clan_id, target_id, inviter_id, current_time))

    database.commit()

    return {"success": True, "message": "Приглашение отправлено!"}


async def get_clan_invites(user_id: int) -> list:
    """Получить все приглашения пользователя"""
    sql.execute("""
        SELECT ci.*, c.name, c.tag 
        FROM clan_invites ci
        JOIN clans c ON ci.clan_id = c.clan_id
        WHERE ci.user_id = ?
    """, (user_id,))

    return sql.fetchall()


async def accept_clan_invite(invite_id: int, user_id: int) -> dict:
    """Принять приглашение в клан"""
    # Получаем информацию о приглашении
    sql.execute("SELECT clan_id FROM clan_invites WHERE invite_id = ? AND user_id = ?", (invite_id, user_id))
    invite = sql.fetchone()

    if not invite:
        return {"success": False, "message": "Приглашение не найдено!"}

    clan_id = invite[0]

    # Добавляем в клан
    result = await add_clan_member(clan_id, user_id, user_id)
    if result["success"]:
        # Удаляем приглашение
        sql.execute("DELETE FROM clan_invites WHERE invite_id = ?", (invite_id,))
        database.commit()

    return result


async def get_top_clans(limit: int = 10) -> list:
    """Получить топ кланов"""
    sql.execute("""
        SELECT clan_id, name, tag, level, exp, bank, members_count, wins, losses 
        FROM clans 
        ORDER BY level DESC, exp DESC, wins DESC 
        LIMIT ?
    """, (limit,))

    return sql.fetchall()


async def clan_deposit(user_id: int, clan_id: int, amount: int) -> dict:
    """Положить деньги в казну клана"""
    balance = await get_balance(user_id)

    if balance < amount:
        return {"success": False, "message": "Недостаточно средств!"}

    if amount < 1000:
        return {"success": False, "message": "Минимальная сумма пополнения: 1000₽"}

    # Снимаем у пользователя
    await setmoney(user_id, -amount)

    # Добавляем в казну
    sql.execute("UPDATE clans SET bank = bank + ? WHERE clan_id = ?", (amount, clan_id))

    # Обновляем статистику пожертвований
    sql.execute("UPDATE clan_members SET donated = donated + ? WHERE user_id = ? AND clan_id = ?",
                (amount, user_id, clan_id))

    # 🔒 ЗАЩИТА ОТ НАКРУТКИ: опыт начисляется только от 1% от суммы
    # Это предотвращает накрутку через снятие/положение денег
    exp_gain = amount // 100  # 1% от суммы идёт в опыт клана
    
    # Добавляем опыт клану за пожертвование
    if exp_gain > 0:
        await add_clan_exp(clan_id, exp_gain)

    database.commit()

    await log_economy(user_id=user_id, target_id=None, amount=amount, log=f"положил в казну клана {amount}₽")

    return {"success": True, "message": f"Вы положили {amount}₽ в казну клана! Клан получил {exp_gain} опыта."}


async def clan_withdraw(user_id: int, clan_id: int, amount: int) -> dict:
    """Снять деньги из казны (только лидер или зам)"""
    # Проверяем права
    sql.execute("SELECT role FROM clan_members WHERE user_id = ? AND clan_id = ?", (user_id, clan_id))
    role = sql.fetchone()

    if not role or role[0] not in ['leader', 'deputy']:
        return {"success": False, "message": "Только лидер и его заместитель могут снимать из казны!"}

    # Проверяем достаточно ли в казне
    clan = await get_clan_by_id(clan_id)
    if clan["bank"] < amount:
        return {"success": False, "message": f"В казне недостаточно средств! Доступно: {clan['bank']}₽"}

    # Снимаем из казны
    sql.execute("UPDATE clans SET bank = bank - ? WHERE clan_id = ?", (amount, clan_id))

    # Комиссия 10%
    commission = amount // 10
    actual_amount = amount - commission

    # Начисляем пользователю за вычетом комиссии
    await setmoney(user_id, actual_amount)

    database.commit()

    await log_economy(user_id=user_id, target_id=None, amount=amount, log=f"снял из казны клана {amount}₽ (комиссия {commission}₽)")

    return {"success": True, "message": f"Вы сняли {amount}₽ из казны клана! Коммисия - 10%\n\nИтого: {actual_amount}₽"}


async def create_clan_war(clan1_id: int, clan2_id: int, bet: int, creator_id: int) -> dict:
    """Создать клановую войну"""
    # Проверяем, что создатель - лидер клана
    clan1 = await get_clan_by_id(clan1_id)
    if clan1["leader_id"] != creator_id:
        return {"success": False, "message": "Только лидер клана может объявить войну!"}

    # Проверяем ставку
    if clan1["bank"] < bet:
        return {"success": False, "message": f"В казне клана недостаточно средств! Доступно: {clan1['bank']}₽"}

    clan2 = await get_clan_by_id(clan2_id)
    if clan2["bank"] < bet:
        return {"success": False, "message": f"У клана-противника недостаточно средств в казне!"}

    # Проверяем, нет ли уже активной войны
    sql.execute("""
        SELECT * FROM clan_wars 
        WHERE ((clan1_id = ? OR clan2_id = ?) AND status IN ('pending', 'active'))
    """, (clan1_id, clan1_id))

    if sql.fetchone():
        return {"success": False, "message": "У вашего клана уже есть активная война!"}

    current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')

    sql.execute("""
        INSERT INTO clan_wars (clan1_id, clan2_id, bet, status, start_time) 
        VALUES (?, ?, ?, 'pending', ?)
    """, (clan1_id, clan2_id, bet, current_time))

    war_id = sql.lastrowid
    database.commit()

    return {"success": True, "war_id": war_id, "message": "Война создана! Ожидайте подтверждения противника."}


async def accept_clan_war(war_id: int, clan_id: int) -> dict:
    """Принять клановую войну"""
    sql.execute("SELECT * FROM clan_wars WHERE war_id = ? AND clan2_id = ? AND status = 'pending'",
                (war_id, clan_id))
    war = sql.fetchone()

    if not war:
        return {"success": False, "message": "Война не найдена или уже принята!"}

    # Получаем названия колонок
    columns = [description[0] for description in sql.description]
    war_data = dict(zip(columns, war))

    # Проверяем наличие средств
    clan2 = await get_clan_by_id(clan_id)
    if clan2["bank"] < war_data["bet"]:
        return {"success": False, "message": "В казне клана недостаточно средств для участия в войне!"}

    # Блокируем ставки в казне
    sql.execute("UPDATE clans SET bank = bank - ? WHERE clan_id = ?", (war_data["bet"], clan_id))
    sql.execute("UPDATE clans SET bank = bank - ? WHERE clan_id = ?", (war_data["bet"], war_data["clan1_id"]))

    # Начинаем войну
    current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')
    sql.execute("""
        UPDATE clan_wars 
        SET status = 'active', start_time = ? 
        WHERE war_id = ?
    """, (current_time, war_id))

    database.commit()

    return {"success": True, "message": "Война принята! Сражения начинаются!"}


async def create_clan_battle(war_id: int, user1_id: int, user2_id: int, bet: int) -> dict:
    """Создать сражение между участниками кланов"""
    # Проверяем, что оба участника в своих кланах
    user1_clan = await get_user_clan(user1_id)
    user2_clan = await get_user_clan(user2_id)

    if not user1_clan or not user2_clan:
        return {"success": False, "message": "Один из участников не состоит в клане!"}

    # Проверяем, что пользователи из разных кланов
    if user1_clan["clan_id"] == user2_clan["clan_id"]:
        return {"success": False, "message": "Нельзя сражаться с одноклановцем!"}

    # Проверяем, существует ли война и активна ли она
    sql.execute("SELECT status, clan1_id, clan2_id FROM clan_wars WHERE war_id = ?", (war_id,))
    war = sql.fetchone()

    if not war:
        return {"success": False, "message": "Война не найдена!"}

    if war[0] != "active":
        return {"success": False, "message": "Война не активна!"}

    # Проверяем, что пользователи из враждующих кланов
    clan1_id = war[1]
    clan2_id = war[2]

    if user1_clan["clan_id"] not in [clan1_id, clan2_id] or user2_clan["clan_id"] not in [clan1_id, clan2_id]:
        return {"success": False, "message": "Участники не из враждующих кланов!"}

    if user1_clan["clan_id"] == user2_clan["clan_id"]:
        return {"success": False, "message": "Участники должны быть из разных кланов!"}

    # Проверяем, нет ли уже активного сражения между этими пользователями
    sql.execute("""
        SELECT battle_id FROM clan_battles 
        WHERE war_id = ? AND status = 'pending' 
        AND ((user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?))
    """, (war_id, user1_id, user2_id, user2_id, user1_id))

    if sql.fetchone():
        return {"success": False, "message": "Вы уже вызвали этого пользователя на дуэль!"}

    current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')

    sql.execute("""
        INSERT INTO clan_battles (war_id, user1_id, user2_id, bet, status, created_at) 
        VALUES (?, ?, ?, ?, 'pending', ?)
    """, (war_id, user1_id, user2_id, bet, current_time))

    battle_id = sql.lastrowid
    database.commit()

    return {"success": True, "battle_id": battle_id}

async def finish_clan_battle(battle_id: int, winner_id: int) -> dict:
    """Завершить сражение и обновить счёт (деньги в казну клана)"""
    sql.execute("SELECT * FROM clan_battles WHERE battle_id = ?", (battle_id,))
    battle = sql.fetchone()

    if not battle:
        return {"success": False, "message": "Сражение не найдено!"}

    columns = [description[0] for description in sql.description]
    battle_data = dict(zip(columns, battle))

    if battle_data["status"] != "pending":
        return {"success": False, "message": "Сражение уже завершено!"}

    # Определяем, какому клану принадлежит победитель
    sql.execute("SELECT clan_id FROM clan_members WHERE user_id = ?", (winner_id,))
    winner_clan = sql.fetchone()

    sql.execute("SELECT clan1_id, clan2_id, bet FROM clan_wars WHERE war_id = ?", (battle_data["war_id"],))
    war = sql.fetchone()
    war_bet = war[2]  # ставка за всю войну

    # Обновляем счёт в войне
    if winner_clan[0] == war[0]:
        # Победил клан1
        sql.execute("UPDATE clan_wars SET clan1_score = clan1_score + 1 WHERE war_id = ?", (battle_data["war_id"],))
    else:
        # Победил клан2
        sql.execute("UPDATE clan_wars SET clan2_score = clan2_score + 1 WHERE war_id = ?", (battle_data["war_id"],))

    sql.execute("UPDATE clan_battles SET status = 'finished', winner_id = ? WHERE battle_id = ?",
                (winner_id, battle_id))

    # 💰💰💰 НАЧИСЛЯЕМ ДЕНЬГИ В КАЗНУ КЛАНА ПОБЕДИТЕЛЯ 💰💰💰
    # Ставка за дуэль идёт в казну клана, а не личный баланс
    clan_id = winner_clan[0]
    sql.execute("UPDATE clans SET bank = bank + ? WHERE clan_id = ?", (battle_data["bet"], clan_id))

    # Добавляем опыт клану за победу в дуэли
    exp_gain = battle_data["bet"] // 20  # 5% от ставки
    await add_clan_exp(clan_id, exp_gain)

    database.commit()

    return {"success": True, "message": "Сражение завершено! Деньги поступили в казну клана."}

async def check_war_end(war_id: int) -> dict:
    """Проверить, не закончилась ли война"""
    sql.execute("SELECT * FROM clan_wars WHERE war_id = ?", (war_id,))
    war = sql.fetchone()

    if not war:
        return {"finished": False}

    columns = [description[0] for description in sql.description]
    war_data = dict(zip(columns, war))

    # Война заканчивается, когда одна из сторон набирает 5 побед
    if war_data.get("clan1_score", 0) >= 5 or war_data.get("clan2_score", 0) >= 5:
        winner_id = war_data["clan1_id"] if war_data.get("clan1_score", 0) >= 5 else war_data["clan2_id"]
        loser_id = war_data["clan2_id"] if winner_id == war_data["clan1_id"] else war_data["clan1_id"]

        total_bet = war_data["bet"] * 2

        # Победитель получает всё в казну
        sql.execute("UPDATE clans SET bank = bank + ?, wins = wins + 1 WHERE clan_id = ?",
                    (total_bet, winner_id))
        sql.execute("UPDATE clans SET losses = losses + 1 WHERE clan_id = ?", (loser_id,))

        # Добавляем опыт за войну
        await add_clan_exp(winner_id, total_bet // 10)

        current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')
        sql.execute("""
            UPDATE clan_wars 
            SET status = 'finished', winner_id = ?, end_time = ? 
            WHERE war_id = ?
        """, (winner_id, current_time, war_id))

        database.commit()

        winner_clan = await get_clan_by_id(winner_id)
        loser_clan = await get_clan_by_id(loser_id)

        return {
            "finished": True,
            "winner": winner_clan["name"],
            "winner_id": winner_id,
            "loser": loser_clan["name"],
            "total_bet": total_bet
        }

    return {"finished": False}

async def check_chat(chat_id=int):
    sql.execute(f"SELECT * FROM chats WHERE chat_id = {chat_id}")
    if sql.fetchone() == None:
        return False
    else:
        return True


async def log_economy(user_id=None, target_id=None, amount=None, log=None):
    try:
        sql.execute(
            "INSERT INTO economy (user_id, target_id, amount, log) VALUES (?, ?, ?, ?)",
            (user_id, target_id, amount, log)
        )
        database.commit()
        print(f"[ECONOMY LOG] {user_id} -> {target_id} | {amount} | {log}")
    except Exception as e:
        print(f"[ECONOMY LOG ERROR] {e}")


async def chats_log(user_id=None, target_id=None, role=None, log=None):
    try:
        sql.execute(
            "INSERT INTO logchats (user_id, target_id, role, log) VALUES (?, ?, ?, ?)",
            (user_id, target_id, role, log)
        )
        database.commit()
        print(f"[CHATS LOG] {user_id} -> {target_id} | {role} | {log}")
    except Exception as e:
        print(f"[CHATS LOG ERROR] {e}")


# 🔧 МИГРАЦИЯ: Исправление аномального опыта в кланах
try:
    sql.execute("SELECT clan_id, level, exp FROM clans")
    clans_data = sql.fetchall()
    fixed_count = 0
    for clan in clans_data:
        clan_id, level, exp = clan
        exp_needed_for_next_level = level * 1000
        # Если опыт больше или равен требуемому для следующего уровня — исправляем
        if exp >= exp_needed_for_next_level:
            excess_exp = exp - exp_needed_for_next_level
            # Вычисляем сколько уровней можно повысить
            extra_levels = 0
            remaining_exp = excess_exp
            current_level = level + 1
            while remaining_exp >= (current_level + 1) * 1000:
                extra_levels += 1
                remaining_exp -= (current_level + 1) * 1000
                current_level += 1
            
            new_level = level + 1 + extra_levels
            new_exp = remaining_exp
            
            sql.execute("UPDATE clans SET level = ?, exp = ? WHERE clan_id = ?",
                        (new_level, new_exp, clan_id))
            print(f"[CLAN FIX] Исправлен опыт клана {clan_id}: level {level}→{new_level}, exp {exp}→{new_exp}")
            fixed_count += 1
    
    if fixed_count > 0:
        database.commit()
        print(f"[CLAN MIGRATION] Исправлено {fixed_count} кланов с аномальным опытом")
except Exception as e:
    print(f"[CLAN MIGRATION ERROR] {e}")


# ВРЕМЕННЫЙ КОД - запустите один раз для исправления базы данных
async def fix_businesses():
    # Проверяем и добавляем недостающие бизнесы в business_types
    missing_businesses = [
        (9, "Крупнейший холдинг в СНГ", "📈", 500000000, 70000000, 85000000, "Крупнейший холдинг"),
        (10, "Банк генетического кода и биодизайна", "🧪", 650000000, 90000000, 100000000, "Биотехнологии"),
        (11, "Высокотехнологичные ниши судостроения", "🚢", 750000000, 110000000, 130000000, "Судостроение"),
        (12, "SPACE X | Ракетостроение", "🚀", 1000000000, 150000000, 180000000, "Космические технологии"),
        (13, "Нефтяная вышка", "🛢️", 1500000000, 200000000, 250000000, "Добыча нефти"),
        (14, "Алмазная шахта", "💎", 2000000000, 280000000, 350000000, "Добыча драгоценных камней"),
        (15, "Завод по производству электроники", "📺", 2500000000, 350000000, 420000000, "Производство техники"),
        (16, "Авиакомпания", "✈️", 3500000000, 450000000, 550000000, "Пассажирские перевозки"),
        (17, "Телекоммуникационная компания", "📡", 5000000000, 600000000, 750000000, "Связь и интернет"),
        (18, "Сеть отелей", "🏨", 7000000000, 850000000, 1000000000, "Гостиничный бизнес"),
        (19, "Фармацевтическая корпорация", "💊", 10000000000, 1200000000, 1500000000, "Производство лекарств"),
        (20, "Международный финансовый холдинг", "🏦", 15000000000, 1800000000, 2200000000, "Финансовые услуги"),
    ]

    for biz in missing_businesses:
        try:
            # Проверяем, есть ли уже такая запись
            sql.execute("SELECT biz_id FROM business_types WHERE biz_id = ?", (biz[0],))
            if not sql.fetchone():
                sql.execute(
                    "INSERT INTO business_types (biz_id, name, emoji, price, min_profit, max_profit, description) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    biz
                )
                print(f"Добавлен бизнес: {biz[1]}")
        except Exception as e:
            print(f"Ошибка при добавлении бизнеса {biz[1]}: {e}")

    database.commit()
    print("Проверка бизнесов завершена!")


# Запустите эту функцию один раз
# asyncio.run(fix_businesses())

async def buy_business(user_id: int, biz_id: int) -> dict:
    """Купить бизнес"""
    # Проверяем, существует ли такой тип бизнеса
    if biz_id not in BUSINESS_TYPES:
        return {"success": False, "message": "Такого бизнеса не существует!"}

    # Проверяем, есть ли бизнес в таблице business_types
    sql.execute("SELECT * FROM business_types WHERE biz_id = ?", (biz_id,))
    if not sql.fetchone():
        return {"success": False, "message": "Ошибка: бизнес не найден в базе данных!"}

    # Проверяем, не куплен ли уже этот бизнес
    sql.execute("SELECT id FROM user_businesses WHERE user_id = ? AND biz_id = ?", (user_id, biz_id))
    if sql.fetchone():
        return {"success": False,
                "message": f"У вас уже есть {BUSINESS_TYPES[biz_id]['emoji']} {BUSINESS_TYPES[biz_id]['name']}!"}

    # Проверяем баланс
    price = BUSINESS_TYPES[biz_id]["price"]
    balance = await get_balance(user_id)
    if balance < price:
        return {"success": False, "message": f"Недостаточно средств! Нужно: {price:,}₽"}

    # Покупаем
    current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')
    await setmoney(user_id, -price)

    sql.execute("""
        INSERT INTO user_businesses (user_id, biz_id, purchase_date, last_collected, balance)
        VALUES (?, ?, ?, ?, 0)
    """, (user_id, biz_id, current_time, current_time))

    database.commit()

    await log_economy(user_id=user_id, target_id=None, amount=price,
                      log=f"купил бизнес {BUSINESS_TYPES[biz_id]['name']}")

    # Проверяем, что бизнес действительно добавился
    sql.execute("SELECT * FROM user_businesses WHERE user_id = ? AND biz_id = ?", (user_id, biz_id))
    if sql.fetchone():
        return {"success": True,
                "message": f"✅ Вы успешно купили {BUSINESS_TYPES[biz_id]['emoji']} {BUSINESS_TYPES[biz_id]['name']}!"}
    else:
        return {"success": False, "message": "❌ Ошибка при сохранении бизнеса в базе данных!"}


async def new_chat(chat_id=int, peer_id=int, owner_id=int):
    sql.execute(f"INSERT INTO chats VALUES (?, ?, ?, '', 0, 0, 0, 0, 0, 0, 0, 0);", (chat_id, peer_id, owner_id))
    sql.execute(f"CREATE TABLE IF NOT EXISTS permissions_{chat_id} (user_id BIGINT, level BIGINT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS balance (user_id BIGINT, money BIGINT, blago BIGINT, bank BIGINT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS staffbot (user_id BIGINT, level BIGINT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS ruk (user_id BIGINT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS logsrole (user BIGINT, role BIGINT, chat_id BIfGINT, date_string TEXT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS economy (user_id INTEGER, target_id INTEGER, amount INTEGER, log TEXT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS logchats (user_id INTEGER, target_id INTEGER, role INTEGER, log TEXT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS rules (chat_id BIGINT, text Text);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS info (chat_id BIGINT, text Text);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS banschats (chat_id BIGINT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS photosettings (chat_id BIGINT NOT NULL PRIMARY KEY,mode INT NOT NULL);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS usprom (user_id BIGINT, promo TEXT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS vip (user_id BIGINT, date_string TEXT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS nicks_{chat_id} (user_id BIGINT, nick TEXT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS promo (promo TEXT, status TEXT, vip BIGINT, money BIGINT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS banwords_{chat_id} (banword TEXT);")
    sql.execute(
        f"CREATE TABLE IF NOT EXISTS warns_{chat_id} (user_id BIGINT, count BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
    sql.execute(
        f"CREATE TABLE IF NOT EXISTS vig_{chat_id} (user_id BIGINT, count BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
    sql.execute(
        f"CREATE TABLE IF NOT EXISTS mutes_{chat_id} (user_id BIGINT, moder TEXT, reason TEXT, date BIGINT, date_string TEXT, time BIGINT);")
    sql.execute(
        f"CREATE TABLE IF NOT EXISTS bans_{chat_id} (user_id BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
    sql.execute(
        f"CREATE TABLE IF NOT EXISTS gbans (user_id BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
    sql.execute(
        f"CREATE TABLE IF NOT EXISTS messages_{chat_id} (user_id BIGINT, date BIGINT, date_string TEXT, message_id BIGINT, cmid BIGINT);")
    sql.execute(
        f'CREATE TABLE IF NOT EXISTS users (user_id BIGINT, last_bonus TIMESTAMP DEFAULT NULL);')
    sql.execute(
        f"CREATE TABLE IF NOT EXISTS warnhistory_{chat_id} (user_id BIGINT, count BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
    sql.execute(
        f"CREATE TABLE IF NOT EXISTS vighistory_{chat_id} (user_id BIGINT, count BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS punishments_{chat_id} (user_id BIGINT, date TEXT);")
    sql.execute(
        f"CREATE TABLE IF NOT EXISTS jobs (user_id BIGINT PRIMARY KEY, job_id INTEGER, skill INTEGER, last_work_time TEXT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS user_skills (user_id BIGINT PRIMARY KEY, skill INTEGER);")
    sql.execute("CREATE TABLE IF NOT EXISTS clans ("
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

    sql.execute("CREATE TABLE IF NOT EXISTS clan_members ("
                "user_id BIGINT PRIMARY KEY, "
                "clan_id INTEGER, "
                "role TEXT DEFAULT 'member', "  # leader, deputy, member
                "joined_date TEXT, "
                "donated BIGINT DEFAULT 0, "
                "FOREIGN KEY(clan_id) REFERENCES clans(clan_id))")

    sql.execute("CREATE TABLE IF NOT EXISTS clan_wars ("
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

    sql.execute("CREATE TABLE IF NOT EXISTS clan_invites ("
                "invite_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "clan_id INTEGER, "
                "user_id BIGINT, "
                "inviter_id BIGINT, "
                "date TEXT, "
                "FOREIGN KEY(clan_id) REFERENCES clans(clan_id))")

    # Найдите в new_chat этот блок и замените:
    sql.execute("CREATE TABLE IF NOT EXISTS clan_battles ("
                "battle_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "war_id INTEGER, "
                "user1_id BIGINT, "
                "user2_id BIGINT, "
                "winner_id BIGINT DEFAULT NULL, "
                "bet BIGINT, "
                "status TEXT DEFAULT 'pending', "
                "created_at TEXT, "
                "FOREIGN KEY(war_id) REFERENCES clan_wars(war_id))")
    sql.execute(
        "CREATE TABLE IF NOT EXISTS jobs (user_id BIGINT PRIMARY KEY, job_id INTEGER, skill INTEGER DEFAULT 0, last_work_time TEXT)")
    sql.execute("CREATE TABLE IF NOT EXISTS business_types ("
                "biz_id INTEGER PRIMARY KEY, "
                "name TEXT, "
                "emoji TEXT, "
                "price BIGINT, "
                "min_profit BIGINT, "
                "max_profit BIGINT, "
                "description TEXT)")

    # Добавьте в функцию new_chat после создания других таблиц
    sql.execute("CREATE TABLE IF NOT EXISTS marriages ("
                "marriage_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "user1_id BIGINT NOT NULL, "
                "user2_id BIGINT NOT NULL, "
                "proposal_date TEXT NOT NULL, "
                "marriage_date TEXT, "
                "status TEXT DEFAULT 'pending', "  # pending, accepted, rejected, divorced
                "initiator_id BIGINT NOT NULL, "
                "divorce_date TEXT, "
                "UNIQUE(user1_id, user2_id))")

    sql.execute("CREATE TABLE IF NOT EXISTS marriage_proposals ("
                "proposal_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "from_id BIGINT NOT NULL, "
                "to_id BIGINT NOT NULL, "
                "proposal_date TEXT NOT NULL, "
                "status TEXT DEFAULT 'pending')")  # pending, accepted, rejected

    sql.execute("CREATE TABLE IF NOT EXISTS user_businesses ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "user_id BIGINT, "
                "biz_id INTEGER, "
                "purchase_date TEXT, "
                "last_collected TEXT, "
                "balance BIGINT DEFAULT 0, "
                "FOREIGN KEY(biz_id) REFERENCES business_types(biz_id), "
                "UNIQUE(user_id, biz_id))")
    # Добавьте в функцию new_chat после существующих CREATE TABLE
    sql.execute("CREATE TABLE IF NOT EXISTS houses ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "user_id BIGINT NOT NULL, "
                "house_id INTEGER NOT NULL, "
                "purchase_date TEXT NOT NULL, "
                "UNIQUE(user_id, house_id))")

    sql.execute("CREATE TABLE IF NOT EXISTS cars ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "user_id BIGINT NOT NULL, "
                "car_id INTEGER NOT NULL, "
                "purchase_date TEXT NOT NULL, "
                "UNIQUE(user_id, car_id))")
    database.commit()

    # Заполняем таблицу типов бизнесов, если она пустая
    # Заполняем таблицу типов бизнесов, если она пустая
    sql.execute("SELECT COUNT(*) FROM business_types")
    if sql.fetchone()[0] == 0:
        businesses = [
            (1, "Комиссионка", "📱", 1000000, 250000, 300000, "Небольшой магазин подержанных товаров"),
            (2, "Забегаловка", "🥙", 3000000, 300000, 500000, "Быстрое питание на каждый день"),
            (3, "Магазин брендовой одежды", "👔", 6000000, 500000, 600000, "Элитная одежда от мировых брендов"),
            (4, "Ресторан", "🍽️", 13000000, 1000000, 2000000, "Изысканная кухня и дорогой интерьер"),
            (5, "Магазин 24/7", "🛍️", 20000000, 2000000, 3000000, "Круглосуточный универмаг"),
            (6, "АЗС", "⛽️", 75000000, 8000000, 11000000, "Сеть автозаправочных станций"),
            (7, "Строительная компания", "🏬", 200000000, 20000000, 25000000,
             "Возведение жилых и коммерческих объектов"),
            (8, "Казино", "🎰", 300000000, 35000000, 40000000, "Игорный дом с высокими ставками"),
            (9, "Крупнейший холдинг в СНГ", "📈", 500000000, 70000000, 85000000, "Крупнейший холдинг"),
            (10, "Банк генетического кода и биодизайна", "🧪", 650000000, 90000000, 100000000, "Биотехнологии"),
            (11, "Высокотехнологичные ниши судостроения", "🚢", 750000000, 110000000, 130000000, "Судостроение"),
            (12, "SPACE X | Ракетостроение", "🚀", 1000000000, 150000000, 180000000, "Космические технологии"),
            (13, "Нефтяная вышка", "🛢️", 1500000000, 200000000, 250000000, "Добыча нефти"),
            (14, "Алмазная шахта", "💎", 2000000000, 280000000, 350000000, "Добыча драгоценных камней"),
            (15, "Завод по производству электроники", "📺", 2500000000, 350000000, 420000000, "Производство техники"),
            (16, "Авиакомпания", "✈️", 3500000000, 450000000, 550000000, "Пассажирские перевозки"),
            (17, "Телекоммуникационная компания", "📡", 5000000000, 600000000, 750000000, "Связь и интернет"),
            (18, "Сеть отелей", "🏨", 7000000000, 850000000, 1000000000, "Гостиничный бизнес"),
            (19, "Фармацевтическая корпорация", "💊", 10000000000, 1200000000, 1500000000, "Производство лекарств"),
            (20, "Международный финансовый холдинг", "🏦", 15000000000, 1800000000, 2200000000, "Финансовые услуги"),
        ]
        for biz in businesses:
            sql.execute(
                "INSERT INTO business_types (biz_id, name, emoji, price, min_profit, max_profit, description) VALUES (?, ?, ?, ?, ?, ?, ?)",
                biz)
    database.commit()


# ================== СИСТЕМА ДОМОВ ==================
HOUSES_DATA = {
    1: {"name": "Коробка", "emoji": "📦", "price": 25000},
    2: {"name": "Шалаш", "emoji": "🪵", "price": 75000},
    3: {"name": "Старый дом", "emoji": "🏚", "price": 150000},
    4: {"name": "Деревянный дом", "emoji": "🏡", "price": 350000},
    5: {"name": "Маленький дом", "emoji": "🏠", "price": 800000},
    6: {"name": "Дача", "emoji": "🏘", "price": 1500000},
    7: {"name": "Квартира", "emoji": "🏢", "price": 3000000},
    8: {"name": "Загородный дом", "emoji": "🏡", "price": 6000000},
    9: {"name": "Коттедж", "emoji": "🏠", "price": 12000000},
    10: {"name": "Таунхаус", "emoji": "🏘", "price": 25000000},
    11: {"name": "Большой коттедж", "emoji": "🏡", "price": 55000000},
    12: {"name": "Современный дом", "emoji": "🏠", "price": 120000000},
    13: {"name": "Дом у озера", "emoji": "🏘", "price": 250000000},
    14: {"name": "Вилла", "emoji": "🌴", "price": 600000000},
    15: {"name": "Вилла у моря", "emoji": "🌅", "price": 1200000000},
    16: {"name": "Особняк", "emoji": "🏛", "price": 2500000000},
    17: {"name": "Роскошный особняк", "emoji": "🏛", "price": 5500000000},
    18: {"name": "Пентхаус", "emoji": "🌇", "price": 12000000000},
    19: {"name": "Тропическая вилла", "emoji": "🌴", "price": 28000000000},
    20: {"name": "Замок", "emoji": "🏰", "price": 65000000000},
    21: {"name": "Средневековый замок", "emoji": "🏰", "price": 150000000000},
    22: {"name": "Огромный замок", "emoji": "🏰", "price": 350000000000},
    23: {"name": "Частный остров", "emoji": "🏝", "price": 800000000000},
    24: {"name": "Остров Эпштейна", "emoji": "🏝️", "price": 1000000000000},
    25: {"name": "Остров с виллой", "emoji": "🏝", "price": 1800000000000},
    26: {"name": "Королевский дворец", "emoji": "🏰", "price": 4000000000000},
    27: {"name": "Частный архипелаг", "emoji": "🌍", "price": 9000000000000},
    28: {"name": "Космическая станция", "emoji": "🪐", "price": 20000000000000},
    29: {"name": "База на Луне", "emoji": "🌕", "price": 50000000000000},
    30: {"name": "Колония на Марсе", "emoji": "🔴", "price": 120000000000000},
    31: {"name": "Галактический дворец", "emoji": "🌌", "price": 300000000000000},
}

# ================== СИСТЕМА МАШИН ==================
CARS_DATA = {
    1: {"name": "Самокат", "emoji": "🛴", "price": 5000},
    2: {"name": "Велосипед", "emoji": "🚲", "price": 15000},
    3: {"name": "Скутер", "emoji": "🛵", "price": 40000},
    4: {"name": "Запорожец", "emoji": "🚗", "price": 120000},
    5: {"name": "ВАЗ-2107", "emoji": "🚗", "price": 250000},
    6: {"name": "Lada Granta", "emoji": "🚗", "price": 600000},
    7: {"name": "Lada Vesta", "emoji": "🚗", "price": 1200000},
    8: {"name": "Hyundai Solaris", "emoji": "🚗", "price": 2000000},
    9: {"name": "Kia Rio", "emoji": "🚗", "price": 2500000},
    10: {"name": "Toyota Corolla", "emoji": "🚗", "price": 3500000},
    11: {"name": "Toyota Camry", "emoji": "🚗", "price": 6000000},
    12: {"name": "BMW 3 Series", "emoji": "🚙", "price": 9000000},
    13: {"name": "Mercedes-Benz C-Class", "emoji": "🚙", "price": 12000000},
    14: {"name": "Audi A6", "emoji": "🚙", "price": 16000000},
    15: {"name": "BMW X5", "emoji": "🚙", "price": 25000000},
    16: {"name": "Mercedes-Benz G-Class", "emoji": "🚙", "price": 45000000},
    17: {"name": "Porsche Cayenne", "emoji": "🚗", "price": 70000000},
    18: {"name": "Porsche 911", "emoji": "🚗", "price": 120000000},
    19: {"name": "Nissan GT-R", "emoji": "🚗", "price": 180000000},
    20: {"name": "Lamborghini Huracán", "emoji": "🚗", "price": 350000000},
    21: {"name": "Ferrari 488", "emoji": "🚗", "price": 600000000},
    22: {"name": "McLaren 720S", "emoji": "🚗", "price": 1000000000},
    23: {"name": "Lamborghini Aventador", "emoji": "🚗", "price": 1800000000},
    24: {"name": "Bugatti Veyron", "emoji": "🚗", "price": 4000000000},
    25: {"name": "Bugatti Chiron", "emoji": "🚗", "price": 9000000000},
    26: {"name": "Rolls-Royce Phantom", "emoji": "🚗", "price": 20000000000},
    27: {"name": "Золотой Lamborghini", "emoji": "🚗", "price": 50000000000},
    28: {"name": "Бронированный лимузин", "emoji": "🚗", "price": 120000000000},
    29: {"name": "Летающий автомобиль", "emoji": "🚀", "price": 300000000000},
    30: {"name": "Инопланетный гиперкар", "emoji": "🛸", "price": 1000000000000},
}


# ================== ФУНКЦИИ ДЛЯ ДОМОВ ==================
async def get_user_houses(user_id: int) -> list:
    """Получить список домов пользователя"""
    try:
        sql.execute("SELECT * FROM houses WHERE user_id = ? ORDER BY house_id", (user_id,))
        return sql.fetchall()
    except Exception as e:
        print(f"Ошибка в get_user_houses: {e}")
        return []


async def get_user_houses_count(user_id: int) -> int:
    """Получить количество домов пользователя"""
    houses = await get_user_houses(user_id)
    return len(houses)


async def buy_house(user_id: int, house_id: int) -> dict:
    """Купить дом"""
    if house_id not in HOUSES_DATA:
        return {"success": False, "message": "❌ Такого дома не существует!"}

    # Проверяем, есть ли уже такой дом
    sql.execute("SELECT id FROM houses WHERE user_id = ? AND house_id = ?", (user_id, house_id))
    if sql.fetchone():
        return {"success": False,
                "message": f"❌ У вас уже есть {HOUSES_DATA[house_id]['emoji']} {HOUSES_DATA[house_id]['name']}!"}

    price = HOUSES_DATA[house_id]["price"]
    balance = await get_balance(user_id)

    if balance < price:
        return {"success": False, "message": f"❌ Недостаточно средств! Нужно: {price:,}₽"}

    # Покупаем
    current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')
    await setmoney(user_id, -price)

    sql.execute("INSERT INTO houses (user_id, house_id, purchase_date) VALUES (?, ?, ?)",
                (user_id, house_id, current_time))
    database.commit()

    await log_economy(user_id=user_id, target_id=None, amount=price,
                      log=f"купил дом {HOUSES_DATA[house_id]['name']}")

    return {"success": True,
            "message": f"✅ Вы успешно купили {HOUSES_DATA[house_id]['emoji']} {HOUSES_DATA[house_id]['name']}!"}


async def sell_house(user_id: int, house_id: int) -> dict:
    """Продать дом (получить 70% от стоимости)"""
    # Проверяем, есть ли такой дом у пользователя
    sql.execute("SELECT * FROM houses WHERE user_id = ? AND house_id = ?", (user_id, house_id))
    if not sql.fetchone():
        return {"success": False, "message": "❌ У вас нет такого дома!"}

    price = HOUSES_DATA[house_id]["price"]
    refund = int(price * 0.7)  # Возвращаем 70%

    # Удаляем дом
    sql.execute("DELETE FROM houses WHERE user_id = ? AND house_id = ?", (user_id, house_id))

    # Возвращаем деньги
    await setmoney(user_id, refund)
    database.commit()

    await log_economy(user_id=user_id, target_id=None, amount=refund,
                      log=f"продал дом {HOUSES_DATA[house_id]['name']} за {refund}₽")

    return {"success": True,
            "message": f"✅ Вы продали {HOUSES_DATA[house_id]['emoji']} {HOUSES_DATA[house_id]['name']} и получили {refund:,}₽"}


async def get_most_expensive_house(user_id: int) -> dict:
    """Получить самый дорогой дом пользователя"""
    houses = await get_user_houses(user_id)
    if not houses:
        return None

    most_expensive = None
    max_price = 0

    for house in houses:
        house_id = house[2]
        price = HOUSES_DATA[house_id]["price"]
        if price > max_price:
            max_price = price
            most_expensive = HOUSES_DATA[house_id]

    return most_expensive


# ================== ФУНКЦИИ ДЛЯ МАШИН ==================
async def get_user_cars(user_id: int) -> list:
    """Получить список машин пользователя"""
    try:
        sql.execute("SELECT * FROM cars WHERE user_id = ? ORDER BY car_id", (user_id,))
        return sql.fetchall()
    except Exception as e:
        print(f"Ошибка в get_user_cars: {e}")
        return []


async def get_user_cars_count(user_id: int) -> int:
    """Получить количество машин пользователя"""
    cars = await get_user_cars(user_id)
    return len(cars)


async def buy_car(user_id: int, car_id: int) -> dict:
    """Купить машину"""
    if car_id not in CARS_DATA:
        return {"success": False, "message": "❌ Такой машины не существует!"}

    # Проверяем, есть ли уже такая машина
    sql.execute("SELECT id FROM cars WHERE user_id = ? AND car_id = ?", (user_id, car_id))
    if sql.fetchone():
        return {"success": False,
                "message": f"❌ У вас уже есть {CARS_DATA[car_id]['emoji']} {CARS_DATA[car_id]['name']}!"}

    price = CARS_DATA[car_id]["price"]
    balance = await get_balance(user_id)

    if balance < price:
        return {"success": False, "message": f"❌ Недостаточно средств! Нужно: {price:,}₽"}

    # Покупаем
    current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')
    await setmoney(user_id, -price)

    sql.execute("INSERT INTO cars (user_id, car_id, purchase_date) VALUES (?, ?, ?)",
                (user_id, car_id, current_time))
    database.commit()

    await log_economy(user_id=user_id, target_id=None, amount=price,
                      log=f"купил машину {CARS_DATA[car_id]['name']}")

    return {"success": True,
            "message": f"✅ Вы успешно купили {CARS_DATA[car_id]['emoji']} {CARS_DATA[car_id]['name']}!"}


async def sell_car(user_id: int, car_id: int) -> dict:
    """Продать машину (получить 70% от стоимости)"""
    # Проверяем, есть ли такая машина у пользователя
    sql.execute("SELECT * FROM cars WHERE user_id = ? AND car_id = ?", (user_id, car_id))
    if not sql.fetchone():
        return {"success": False, "message": "❌ У вас нет такой машины!"}

    price = CARS_DATA[car_id]["price"]
    refund = int(price * 0.7)  # Возвращаем 70%

    # Удаляем машину
    sql.execute("DELETE FROM cars WHERE user_id = ? AND car_id = ?", (user_id, car_id))

    # Возвращаем деньги
    await setmoney(user_id, refund)
    database.commit()

    await log_economy(user_id=user_id, target_id=None, amount=refund,
                      log=f"продал машину {CARS_DATA[car_id]['name']} за {refund}₽")

    return {"success": True,
            "message": f"✅ Вы продали {CARS_DATA[car_id]['emoji']} {CARS_DATA[car_id]['name']} и получили {refund:,}₽"}


async def get_most_expensive_car(user_id: int) -> dict:
    """Получить самую дорогую машину пользователя"""
    cars = await get_user_cars(user_id)
    if not cars:
        return None

    most_expensive = None
    max_price = 0

    for car in cars:
        car_id = car[2]
        price = CARS_DATA[car_id]["price"]
        if price > max_price:
            max_price = price
            most_expensive = CARS_DATA[car_id]

    return most_expensive




def ensure_top_whitelist_table():
    sql.execute("CREATE TABLE IF NOT EXISTS top_whitelist (user_id INTEGER PRIMARY KEY)")
    database.commit()


async def get_top_excluded_ids() -> set:
    excluded = set(await ruklist() or [])
    try:
        sql.execute("SELECT user_id FROM global_managers WHERE level >= 1")
        excluded.update(row[0] for row in sql.fetchall())
    except sqlite3.Error:
        pass
    ensure_top_whitelist_table()
    sql.execute("SELECT user_id FROM top_whitelist")
    excluded.update(row[0] for row in sql.fetchall())
    return excluded

# ================== ФУНКЦИИ ДЛЯ ТОПА ИМУЩЕСТВА ==================
async def calculate_user_wealth(user_id: int) -> int:
    """Рассчитать общее состояние пользователя (деньги + банк + дома + машины)"""

    # Стоимость домов
    houses = await get_user_houses(user_id)
    houses_value = sum(HOUSES_DATA[house[2]]["price"] for house in houses if house[2] in HOUSES_DATA)

    # Стоимость машин
    cars = await get_user_cars(user_id)
    cars_value = sum(CARS_DATA[car[2]]["price"] for car in cars if car[2] in CARS_DATA)

    total = houses_value + cars_value
    return total


async def top_wealth(limit: int = 10) -> str:
    """Топ 10 самых богатых игроков по общему состоянию"""
    # Получаем всех пользователей с балансом
    sql.execute("SELECT DISTINCT user_id FROM balance")
    users = sql.fetchall()

    wealth_list = []
    excluded_users = await get_top_excluded_ids()

    for user in users:
        user_id = user[0]
        if user_id in excluded_users:
            continue

        total = await calculate_user_wealth(user_id)
        if total > 0:
            wealth_list.append((user_id, total))

    # Сортируем по убыванию
    wealth_list.sort(key=lambda x: x[1], reverse=True)

    # Берем топ
    top_10 = wealth_list[:limit]

    result = '💰 ТОП 10 БОГАТЫХ ИМУЩЕСТВОМ:\n\n'
    for i, (user_id, total) in enumerate(top_10):
        total_formatted = f'{total:,d}'.replace(',', '.')
        result += f'{i + 1}. {await get_user_or_group_mention(user_id)} — {total_formatted}₽\n'

    return result


async def get_user_job(user_id: int) -> dict:
    """Получить информацию о работе пользователя"""
    try:
        sql.execute("SELECT job_id, skill, last_work_time FROM jobs WHERE user_id = ?", (user_id,))
        fetch = sql.fetchone()
        if fetch:
            return {
                "job_id": fetch[0],
                "skill": fetch[1] if fetch[1] is not None else 0,
                "last_work_time": fetch[2]
            }
        return None
    except Exception as e:
        print(f"Ошибка в get_user_job для user_id {user_id}: {e}")
        return None


async def check_work(user_id: int) -> tuple:
    """Проверка, может ли пользователь работать сейчас"""
    try:
        sql.execute("SELECT last_work_time FROM jobs WHERE user_id = ?", (user_id,))
        fetch = sql.fetchone()

        if not fetch or not fetch[0]:
            return True, 0, 0

        last_time = datetime.strptime(fetch[0], '%Y-%m-%d %H:%M:%S.%f')
        current_time = moscow_now()
        time_diff = current_time - last_time

        cooldown_hours = 3  # Фиксированный КД 3 часа для всех работ
        cooldown_seconds = cooldown_hours * 3600

        if time_diff.total_seconds() >= cooldown_seconds:
            return True, 0, 0
        else:
            remaining = cooldown_seconds - time_diff.total_seconds()
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            return False, hours, minutes
    except Exception as e:
        print(f"Ошибка при проверке времени работы для user_id {user_id}: {e}")
        return True, 0, 0


async def set_user_job(user_id: int, job_id: int):
    """Установить работу пользователю с сохранением навыка"""
    try:
        # Проверяем, есть ли уже запись
        sql.execute("SELECT skill, last_work_time FROM jobs WHERE user_id = ?", (user_id,))
        fetch = sql.fetchone()

        current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')

        if fetch:
            # Сохраняем текущий навык, но обновляем работу
            current_skill = fetch[0] if fetch[0] is not None else 0
            last_work_time = fetch[1]  # Сохраняем время последней работы!
            sql.execute("UPDATE jobs SET job_id = ?, skill = ?, last_work_time = ? WHERE user_id = ?",
                        (job_id, current_skill, last_work_time, user_id))
        else:
            # Новая запись
            sql.execute("INSERT INTO jobs (user_id, job_id, skill, last_work_time) VALUES (?, ?, 0, ?)",
                        (user_id, job_id, current_time))
        database.commit()
    except Exception as e:
        print(f"Ошибка в set_user_job для user_id {user_id}: {e}")


async def update_clan_battles_table():
    """Обновляет таблицу clan_battles, добавляя колонку created_at"""
    try:
        sql.execute("PRAGMA table_info(clan_battles)")
        columns = sql.fetchall()
        column_names = [col[1] for col in columns]

        if 'created_at' not in column_names:
            sql.execute("ALTER TABLE clan_battles ADD COLUMN created_at TEXT")
            database.commit()
            print("Добавлена колонка created_at в clan_battles")

        print("✅ Таблица clan_battles обновлена!")
    except Exception as e:
        print(f"Ошибка при обновлении clan_battles: {e}")

async def update_user_skill(user_id: int, skill_gain: int):
    """Обновить навык пользователя"""
    try:
        sql.execute("UPDATE jobs SET skill = skill + ? WHERE user_id = ?", (skill_gain, user_id))
        database.commit()
    except Exception as e:
        print(f"Ошибка в update_user_skill для user_id {user_id}: {e}")


async def update_last_work_time(user_id: int):
    """Обновить время последней работы"""
    try:
        current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')
        sql.execute("UPDATE jobs SET last_work_time = ? WHERE user_id = ?", (current_time, user_id))
        database.commit()
    except Exception as e:
        print(f"Ошибка в update_last_work_time для user_id {user_id}: {e}")


async def get_user_skill(user_id: int) -> int:
    """Получить сохранённый навык пользователя"""
    # Сначала проверяем в таблице jobs
    sql.execute("SELECT skill FROM jobs WHERE user_id = ?", (user_id,))
    fetch = sql.fetchone()
    if fetch:
        return fetch[0]

    # Если нет, проверяем в таблице сохранённых навыков
    sql.execute("SELECT skill FROM user_skills WHERE user_id = ?", (user_id,))
    fetch = sql.fetchone()
    if fetch:
        return fetch[0]

    return 0


async def can_work(user_id: int) -> tuple:
    """
    Проверить, может ли пользователь работать сейчас
    Возвращает (can_work, hours_left, minutes_left)
    """
    job_data = await get_user_job(user_id)
    if not job_data or not job_data["last_work_time"]:
        return True, 0, 0

    try:
        last_time = datetime.strptime(job_data["last_work_time"], '%Y-%m-%d %H:%M:%S.%f')
        current_time = moscow_now()
        time_diff = current_time - last_time

        cooldown_hours = JOBS_DATA[job_data["job_id"]]["cooldown_hours"]
        cooldown_seconds = cooldown_hours * 3600

        if time_diff.total_seconds() >= cooldown_seconds:
            return True, 0, 0
        else:
            remaining = cooldown_seconds - time_diff.total_seconds()
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            return False, hours, minutes
    except Exception as e:
        print(f"Ошибка при проверке времени работы: {e}")
        return True, 0, 0


async def fire_user(user_id: int):
    """Уволить пользователя"""
    try:
        sql.execute("DELETE FROM jobs WHERE user_id = ?", (user_id,))
        database.commit()
    except Exception as e:
        print(f"Ошибка в fire_user для user_id {user_id}: {e}")


async def get_jobs_list() -> str:
    """Получить список доступных работ"""
    jobs_list = "📋 Список доступных работ:\n\n"
    for job_id, job_data in JOBS_DATA.items():
        jobs_list += f"{job_id}. {job_data['name']}\n"
        jobs_list += f"   📝 {job_data['description']}\n"
        jobs_list += f"   🎯 Требуемый навык: {job_data['min_skill']}\n"
        jobs_list += f"   💰 Зарплата: {job_data['salary']:,}₽\n"
        jobs_list += f"   ⏰ КД: {job_data['cooldown_hours']} часа(ов)\n"
        jobs_list += f"   📈 Навык за работу: +{job_data['skill_gain']}\n\n"
    return jobs_list


async def get_user_data1(user_id: int):
    """Получить дату окончания VIP статуса из БД"""
    sql.execute(f"SELECT date_string FROM vip WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if fetch:
        return fetch[0]
    else:
        return None


async def is_vip_active(user_id: int):
    """Проверить, активен ли VIP статус"""
    vip_end_date = await get_user_data1(user_id)
    if not vip_end_date:
        return False

    try:
        end_date = datetime.strptime(vip_end_date, '%Y-%m-%d %H:%M:%S.%f')
        current_date = moscow_now()
        return end_date > current_date
    except:
        return False


async def set_user_date(user_id: int, days: int):
    """Установить/обновить дату окончания VIP статуса"""
    sql.execute(f"SELECT date_string FROM vip WHERE user_id = {user_id}")
    fetch = sql.fetchone()

    current_date = moscow_now()

    if fetch and fetch[0]:
        try:
            end_date = datetime.strptime(fetch[0], '%Y-%m-%d %H:%M:%S.%f')
            if end_date > current_date:
                new_end_date = end_date + timedelta(days=days)
            else:
                new_end_date = current_date + timedelta(days=days)
        except:
            new_end_date = current_date + timedelta(days=days)
    else:
        new_end_date = current_date + timedelta(days=days)

    date_string = new_end_date.strftime('%Y-%m-%d %H:%M:%S.%f')

    if fetch:
        sql.execute(f"UPDATE vip SET date_string = ? WHERE user_id = ?", (date_string, user_id))
    else:
        sql.execute(f"INSERT INTO vip VALUES (?,?)", (user_id, date_string))
    await log_economy(user_id=user_id, target_id=None, amount=None,
                      log=f"получил(+а) VIP на {days} дней")

    database.commit()
    return date_string


async def get_user_data(user_id):
    sql.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = sql.fetchone()

    if user is None:
        # Узнайте, какие именно колонки в вашей таблице users
        # Пример: если колонки (id, last_bonus, balance)
        sql.execute("INSERT INTO users VALUES (?, ?)", (user_id, 0))  # Последнее значение - начальный баланс
        database.commit()
        return 0
    else:
        # Возвращаем last_bonus (предполагая, что это вторая колонка)
        return user[1]  # или user['last_bonus'] если используете row_factory


async def ensure_column_exists(table_name, column_name, column_type="INTEGER"):
    sql.execute(f"PRAGMA table_info({table_name})")
    columns = sql.fetchall()
    column_names = [col[1] for col in columns]
    if column_name not in column_names:
        print(f"Колонка '{column_name}' не найдена в таблице '{table_name}'. Создаем...")
        try:
            sql.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            print(f"Колонка '{column_name}' успешно создана.")
            database.commit()
        except sqlite3.OperationalError as e:
            print(f"Ошибка при создании колонки '{column_name}': {e}")
            database.rollback()
    else:
        print(f"Колонка '{column_name}' уже существует в таблице '{table_name}'. Ничего не делаем.")


async def ensure_column_delete(table_name=str):
    print(1, table_name)
    sql.execute(f"DELETE FROM promo WHERE promo = ?", (table_name,))
    print(f"Колонка '{table_name}' успешно удалена.")
    database.commit()


async def update_last_bonus_time(user_id: int):
    """Обновить время последнего получения бонуса"""
    sql.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (moscow_now(), user_id))
    database.commit()


async def get_blago(user_id=int):
    sql.execute(f"SELECT blago FROM balance WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if fetch == None:
        return 0
    else:
        return fetch[0]


async def get_bank(user_id=int):
    sql.execute(f"SELECT bank FROM balance WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if fetch == None:
        return 0
    else:
        return fetch[0]


async def get_balance(user_id=int):
    sql.execute(f"SELECT money FROM balance WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if fetch == None:
        return 0
    else:
        return fetch[0]


async def get_duelwin(user_id=int):
    sql.execute(f"SELECT money FROM duelwin WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if fetch == None:
        return 0
    else:
        return fetch[0]


async def get_duelunwin(user_id=int):
    sql.execute(f"SELECT money FROM duelunallwin WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if fetch == None:
        return 0
    else:
        return fetch[0]


async def get_duelwinid(user_id=int):
    sql.execute(f"SELECT id FROM duelwin WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if fetch == None:
        return 0
    else:
        return fetch[0]


async def get_duelunwinid(user_id=int):
    sql.execute(f"SELECT id FROM duelunallwin WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if fetch == None:
        return 0
    else:
        return fetch[0]


async def get_user_name(user_id=int):
    try:
        info = await bot.api.users.get(user_id=[user_id], fields=['first_name', 'last_name', 'screen_name'])
        if not info:
            print(f"API вернул пустой список для user_id: {user_id}.")
            display_name = f"ID{user_id}"
            return display_name
        first_name = info[0].first_name
        last_name = info[0].last_name
        display_name = f"{first_name} {last_name}"
        return display_name
    except vk_api.exceptions.ApiError as e:
        print(1)


async def is_nick(user_id=int, chat_id=int):
    sql.execute(f"SELECT nick FROM nicks_{chat_id} WHERE user_id = {user_id}")
    if sql.fetchone() == None:
        return False
    else:
        return True


async def setpromo5(user_id=int, new_blago=int):
    sql.execute(f"INSERT INTO usprom(user_id, promo) VALUES (?, ?)", (user_id, new_blago))
    database.commit()


async def getpromo5(user_id=int, promo=str):
    try:
        print(101)
        print(user_id, promo)
        query = 'SELECT 1 FROM usprom WHERE user_id = ? AND promo = ?'
        sql.execute(query, (user_id, promo))
        fetch = sql.fetchone()
        print(fetch)
        print(1)
        if fetch:
            return 1
        else:
            return 2
    except sqlite3.Error as e:
        print(f'Ошибка бд {e}')
        return 2
    except Exception as e:
        print(f'Ошибка проверки промо {e}')
        return 2


async def setblago(user_id=int, new_blago=int):
    sql.execute(f"SELECT blago FROM balance WHERE user_id = {user_id}")
    result = sql.fetchone()
    print(result)
    if result is None:
        sql.execute(f"INSERT INTO balance(user_id, blago) VALUES (?, ?)", (user_id, new_blago))
        database.commit()
    else:
        current_money = result[0]
        updated_money = current_money + new_blago
        print(updated_money)
        sql.execute(f"UPDATE balance SET blago = ? WHERE user_id = ?", (updated_money, user_id,))
        database.commit()


async def getgame(chat_id=int):
    sql.execute(f"SELECT game FROM chats WHERE chat_id = {chat_id}")
    fetch = sql.fetchone()
    if fetch == None:
        return 0
    else:
        return fetch[0]


async def getpromo(promo=str):
    sql_query = "SELECT promo FROM promo WHERE promo = ?"
    sql.execute(sql_query, (promo,))
    fetch = sql.fetchone()
    print(fetch)
    if fetch == None:
        return 0
    else:
        return fetch[0]


async def getpromo1(promo=str):
    sql_query = "SELECT status FROM promo WHERE promo = ?"
    sql.execute(sql_query, (promo,))
    fetch = sql.fetchone()
    if fetch == None:
        return 0
    else:
        return fetch[0]


async def getpromo2(promo=str):
    sql_query = "SELECT vip FROM promo WHERE promo = ?"
    sql.execute(sql_query, (promo,))
    fetch = sql.fetchone()
    print(fetch)
    if fetch == None:
        return 0
    else:
        return fetch[0]


async def getpromo3(promo=str):
    sql_query = "SELECT money FROM promo WHERE promo = ?"
    sql.execute(sql_query, (promo,))
    fetch = sql.fetchone()
    if fetch is None:
        return 0
    else:
        return fetch[0]


async def setpromo(promo=str, status=str, vip=int, money=int):
    sql_query = "SELECT promo FROM promo WHERE promo = ?"
    sql.execute(sql_query, (promo,))
    result = sql.fetchone()
    print(result)
    if result is None:
        sql.execute(f"INSERT INTO promo VALUES (?, ?, ?, ?)", (promo, status, vip, money))
        database.commit()
    else:
        sql.execute(f"UPDATE promo SET status = ?, vip = ?, money = ? WHERE promo = ?", (status, vip, money, promo,))
        database.commit()


async def setgame(chat_id=int, id=int):
    sql.execute(f"SELECT game FROM chats WHERE chat_id = {chat_id}")
    result = sql.fetchone()
    print(result)
    if result != 0:
        sql.execute(f"UPDATE chats SET game = ? WHERE chat_id = ?", (id, chat_id,))
        database.commit()
        print(1)
    else:
        sql.execute(f"UPDATE chats SET game = ? WHERE chat_id = ?", (id, chat_id,))
        database.commit()


async def setmoney(user_id=int, new_money=int):
    sql.execute(f"SELECT money FROM balance WHERE user_id = {user_id}")
    result = sql.fetchone()
    print(result)
    if result is None:
        sql.execute(f"INSERT INTO balance(user_id, money) VALUES (?, ?)", (user_id, new_money))
        database.commit()
    else:
        current_money = result[0]
        updated_money = current_money + new_money
        print(updated_money)
        sql.execute(f"UPDATE balance SET money = ? WHERE user_id = ?", (updated_money, user_id,))
        database.commit()


async def delmoney(user_id=int):
    sql.execute("DELETE FROM balance WHERE user_id = ?", (user_id,))
    database.commit()


async def setbank(user_id=int, new_money=int):
    sql.execute(f"SELECT bank FROM balance WHERE user_id = {user_id}")
    result = sql.fetchone()
    print(result)
    if result is None:
        sql.execute(f"INSERT INTO balance(user_id, bank) VALUES (?, ?)", (user_id, new_money))
        database.commit()
    else:
        current_money = result[0]
        updated_money = current_money + new_money
        print(updated_money)
        sql.execute(f"UPDATE balance SET bank = ? WHERE user_id = ?", (updated_money, user_id,))
        database.commit()


async def rename_clan(clan_id: int, new_name: str, new_tag: str = None) -> dict:
    """Изменить название и/или тег клана"""
    try:
        if new_tag:
            # Проверяем уникальность тега
            sql.execute("SELECT clan_id FROM clans WHERE tag = ? AND clan_id != ?", (new_tag, clan_id))
            if sql.fetchone():
                return {"success": False, "message": "Клан с таким тегом уже существует!"}

            sql.execute("UPDATE clans SET tag = ? WHERE clan_id = ?", (new_tag, clan_id))

        if new_name:
            # Проверяем уникальность названия
            sql.execute("SELECT clan_id FROM clans WHERE name = ? AND clan_id != ?", (new_name, clan_id))
            if sql.fetchone():
                return {"success": False, "message": "Клан с таким названием уже существует!"}

            sql.execute("UPDATE clans SET name = ? WHERE clan_id = ?", (new_name, clan_id))

        database.commit()
        return {"success": True, "message": "Название клана успешно изменено!"}
    except Exception as e:
        print(f"Ошибка при изменении названия клана: {e}")
        return {"success": False, "message": f"Ошибка: {e}"}


async def duelwin(user_id=int, money=int):
    moneyall = int(await get_duelwin(user_id))
    money = int(money)
    id = await get_duelwinid(user_id)
    if moneyall > 1:
        sql.execute(f"INSERT INTO duelwin VALUES (?, ?, ?)",
                    (user_id, moneyall + money, id + 1))
        database.commit()
    if moneyall < 1:
        sql.execute(f"INSERT INTO duelwin VALUES (?, ?, ?)",
                    (user_id, money, 1))
        database.commit()
        return 1


async def duelunwin(user_id=int, money=int):
    moneyall = int(await get_duelunwin(user_id))
    money = int(money)
    id = await get_duelunwinid(user_id)
    if moneyall > 1:
        sql.execute(f"INSERT INTO duelunallwin VALUES (?, ?, ?)",
                    (user_id, moneyall + money, id + 1))
        database.commit()
    if moneyall < 1:
        sql.execute(f"INSERT INTO duelunallwin VALUES (?, ?, ?)",
                    (user_id, money, 1))
        database.commit()
        return 1


async def gcheckpromo(message):
    allpromo = []
    try:
        sql.execute("SELECT * FROM promo")
        fetch = sql.fetchall()
        print(6, fetch)
        for row in fetch:
            a = row[0]
            b = row[1]
            c = row[2]
            d = row[3]
            await message.reply(f'Информация о промокоде: {a}\nСтатус промокода: {b}\nВип: {c} дней\nМонеты: {d}')
        return True
    except Exception as e:
        print('error')
        return []


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


async def get_user_nam(user_id=int, chat_id=int):
    sql.execute(f"SELECT nick FROM nicks_{chat_id} WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if not fetch == None:
        return fetch[0]


async def get_all_peerids():
    sql.execute("SELECT peer_id FROM chats")
    fetch = sql.fetchall()
    peer_ids = []
    for i in fetch:
        peer_ids.append(i[0])
    return peer_ids


async def topblago():
    # Получаем список админов
    a = await ruklist()
    admin_ids = a if a else []
    
    # Получаем пользователей с глобальными ролями
    sql.execute("SELECT user_id FROM global_managers WHERE level >= 1")
    global_roles = sql.fetchall()
    global_ids = [row[0] for row in global_roles] if global_roles else []
    
    # Объединяем оба списка
    ensure_top_whitelist_table()
    sql.execute("SELECT user_id FROM top_whitelist")
    whitelist_ids = [row[0] for row in sql.fetchall()]
    excluded_user_ids = list(set(admin_ids + global_ids + whitelist_ids))
    
    if not excluded_user_ids:
        query = '''
                    SELECT user_id, blago FROM balance
                    ORDER BY blago DESC LIMIT 10
                '''
        sql.execute(query)
    else:
        placeholders = ", ".join("?" * len(excluded_user_ids))
        query = f'''
                    SELECT user_id, blago FROM balance
                    WHERE user_id NOT IN ({placeholders})
                    ORDER BY blago DESC LIMIT 10
                '''
        sql.execute(query, tuple(excluded_user_ids))
    top_10 = sql.fetchall()
    
    result = '👾 Топ благотворительности:\n\n'
    
    for i, (user_id, blago) in enumerate(top_10):
        blago_formatted = f'{blago:,d}'.replace(',', '.')
        user_mention = await get_user_or_group_mention(user_id)
        result += f'Топ: {i + 1} 🎗️: {user_mention} | {blago_formatted}₽\n\n'
    
    print(result)
    return result


async def delete_message(group_id=int, peer_id=int, cmid=int):
    try:
        await bot.api.messages.delete(group_id=group_id, peer_id=peer_id, delete_for_all=True, cmids=cmid)
    except:
        pass


async def addruk(user_id=int):
    sql.execute(f"INSERT INTO ruk VALUES (?)", (user_id,))
    database.commit()


async def delruk(user_id=int):
    sql.execute(f"DELETE FROM ruk WHERE user_id = {user_id}")
    database.commit()


async def ruklist():
    sql.execute(f"SELECT * FROM ruk")
    fetch = sql.fetchall()
    if fetch:
        ids_list = [item[0] for item in fetch]
        idstuple = tuple(ids_list)
        print(ids_list)
        return ids_list


async def topbalance():
    # Получаем список админов
    a = await ruklist()
    admin_ids = a if a else []
    
    # Получаем пользователей с глобальными ролями
    sql.execute("SELECT user_id FROM global_managers WHERE level >= 1")
    global_roles = sql.fetchall()
    global_ids = [row[0] for row in global_roles] if global_roles else []
    
    # Объединяем оба списка
    ensure_top_whitelist_table()
    sql.execute("SELECT user_id FROM top_whitelist")
    whitelist_ids = [row[0] for row in sql.fetchall()]
    excluded_user_ids = list(set(admin_ids + global_ids + whitelist_ids))
    
    if not excluded_user_ids:
        query = '''
                SELECT user_id, money, bank FROM balance
                ORDER BY money DESC LIMIT 10
            '''
        sql.execute(query)
    else:
        placeholders = ", ".join("?" * len(excluded_user_ids))
        query = f'''
                SELECT user_id, money, bank FROM balance
                WHERE user_id NOT IN ({placeholders})
                ORDER BY money DESC LIMIT 10
            '''
        sql.execute(query, tuple(excluded_user_ids))
    top_10 = sql.fetchall()
    
    result = '💰 Самые богатые пользователи:\n\n'
    
    for i, (user_id, money, bank) in enumerate(top_10):
        # Форматируем общую сумму
        money_formatted = f'{money:,d}'.replace(',', '.')
        
        # Форматируем банк
        bank_formatted = f'{bank:,d}'.replace(',', '.')
        
        # Получаем имя пользователя
        user_mention = await get_user_or_group_mention(user_id)
        
        # Проверяем VIP статус
        vip_active = await is_vip_active(user_id)
        vip_status = "VIP" if vip_active else "—"
        vip_emoji = "⭐" if vip_active else ""
        
        # Получаем количество бизнесов
        sql.execute("SELECT COUNT(*) FROM user_businesses WHERE user_id = ?", (user_id,))
        businesses_count = sql.fetchone()[0]
        
        # Получаем количество домов
        sql.execute("SELECT COUNT(*) FROM houses WHERE user_id = ?", (user_id,))
        houses_count = sql.fetchone()[0]
        
        # Получаем количество машин
        sql.execute("SELECT COUNT(*) FROM cars WHERE user_id = ?", (user_id,))
        cars_count = sql.fetchone()[0]
        
        # Формируем строку топа
        result += f'Топ: {i + 1} 👑: {user_mention} | {money_formatted}₽\n\n'
        result += f'💳 Счет в банке: {bank_formatted}₽\n'
        result += f'{vip_emoji} Статус: {vip_status}\n'
        result += f'🏢 Бизнесов: {businesses_count}\n'
        result += f'🏠 Дома: {houses_count}\n'
        result += f'🚗 Машины: {cars_count}\n\n'
    
    print(result)
    return result


@bot.on.chat_message(rules.ChatActionRule("chat_invite_user"))
async def user_joined(message: Message) -> None:
    invited_user = message.action.member_id
    print('gi')
    user_id = message.from_id
    chat_id = message.chat_id
    if invited_user == -236475011:
        print([photo1])
        try:
            await message.answer(
                "Бот успешно добавлен в беседу!\nДля его активации в беседе напишите /start!",
                attachment=[photo1])
        except Exception as e:
            print(e)


def save_data(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Создаём пустые JSON, если их нет
for f in [BALANCES_FILE]:
    if not os.path.exists(f):
        with open(f, "w", encoding="utf-8") as fp:
            json.dump({}, fp)

for f in [BALANCES_FILE]:
    if not os.path.exists(f):
        with open(f, "w", encoding="utf-8") as fp:
            json.dump({}, fp)

# Загружаем конфиг
with open("config3.json", "r") as js:
    open_file = json.load(js)

# ================== STORAGE ==================
balances = load_data(BALANCES_FILE)


async def update_clan_battles_table():
    """Обновляет таблицу clan_battles, добавляя колонку created_at"""
    try:
        sql.execute("PRAGMA table_info(clan_battles)")
        columns = sql.fetchall()
        column_names = [col[1] for col in columns]

        if 'created_at' not in column_names:
            sql.execute("ALTER TABLE clan_battles ADD COLUMN created_at TEXT")
            database.commit()
            print("Добавлена колонка created_at в clan_battles")

        print("✅ Таблица clan_battles обновлена!")
    except Exception as e:
        print(f"Ошибка при обновлении clan_battles: {e}")

async def clear(cmid=int, chat_id=int, group_id=int, peer_id=int):
    try:
        await bot.api.messages.delete(group_id=group_id, peer_id=peer_id, delete_for_all=True, cmids=cmid)
    except:
        pass


async def handle_duel_callback(message):
    payload = message.object.payload
    user_id = message.object.user_id
    event_id = message.object.event_id

    # Проверяем, что это действительно команда дуэли
    if payload.get('cmd') != "duel_join":
        return

    creator_id = payload['creator']
    stake = payload['stake']
    target_chat_id = payload.get('chat')

    print(f"Дуэль: creator={creator_id}, user={user_id}, chat={target_chat_id}, stake={stake}")

    # Проверяем, существует ли дуэль
    if target_chat_id not in current_duel:
        await bot.api.messages.send_message_event_answer(
            event_id=event_id,
            peer_id=message.object.peer_id,
            user_id=user_id,
            event_data=json.dumps({"type": "show_snackbar", "text": "Эта дуэль уже неактуальна!"})
        )
        return

    duel_data = current_duel[target_chat_id]

    if user_id == creator_id:
        await bot.api.messages.send_message_event_answer(
            event_id=event_id,
            peer_id=message.object.peer_id,
            user_id=user_id,
            event_data=json.dumps({"type": "show_snackbar", "text": "Вы не можете сразиться сами с собой!"})
        )
        return

    # Проверяем баланс участника
    participant_balance = await get_balance(user_id)
    if stake > participant_balance:
        await bot.api.messages.send_message_event_answer(
            event_id=event_id,
            peer_id=message.object.peer_id,
            user_id=user_id,
            event_data=json.dumps({"type": "show_snackbar", "text": f"У вас недостаточно ₽! Нужно: {stake}"})
        )
        return

    # Проверяем баланс создателя
    creator_balance = await get_balance(creator_id)
    if stake > creator_balance:
        await bot.api.messages.send_message_event_answer(
            event_id=event_id,
            peer_id=message.object.peer_id,
            user_id=user_id,
            event_data=json.dumps({"type": "show_snackbar", "text": "У создателя дуэли недостаточно средств!"})
        )
        # Удаляем дуэль
        del current_duel[target_chat_id]
        return

    # Проверка VIP статуса для комиссии
    is_vip = await is_vip_active(user_id)
    is_creator_vip = await is_vip_active(creator_id)

    # Расчёт комиссии
    if is_vip or is_creator_vip:
        commission = 0
        winner_amount = stake
    else:
        commission = 20
        winner_amount = stake - int(stake * 20 / 100)

    # Определяем победителя
    winner_id = random.choice([creator_id, user_id])
    loser_id = creator_id if winner_id == user_id else user_id

    # Начисляем деньги
    await setmoney(winner_id, winner_amount)
    await setmoney(loser_id, -stake)

    # Обновляем статистику в balances.json
    balances = load_data(BALANCES_FILE)

    w_bal = balances.get(str(winner_id), get_balanc(winner_id))
    l_bal = balances.get(str(loser_id), get_balanc(loser_id))

    w_bal["won"] += 1
    w_bal["won_total"] += winner_amount

    l_bal["lost"] += 1
    l_bal["lost_total"] += stake

    balances[str(winner_id)] = w_bal
    balances[str(loser_id)] = l_bal

    save_data(BALANCES_FILE, balances)

    # Логируем
    await log_economy(
        user_id=winner_id,
        target_id=loser_id,
        amount=winner_amount,
        log=f"победил в дуэли на {stake}₽ (комиссия {commission}%)"
    )
    await log_economy(
        user_id=loser_id,
        target_id=winner_id,
        amount=stake,
        log=f"проиграл в дуэли на {stake}₽"
    )

    # Получаем имена
    winner_name = await get_user_or_group_name(winner_id)
    loser_name = await get_user_or_group_name(loser_id)
    creator_name = await get_user_or_group_name(creator_id)

    # Форматируем числа
    stake_formatted = f'{stake:,d}'.replace(',', '.')
    winner_amount_formatted = f'{winner_amount:,d}'.replace(',', '.')

    # Редактируем сообщение
    result_text = (
        f"⚔️ Дуэль завершена!\n\n"
        f"{await get_user_or_group_mention(creator_id)} VS {await get_user_or_group_mention(user_id)}\n"
        f"Ставка: {stake_formatted}₽\n\n"
        f"🏆 Победитель: {await get_user_or_group_mention(winner_id)}\n"
        f"💀 Проигравший: {await get_user_or_group_mention(loser_id)}\n\n"
        f"💰 Победитель забирает {winner_amount_formatted}₽, с учетом комиссии {commission}%!"
    )

    try:
        await bot.api.messages.edit(
            peer_id=2000000000 + target_chat_id,
            message=result_text,
            conversation_message_id=duel_data['message_id'],
            keyboard=None
        )
    except Exception as e:
        print(f"Ошибка при редактировании сообщения дуэли: {e}")

    # Удаляем дуэль
    del current_duel[target_chat_id]


# Замените существующую функцию on_private_message на эту:

@bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=GroupTypes.MessageEvent)
async def handle_all_callbacks(message):
    payload = message.object.payload
    command = str(payload.get("command") or payload.get("cmd") or "").lower()
    user_id = message.object.user_id
    chat_id = payload.get("chatId") or payload.get("chat")

    # ИГРОВОЙ БОТ - игнорируем административные команды от manager.py
    admin_commands = ["modersallminus", "modersallplus", "nicksminus", "nicksplus", "activewarns",
                      "stats", "warnhistory", "nonicks", "nicks", "nonickminus", "nonickplus",
                      "clear", "unwarn", "unmute", "unban", "alt"]
    if command in admin_commands or command.startswith("moders") or command.startswith("nicks") or \
       command.startswith("nonick") or command.startswith("activewarn") or command.startswith("warn") or \
       command == "stats" or command == "clear" or command == "unwarn" or command == "unmute" or \
       command == "unban" or command == "alt":
        return  # Игнорируем административные команды

    # Получаем список админов для проверки прав
    admin_list = await ruklist()

    # --- ОБРАБОТКА ДУЭЛЕЙ ---
    if command == "duel_join" or payload.get('cmd') == "duel_join":
        await handle_duel_callback(message)
        return

    if command == 'duelponmakendinqwe':
        await handle_duel_callback(Message)
        print(1)

    # --- ОБРАБОТКА КЛАНОВЫХ БИТВ ---
    if command == "accept_clan_battle":
        battle_id = payload.get("battle_id")
        target_id = payload.get("user_id")

        if user_id != target_id:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это не ваш вызов!"})
            )
            return

        # Проверяем существование сражения
        sql.execute("SELECT * FROM clan_battles WHERE battle_id = ?", (battle_id,))
        battle = sql.fetchone()

        if not battle:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Сражение не найдено!"})
            )
            return

        columns = [description[0] for description in sql.description]
        battle_data = dict(zip(columns, battle))

        if battle_data["status"] != "pending":
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это сражение уже завершено!"})
            )
            return

        # Проводим дуэль (рандомный победитель)
        winner_id = random.choice([battle_data["user1_id"], battle_data["user2_id"]])
        loser_id = battle_data["user1_id"] if winner_id == battle_data["user2_id"] else battle_data["user2_id"]

        # Завершаем битву
        result = await finish_clan_battle(battle_id, winner_id)

        if result["success"]:
            # Проверяем, не закончилась ли война
            war_result = await check_war_end(battle_data["war_id"])

            winner_name = await get_user_or_group_name(winner_id)
            loser_name = await get_user_or_group_name(loser_id)

            result_text = (
                f"⚔️ КЛАНОВАЯ ДУЭЛЬ ⚔️\n\n"
                f"🏆 Победитель: {await get_user_or_group_mention(winner_id)}\n"
                f"💀 Проигравший: {await get_user_or_group_mention(loser_id)}\n"
                f"💰 Ставка: {battle_data['bet']}₽ (поступит в казну клана-победителя)\n\n"
            )

            if war_result["finished"]:
                result_text += (
                    f"🏰 ВОЙНА ЗАВЕРШЕНА! 🏰\n\n"
                    f"🥇 Победил клан {war_result['winner']}!\n"
                    f"💰 Клан получил {war_result['total_bet']}₽ в казну!"
                )
            else:
                # Получаем текущий счёт
                sql.execute("SELECT clan1_score, clan2_score FROM clan_wars WHERE war_id = ?", (battle_data["war_id"],))
                scores = sql.fetchone()
                result_text += f"📊 Текущий счёт: {scores[0]} : {scores[1]}"

            await bot.api.messages.send(
                peer_id=message.object.peer_id,
                message=result_text,
                random_id=0
            )

            # Удаляем сообщение с кнопками
            try:
                await bot.api.messages.delete(
                    peer_id=message.object.peer_id,
                    cmids=[message.object.conversation_message_id],
                    delete_for_all=True
                )
            except:
                pass
        else:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": result["message"]})
            )
        return

    if command == "reject_clan_battle":
        await bot.api.messages.send_message_event_answer(
            event_id=message.object.event_id,
            peer_id=message.object.peer_id,
            user_id=message.object.user_id,
            event_data=json.dumps({"type": "show_snackbar", "text": "Вы отклонили вызов"})
        )
        return

    # Команда economyminus

    if command == "economyminus":
        chat_id = message.object.peer_id - 2000000000
        a = await ruklist()
        excluded_user_ids = a
        if user_id not in excluded_user_ids:  # ИСПРАВЛЕНО: было 'is not excludeduser_ids'
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return

        page = payload.get("page")
        target = payload.get("target")

        if page < 2:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это первая страница!"})
            )
            return

        if target:
            sql.execute("SELECT * FROM economy WHERE user_id = ? ORDER BY rowid DESC LIMIT 9999999999999",
                        (target,))
            logs = sql.fetchall()
        else:
            sql.execute("SELECT * FROM economy ORDER BY rowid DESC LIMIT 9999999999999")
            logs = sql.fetchall()

        total = len(logs)
        per_page = MAX_LOGS
        max_page = max(1, (total + per_page - 1) // per_page)

        async def get_economy_page(page: int):
            start = (page - 1) * per_page
            end = start + per_page
            selected = logs[start:end] if start < total else []
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
                    f"{idx}. {u_display} | Кому: {t_display} | Сколько: {a_display} | Лог: {l_display}")
            return formatted

        new_page = page - 1
        economy_page = await get_economy_page(new_page)

        if not economy_page and new_page > 1:
            new_page = 1
            economy_page = await get_economy_page(new_page)

        if not economy_page:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Нет данных для отображения!"})
            )
            return

        economy_text = "\n\n".join(economy_page)

        if target:
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("⏪", {"command": "economyMinus", "target": target, "page": new_page}),
                     color=KeyboardButtonColor.NEGATIVE)
                .add(Callback("⏩", {"command": "economyPlus", "target": target, "page": new_page}),
                     color=KeyboardButtonColor.POSITIVE)
            )
            message_text = f"Логи экономики {await get_user_or_group_mention(target)} [{new_page}/{max_page}]:\n\n{economy_text}"
        else:
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("⏪", {"command": "economyAllMinus", "page": new_page}),
                     color=KeyboardButtonColor.NEGATIVE)
                .add(Callback("⏩", {"command": "economyAllPlus", "page": new_page}),
                     color=KeyboardButtonColor.POSITIVE)
            )
            message_text = f"Общие логи экономики [{new_page}/{max_page}]:\n\n{economy_text}"

        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=message_text,
            disable_mentions=1, random_id=0, keyboard=keyboard
        )
        return

    # Команда economyplus
    if command == "economyplus":
        chat_id = message.object.peer_id - 2000000000
        a = await ruklist()
        excluded_user_ids = a
        if user_id not in excluded_user_ids:  # ИСПРАВЛЕНО: было 'is not excludeduser_ids'
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return

        page = payload.get("page")
        target = payload.get("target")

        if target:
            sql.execute("SELECT * FROM economy WHERE user_id = ? ORDER BY rowid DESC LIMIT 9999999999999",
                        (target,))
            logs = sql.fetchall()
        else:
            sql.execute("SELECT * FROM economy ORDER BY rowid DESC LIMIT 9999999999999")
            logs = sql.fetchall()

        total = len(logs)
        per_page = MAX_LOGS
        max_page = max(1, (total + per_page - 1) // per_page)

        async def get_economy_page(page: int):
            start = (page - 1) * per_page
            end = start + per_page
            selected = logs[start:end] if start < total else []
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
                    f"{idx}. {u_display} | Кому: {t_display} | Сколько: {a_display} | Лог: {l_display}")
            return formatted

        new_page = page + 1

        if new_page > max_page:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это последняя страница!"})
            )
            return

        economy_page = await get_economy_page(new_page)

        if not economy_page:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это последняя страница!"})
            )
            return

        economy_text = "\n\n".join(economy_page)

        if target:
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("⏪", {"command": "economyMinus", "target": target, "page": new_page}),
                     color=KeyboardButtonColor.NEGATIVE)
                .add(Callback("⏩", {"command": "economyPlus", "target": target, "page": new_page}),
                     color=KeyboardButtonColor.POSITIVE)
            )
            message_text = f"Логи экономики {await get_user_or_group_mention(target)} [{new_page}/{max_page}]:\n\n{economy_text}"
        else:
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("⏪", {"command": "economyAllMinus", "page": new_page}),
                     color=KeyboardButtonColor.NEGATIVE)
                .add(Callback("⏩", {"command": "economyAllPlus", "page": new_page}),
                     color=KeyboardButtonColor.POSITIVE)
            )
            message_text = f"Общие логи экономики [{new_page}/{max_page}]:\n\n{economy_text}"

        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=message_text,
            disable_mentions=1, random_id=0, keyboard=keyboard
        )
        return

    # Команда economyallminus
    if command == "economyallminus":
        chat_id = message.object.peer_id - 2000000000
        a = await ruklist()
        excluded_user_ids = a
        if user_id not in excluded_user_ids:  # ИСПРАВЛЕНО: было 'is not excludeduser_ids'
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

        sql.execute("SELECT * FROM economy ORDER BY rowid DESC LIMIT 9999999999999")
        logs = sql.fetchall()

        total = len(logs)
        per_page = MAX_LOGS
        max_page = max(1, (total + per_page - 1) // per_page)

        async def get_economy_page(page: int):
            start = (page - 1) * per_page
            end = start + per_page
            selected = logs[start:end] if start < total else []
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
                    f"{idx}. {u_display} | Кому: {t_display} | Сколько: {a_display} | Лог: {l_display}")
            return formatted

        new_page = page - 1
        economy_page = await get_economy_page(new_page)

        if not economy_page and new_page > 1:
            new_page = 1
            economy_page = await get_economy_page(new_page)

        if not economy_page:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Нет данных для отображения!"})
            )
            return

        economy_text = "\n\n".join(economy_page)

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("⏪", {"command": "economyAllMinus", "page": new_page}),
                 color=KeyboardButtonColor.NEGATIVE)
            .add(Callback("⏩", {"command": "economyAllPlus", "page": new_page}), color=KeyboardButtonColor.POSITIVE)
        )

        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=f"Общие логи экономики [{new_page}/{max_page}]:\n\n{economy_text}",
            disable_mentions=1, random_id=0, keyboard=keyboard
        )
        return

    # Команда economyallplus
    if command == "economyallplus":
        chat_id = message.object.peer_id - 2000000000
        a = await ruklist()
        excluded_user_ids = a
        if user_id not in excluded_user_ids:  # ИСПРАВЛЕНО: было 'is not excludeduser_ids'
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return

        page = payload.get("page")

        sql.execute("SELECT * FROM economy ORDER BY rowid DESC LIMIT 9999999999999")
        logs = sql.fetchall()

        total = len(logs)
        per_page = MAX_LOGS
        max_page = max(1, (total + per_page - 1) // per_page)

        async def get_economy_page(page: int):
            start = (page - 1) * per_page
            end = start + per_page
            selected = logs[start:end] if start < total else []
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
                    f"{idx}. {u_display} | Кому: {t_display} | Сколько: {a_display} | Лог: {l_display}")
            return formatted

        new_page = page + 1

        if new_page > max_page:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это последняя страница!"})
            )
            return

        economy_page = await get_economy_page(new_page)

        if not economy_page:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это последняя страница!"})
            )
            return

        economy_text = "\n\n".join(economy_page)

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("⏪", {"command": "economyAllMinus", "page": new_page}),
                 color=KeyboardButtonColor.NEGATIVE)
            .add(Callback("⏩", {"command": "economyAllPlus", "page": new_page}), color=KeyboardButtonColor.POSITIVE)
        )

        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=f"Общие логи экономики [{new_page}/{max_page}]:\n\n{economy_text}",
            disable_mentions=1, random_id=0, keyboard=keyboard
        )
        return

        # ================== ОБРАБОТКА КНОПОК МАФИИ ==================
        # Добавьте эти условия в функцию handle_all_callbacks

    # ================== ОБРАБОТКА КНОПОК МАФИИ ==================
    if command.startswith("mafia_"):
        action = command.replace("mafia_", "")
        user_id = message.object.user_id

        # Ищем активную игру
        active_game = None
        active_chat_id = None

        for chat_id, game in active_mafia_games.items():
            if user_id in game.players and game.status == "active" and game.alive.get(user_id, False):
                active_game = game
                active_chat_id = chat_id
                break

        if not active_game:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Вы не участвуете в игре!"})
            )
            return

        if action == "none":
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Нет доступных игроков!"})
            )
            return

        target_id = payload.get("target")

        if action in ["kill", "check", "save"]:
            result = await handle_night_action(active_game, user_id, target_id, action)

            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": result["message"]})
            )

            try:
                await bot.api.messages.delete(
                    peer_id=message.object.peer_id,
                    cmids=[message.object.conversation_message_id],
                    delete_for_all=True
                )
            except:
                pass

        elif action == "vote":
            result = await handle_day_vote(active_game, user_id, target_id)

            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": result["message"]})
            )

            try:
                await bot.api.messages.delete(
                    peer_id=message.object.peer_id,
                    cmids=[message.object.conversation_message_id],
                    delete_for_all=True
                )
            except:
                pass

        return

    # ================== ОБРАБОТКА КНОПОК HELP ==================
    if command == "help_main":
        # Удаляем сообщение с кнопками
        try:
            await bot.api.messages.delete(
                peer_id=message.object.peer_id,
                cmids=[message.object.conversation_message_id],
                delete_for_all=True
            )
        except:
            pass

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("💼 Работы", payload={"cmd": "help_jobs", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
            .add(Callback("🏢 Бизнесы", payload={"cmd": "help_business", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
            .row()
            .add(Callback("🏠 Дома", payload={"cmd": "help_houses", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
            .add(Callback("🚗 Машины", payload={"cmd": "help_cars", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
            .row()
            .add(Callback("📊 Имущество", payload={"cmd": "help_property", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
            .add(Callback("💍 Браки", payload={"cmd": "help_marriage", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
            .row()
            .add(Callback("🎭 Мафия", payload={"cmd": "help_mafia", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
            .add(Callback("🎭 РП команды", payload={"cmd": "help_rp", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
            .row()
            .add(Callback("🏰 Кланы", payload={"cmd": "help_clans", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
        )

        main_text = (
            "🎮 GREAT GAME - СПРАВКА 🎮\n\n"
            "Выберите раздел с помощью кнопок ниже:\n\n"
            "📌 Основные команды:\n"
            "• /бонус - получить бонус\n"
            "• /подписка - получить бонус за подписку\n"
            "• /баланс - посмотреть баланс\n"
            "• /положить - положить на счет банка\n"
            "• /снять - снять со счета банка\n"
            "• /promo - ввести промокод\n"
            "• /buyvip - купить VIP статус\n"
            "• /шар - спросить вероятность у шара\n"
            "• /дуэль - начать дуэль\n"
            "• /казино - играть в казино\n"
            "• /пожертвовать - в благотворительность\n"
            "• /топблаго - топ благотворительности\n"
            "• /myblago - сумма пожертвований\n"
            "• /передать - передать рубли\n"
            "• /топ - топ богатых игроков\n"
            "• /профиль - посмотреть профиль"
        )

        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=main_text,
            keyboard=keyboard,
            random_id=0
        )
        return

        # РАБОТЫ
    if command == "help_jobs":
        try:
            await bot.api.messages.delete(
                peer_id=message.object.peer_id,
                cmids=[message.object.conversation_message_id],
                delete_for_all=True
            )
        except:
            pass

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("📋 Список команд", payload={"cmd": "help_main", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
        )

        text = (
            "💼 СИСТЕМА РАБОТ 💼\n\n"
            "/job - посмотреть доступные вакансии\n"
            "/работа - получить зарплату (КД 3 часа)\n"
            "/уволиться - уволиться с работы\n"
            "/statsjob - статистика работы\n\n"
            "📊 НАВЫКИ:\n"
            "• Навык повышается с каждой работой\n"
            "• Чем выше навык, тем доступнее работа\n"
            "• Навык сохраняется при увольнении\n\n"
            "💡 Совет: начинайте с простых работ!"
        )

        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=text,
            keyboard=keyboard,
            random_id=0
        )
        return

        # БИЗНЕСЫ
    if command == "help_business":
        try:
            await bot.api.messages.delete(
                peer_id=message.object.peer_id,
                cmids=[message.object.conversation_message_id],
                delete_for_all=True
            )
        except:
            pass

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("📋 Список команд", payload={"cmd": "help_main", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
        )

        text = (
            "🏢 СИСТЕМА БИЗНЕСОВ 🏢\n\n"
            "/бизнесы - список доступных бизнесов\n"
            "/бизнес - ваши бизнесы\n"
            "/инфобиз [номер] - информация о бизнесе\n"
            "/купбиз [номер] - купить бизнес\n"
            "/продбиз [номер] - продать бизнес (70% возврат)\n"
            "/собратьбиз [номер] - собрать прибыль (24 часа)\n"
            "/снятьбиз [номер] [сумма] - снять деньги\n\n"
            "💡 Прибыль начисляется каждый день!"
        )

        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=text,
            keyboard=keyboard,
            random_id=0
        )
        return

        # ДОМА
    if command == "help_houses":
        try:
            await bot.api.messages.delete(
                peer_id=message.object.peer_id,
                cmids=[message.object.conversation_message_id],
                delete_for_all=True
            )
        except:
            pass

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("📋 Список команд", payload={"cmd": "help_main", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
        )

        text = (
            "🏠 СИСТЕМА НЕДВИЖИМОСТИ 🏠\n\n"
            "/дома - список доступных домов\n"
            "/купдом [номер] - купить дом\n"
            "/проддом [номер] - продать дом (70% возврат)\n\n"
            "💡 Самый дорогой дом отображается в профиле как место проживания"
        )

        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=text,
            keyboard=keyboard,
            random_id=0
        )
        return

        # МАШИНЫ
    if command == "help_cars":
        try:
            await bot.api.messages.delete(
                peer_id=message.object.peer_id,
                cmids=[message.object.conversation_message_id],
                delete_for_all=True
            )
        except:
            pass

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("📋 Список команд", payload={"cmd": "help_main", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
        )

        text = (
            "🚗 СИСТЕМА ТРАНСПОРТА 🚗\n\n"
            "/машины - список доступных машин\n"
            "/купмашин [номер] - купить машину\n"
            "/продмашин [номер] - продать машину (70% возврат)\n\n"
            "💡 Самая дорогая машина отображается в профиле"
        )

        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=text,
            keyboard=keyboard,
            random_id=0
        )
        return

        # ИМУЩЕСТВО
    if command == "help_property":
        try:
            await bot.api.messages.delete(
                peer_id=message.object.peer_id,
                cmids=[message.object.conversation_message_id],
                delete_for_all=True
            )
        except:
            pass

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("📋 Список команд", payload={"cmd": "help_main", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
        )

        text = (
            "📊 ПРОСМОТР ИМУЩЕСТВА 📊\n\n"
            "/имущ - ваши дома и машины\n"
            "/имущ @user - имущество другого игрока\n"
            "/топимущ - топ 10 по имуществу\n"
            "/профиль - полный профиль игрока\n\n"
            "💡 В профиле отображается:\n"
            "• Баланс и банк\n"
            "• Количество домов и машин\n"
            "• Место проживания и транспорт\n"
            "• Работа и навык\n"
            "• Клан и семейное положение"
        )

        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=text,
            keyboard=keyboard,
            random_id=0
        )
        return

        # БРАКИ
    if command == "help_marriage":
        try:
            await bot.api.messages.delete(
                peer_id=message.object.peer_id,
                cmids=[message.object.conversation_message_id],
                delete_for_all=True
            )
        except:
            pass

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("📋 Список команд", payload={"cmd": "help_main", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
        )

        text = (
            "💍 СИСТЕМА БРАКОВ 💍\n\n"
            "/брак - информация о вашем браке\n"
            "/брак предложить @user - сделать предложение\n"
            "/брак принять [ID] - принять предложение\n"
            "/брак отклонить [ID] - отклонить предложение\n"
            "/брак список - список ваших предложений\n"
            "/развод - развестись\n"
            "/брак топ - статистика браков\n\n"
            "💡 Статус брака отображается в профиле!"
        )

        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=text,
            keyboard=keyboard,
            random_id=0
        )
        return

        # МАФИЯ
    if command == "help_mafia":
        try:
            await bot.api.messages.delete(
                peer_id=message.object.peer_id,
                cmids=[message.object.conversation_message_id],
                delete_for_all=True
            )
        except:
            pass

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("📋 Список команд", payload={"cmd": "help_main", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
        )

        text = (
            "🎭 ИГРА В МАФИЮ 🎭\n\n"
            "📋 КОМАНДЫ ДЛЯ ЧАТА:\n"
            "• /мафия создать - создать новую игру\n"
            "• /мафия войти - присоединиться к игре\n"
            "• /мафия выйти - выйти из игры\n"
            "• /мафия начать - начать игру (4+ игроков)\n"
            "• /мафия статус - статус игры с таймером\n"
            "• /мафия время - время до автоудаления\n"
            "• /мафия остановить - остановить игру\n\n"

            "👥 РОЛИ И ДЕЙСТВИЯ (в ЛС):\n"
            "🔪 МАФИЯ: убить @игрок\n"
            "👮 КОМИССАР: проверить @игрок\n"
            "👨‍⚕️ ДОКТОР: спасти @игрок\n"
            "👨‍🌾 МИРНЫЙ: казнить @игрок\n\n"

            "🎮 ПОРЯДОК ХОДОВ:\n"
            "Ночь: Доктор → Комиссар → Мафия\n"
            "День: Все голосуют за казнь\n\n"

            "⏰ АВТОУДАЛЕНИЕ:\n"
            "• Игра удаляется через 10 минут бездействия\n\n"

            "⚠️ ВАЖНО: Напишите боту ЛЮБОЕ сообщение в ЛС!"
        )

        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=text,
            keyboard=keyboard,
            random_id=0
        )
        return

        # РП КОМАНДЫ
    if command == "help_rp":
        try:
            await bot.api.messages.delete(
                peer_id=message.object.peer_id,
                cmids=[message.object.conversation_message_id],
                delete_for_all=True
            )
        except:
            pass

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("📋 Список команд", payload={"cmd": "help_main", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
        )

        text = (
            "🎭 РОЛЕВЫЕ КОМАНДЫ 🎭\n\n"
            "/обнять @user - обнять собеседника\n"
            "/поцеловать @user - поцеловать собеседника\n"
            "/отсосать @user - отсосать собеседнику\n"
            "/отлизать @user - отлизать собеседнику\n"
            "/трахнуть @user - трахнуть собеседника\n"
            "/выебать @user - жестко трахнуть собеседника\n"
            "/застрелить @user - застрелить собеседника\n"
            "/обоссать @user - обоссать собеседника\n"
            "/ударить @user - ударить собеседника\n"
            "/пнуть @user - пнуть собеседника\n"
            "/вьебать @user - жестко ударить собеседника\n\n"
            "💡 Используйте @упоминание или ответ на сообщение"
        )

        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=text,
            keyboard=keyboard,
            random_id=0
        )
        return

        # КЛАНЫ
    if command == "help_clans":
        try:
            await bot.api.messages.delete(
                peer_id=message.object.peer_id,
                cmids=[message.object.conversation_message_id],
                delete_for_all=True
            )
        except:
            pass

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("📋 Список команд", payload={"cmd": "help_main", "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
        )

        text = (
            "🏰 СИСТЕМА КЛАНОВ 🏰\n\n"
            "📋 ОСНОВНЫЕ КОМАНДЫ:\n"
            "/клан создать [название] [тег] - создать клан (100,000₽)\n"
            "/клан инфо - информация о клане\n"
            "/клан топ - топ кланов\n"
            "/клан поиск [название] - найти клан\n\n"

            "👥 УПРАВЛЕНИЕ:\n"
            "/клан пригласить @user - пригласить в клан\n"
            "/клан принять - принять приглашение\n"
            "/клан кикнуть @user - исключить из клана\n"
            "/клан покинуть - выйти из клана\n"
            "/клан передать @user - передать права лидера\n\n"

            "👑 ЗАМЕСТИТЕЛЬ:\n"
            "/клан заместитель добавить @user\n"
            "/клан заместитель удалить @user\n"
            "/клан заместитель список\n\n"

            "💰 КАЗНА:\n"
            "/клан казна - баланс казны\n"
            "/клан казна положить [сумма]\n"
            "/клан казна снять [сумма] (лидер/зам)\n\n"

            "⚔️ ВОЙНЫ:\n"
            "/клан война [название] [ставка]\n"
            "/клан принятьвойну [ID]\n"
            "/клан вызвать @user [ставка]\n"
            "/клан войнастат [ID]\n\n"

            "✏️ НАСТРОЙКИ:\n"
            "/клан переименовать [название] (50,000₽)\n"
            "/клан сменитьтег [тег] (25,000₽)\n"
            "/клан удалить (только если вы один)\n\n"

            "💡 Создание клана стоит 100,000₽\n"
            "📌 Тег должен быть в скобках, например [WAR]"
        )

        await bot.api.messages.send(
            peer_id=message.object.peer_id,
            message=text,
            keyboard=keyboard,
            random_id=0
        )
        return

    if command == "clear":
        a = await ruklist()
        excluded_user_ids = a
        if user_id not in excluded_user_ids:  # ИСПРАВЛЕНО: было 'is not excludeduser_ids'
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
        await bot.api.messages.send(peer_id=2000000000 + chat_id,
                                    message=f"{await get_user_or_group_mention(user_id)} очистил(-а) сообщения",
                                    disable_mentions=1, random_id=0)
        return


def sync_balances():
    global balances
    balances = load_data(BALANCES_FILE)
    return balances


def format_number(n: int) -> str:
    return f"{n:,}".replace(",", ".")


# ================== СИСТЕМА БРАКОВ ==================

async def create_marriage_proposal(from_id: int, to_id: int) -> dict:
    """Создать предложение брака"""
    # Проверяем, не состоят ли уже пользователи в браке
    from_married = await is_user_married(from_id)
    to_married = await is_user_married(to_id)

    if from_married:
        return {"success": False, "message": "Вы уже состоите в браке!"}

    if to_married:
        return {"success": False, "message": "Этот пользователь уже состоит в браке!"}

    if from_id == to_id:
        return {"success": False, "message": "Нельзя жениться на самом себе!"}

    # Проверяем, есть ли уже активное предложение
    sql.execute("""
        SELECT proposal_id FROM marriage_proposals 
        WHERE ((from_id = ? AND to_id = ?) OR (from_id = ? AND to_id = ?)) 
        AND status = 'pending'
    """, (from_id, to_id, to_id, from_id))

    if sql.fetchone():
        return {"success": False, "message": "Предложение уже отправлено!"}

    # Создаём предложение
    current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')

    sql.execute("""
        INSERT INTO marriage_proposals (from_id, to_id, proposal_date, status)
        VALUES (?, ?, ?, 'pending')
    """, (from_id, to_id, current_time))

    proposal_id = sql.lastrowid
    database.commit()

    return {"success": True, "proposal_id": proposal_id, "message": "Предложение отправлено!"}


async def get_user_proposals(user_id: int) -> list:
    """Получить все активные предложения пользователя"""
    sql.execute("""
        SELECT mp.*, 
               u1.user_name as from_name,
               u2.user_name as to_name
        FROM marriage_proposals mp
        LEFT JOIN (SELECT DISTINCT user_id, 'user' as user_name FROM users) u1 ON mp.from_id = u1.user_id
        LEFT JOIN (SELECT DISTINCT user_id, 'user' as user_name FROM users) u2 ON mp.to_id = u2.user_id
        WHERE (mp.to_id = ? OR mp.from_id = ?) AND mp.status = 'pending'
        ORDER BY mp.proposal_date DESC
    """, (user_id, user_id))

    return sql.fetchall()


async def accept_marriage_proposal(proposal_id: int, user_id: int) -> dict:
    """Принять предложение брака"""
    # Получаем информацию о предложении
    sql.execute("SELECT * FROM marriage_proposals WHERE proposal_id = ? AND status = 'pending'", (proposal_id,))
    proposal = sql.fetchone()

    if not proposal:
        return {"success": False, "message": "Предложение не найдено!"}

    columns = [description[0] for description in sql.description]
    proposal_data = dict(zip(columns, proposal))

    # Проверяем, что принимает именно тот, кому предложили
    if proposal_data["to_id"] != user_id:
        return {"success": False, "message": "Это не ваше предложение!"}

    # Проверяем, не в браке ли уже
    if await is_user_married(user_id):
        return {"success": False, "message": "Вы уже состоите в браке!"}

    if await is_user_married(proposal_data["from_id"]):
        return {"success": False, "message": "Отправитель предложения уже в браке!"}

    # Создаём брак
    current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')

    sql.execute("""
        INSERT INTO marriages (user1_id, user2_id, proposal_date, marriage_date, status, initiator_id)
        VALUES (?, ?, ?, ?, 'accepted', ?)
    """, (proposal_data["from_id"], proposal_data["to_id"],
          proposal_data["proposal_date"], current_time, proposal_data["from_id"]))

    marriage_id = sql.lastrowid

    # Обновляем статус предложения
    sql.execute("UPDATE marriage_proposals SET status = 'accepted' WHERE proposal_id = ?", (proposal_id,))

    database.commit()

    # Логируем
    await log_economy(user_id=proposal_data["from_id"], target_id=proposal_data["to_id"], amount=None,
                      log=f"вступил в брак с пользователем {proposal_data['to_id']}")

    return {
        "success": True,
        "marriage_id": marriage_id,
        "user1": proposal_data["from_id"],
        "user2": proposal_data["to_id"],
        "message": "Поздравляем с бракосочетанием!"
    }


async def reject_marriage_proposal(proposal_id: int, user_id: int) -> dict:
    """Отклонить предложение брака"""
    sql.execute("SELECT * FROM marriage_proposals WHERE proposal_id = ? AND status = 'pending'", (proposal_id,))
    proposal = sql.fetchone()

    if not proposal:
        return {"success": False, "message": "Предложение не найдено!"}

    columns = [description[0] for description in sql.description]
    proposal_data = dict(zip(columns, proposal))

    # Проверяем права
    if proposal_data["to_id"] != user_id and proposal_data["from_id"] != user_id:
        return {"success": False, "message": "Это не ваше предложение!"}

    sql.execute("UPDATE marriage_proposals SET status = 'rejected' WHERE proposal_id = ?", (proposal_id,))
    database.commit()

    return {"success": True, "message": "Предложение отклонено!"}


async def get_user_marriage(user_id: int) -> dict:
    """Получить информацию о браке пользователя"""
    sql.execute("""
        SELECT * FROM marriages 
        WHERE (user1_id = ? OR user2_id = ?) AND status = 'accepted'
    """, (user_id, user_id))

    marriage = sql.fetchone()
    if not marriage:
        return None

    columns = [description[0] for description in sql.description]
    marriage_data = dict(zip(columns, marriage))

    # Определяем супруга
    if marriage_data["user1_id"] == user_id:
        spouse_id = marriage_data["user2_id"]
    else:
        spouse_id = marriage_data["user1_id"]

    marriage_data["spouse_id"] = spouse_id
    marriage_data["spouse_name"] = await get_user_or_group_name(spouse_id)

    return marriage_data


async def is_user_married(user_id: int) -> bool:
    """Проверить, состоит ли пользователь в браке"""
    marriage = await get_user_marriage(user_id)
    return marriage is not None


async def divorce(user_id: int, confirm: bool = False) -> dict:
    """Развестись"""
    marriage = await get_user_marriage(user_id)

    if not marriage:
        return {"success": False, "message": "Вы не состоите в браке!"}

    if not confirm:
        spouse_name = marriage["spouse_name"]
        marriage_date = marriage["marriage_date"][:10] if marriage["marriage_date"] else "неизвестно"
        return {
            "success": False,
            "need_confirm": True,
            "message": f"⚠️ Вы уверены, что хотите развестись с {spouse_name}?\n"
                       f"Дата брака: {marriage_date}\n\n"
                       f"Для подтверждения: /развод confirm"
        }

    current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')

    sql.execute("""
        UPDATE marriages 
        SET status = 'divorced', divorce_date = ? 
        WHERE marriage_id = ?
    """, (current_time, marriage["marriage_id"]))

    database.commit()

    await log_economy(user_id=user_id, target_id=marriage["spouse_id"], amount=None,
                      log=f"развёлся с пользователем {marriage['spouse_id']}")

    return {
        "success": True,
        "message": f"✅ Брак расторгнут. Вы разведены."
    }


async def get_marriage_stats() -> str:
    """Получить статистику браков"""
    sql.execute("SELECT COUNT(*) FROM marriages WHERE status = 'accepted'")
    active_marriages = sql.fetchone()[0]

    sql.execute("SELECT COUNT(*) FROM marriages WHERE status = 'divorced'")
    divorced = sql.fetchone()[0]

    # Самый долгий брак
    sql.execute("""
        SELECT user1_id, user2_id, marriage_date, 
               julianday('now') - julianday(marriage_date) as days
        FROM marriages 
        WHERE status = 'accepted' 
        ORDER BY days DESC LIMIT 1
    """)
    longest = sql.fetchone()

    text = f"📊 СТАТИСТИКА БРАКОВ\n\n"
    text += f"💍 Активных браков: {active_marriages}\n"
    text += f"💔 Разводов: {divorced}\n"

    if longest:
        days = int(longest[3])
        user1_name = await get_user_or_group_name(longest[0])
        user2_name = await get_user_or_group_name(longest[1])
        text += f"🏆 Самый долгий брак: {user1_name} и {user2_name} ({days} дней)"

    return text


# ВРЕМЕННЫЙ КОД - запустите один раз
async def add_missing_businesses():
    missing_businesses = [
        (9, "Крупнейший холдинг в СМГ", "📈", 500000000, 70000000, 85000000, "Крупнейший холдинг"),
        (10, "Банк генетического кода и биодизайна", "🧪", 650000000, 90000000, 100000000, "Биотехнологии"),
        (11, "Высокотехнологичные ниши судостроения", "🚢", 750000000, 110000000, 130000000, "Судостроение"),
        (12, "SPACE X | Ракетостроение", "🚀", 1000000000, 150000000, 180000000, "Космические технологии")
    ]

    for biz in missing_businesses:
        try:
            # Вставляем с проверкой на дубликат
            sql.execute("""
                INSERT OR REPLACE INTO business_types 
                (biz_id, name, emoji, price, min_profit, max_profit, description) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, biz)
            print(f"Добавлен/обновлен бизнес: {biz[1]}")
        except Exception as e:
            print(f"Ошибка при добавлении бизнеса {biz[1]}: {e}")

    database.commit()
    print("Все бизнесы добавлены!")


# Запустите эту функцию один раз

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

    global all_chat_title
    global chat_titles_string

    # Получаем список админов для проверки прав
    admin_list = await ruklist()

    try:
        command_identifier = arguments[0].strip()[0]
        command = arguments_lower[0][1:]
    except:
        command_identifier = " "
        command = " "

    if command_identifier in bot_identifiers:

        global bot_enabled, chat_mode, enabled_chats
        if command in ['startbot', 'включибот']:
            if user_id != 597064735:  # ИСПРАВЛЕНО: было 'await user_id == 597064735'
                await message.reply("Недостаточно прав для этой команды.", disable_mentions=1)
                return
            bot_enabled = True
            chat_mode = "global"
            enabled_chats.clear()
            await message.reply("Бот включен во всех чатах.", disable_mentions=1)
            return
        elif command in ['offbot', 'выключибот']:
            if user_id != 597064735:  # ИСПРАВЛЕНО: было 'await user_id == 597064735'
                await message.reply("Недостаточно прав для этой команды.", disable_mentions=1)
                return
            bot_enabled = False
            await message.reply("Бот выключен во всех чатах.", disable_mentions=1)
            return

        if not bot_enabled and command not in ['startbot', 'включибот', 'offbot', 'выключибот']:
            return True
        if chat_mode == "local":
            if not chat_id:
                return True
            if chat_id not in enabled_chats:
                return True

        if command in ['start', 'старт', 'активировать']:
            if await check_chat(chat_id):
                await message.reply("Бот уже был активирован. Используйте /gamehelp!", disable_mentions=1)
                return True
            try:
                x = await bot.api.messages.get_conversations_by_id(
                    peer_ids=peer_id, extended=1, fields='chat_settings', group_id=message.group_id
                )
                x = json.loads(x.model_dump_json())
                for i in x['items']:
                    owner = int(i["chat_settings"]["owner_id"])

                # Проверка, является ли пользователь владельцем или администратором
                is_owner = (owner == user_id)
                is_admin = False
                if not is_owner:
                    # Получаем список участников и проверяем права администратора
                    members = await bot.api.messages.get_conversation_members(
                        peer_id=peer_id, group_id=message.group_id
                    )
                    members_dict = json.loads(members.json())
                    # Ищем профиль пользователя и проверяем флаг is_admin в items
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
                    "Бот успешно запущен!\nДля того, чтобы начать пользоваться им, напишите /gamehelp!",
                    disable_mentions=1
                )
            except Exception as ex:
                await message.reply("Вы не выдали звезду боту!", disable_mentions=1)
                return True

        if command in ['игры', 'gamehelp', 'помощь', 'команды', 'commands']:
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("💼 Работы", payload={"cmd": "help_jobs", "chatId": chat_id}),
                     color=KeyboardButtonColor.PRIMARY)
                .add(Callback("🏢 Бизнесы", payload={"cmd": "help_business", "chatId": chat_id}),
                     color=KeyboardButtonColor.PRIMARY)
                .row()
                .add(Callback("🏠 Дома", payload={"cmd": "help_houses", "chatId": chat_id}),
                     color=KeyboardButtonColor.PRIMARY)
                .add(Callback("🚗 Машины", payload={"cmd": "help_cars", "chatId": chat_id}),
                     color=KeyboardButtonColor.PRIMARY)
                .row()
                .add(Callback("📊 Имущество", payload={"cmd": "help_property", "chatId": chat_id}),
                     color=KeyboardButtonColor.PRIMARY)
                .add(Callback("💍 Браки", payload={"cmd": "help_marriage", "chatId": chat_id}),
                     color=KeyboardButtonColor.PRIMARY)
                .row()
                .add(Callback("🎭 Мафия", payload={"cmd": "help_mafia", "chatId": chat_id}),
                     color=KeyboardButtonColor.PRIMARY)
                .add(Callback("🎭 РП команды", payload={"cmd": "help_rp", "chatId": chat_id}),
                     color=KeyboardButtonColor.PRIMARY)
                .row()
                .add(Callback("🏰 Кланы", payload={"cmd": "help_clans", "chatId": chat_id}),
                     color=KeyboardButtonColor.PRIMARY)
            )

            main_text = (
                "🎮 GREAT GAME - СПРАВКА 🎮\n\n"
                "Выберите раздел с помощью кнопок ниже:\n\n"
                "📌 Основные команды:\n"
                "• /бонус - получить бонус\n"
                "• /подписка - получить бонус за подписку\n"
                "• /баланс - посмотреть баланс\n"
                "• /положить - положить на счет банка\n"
                "• /снять - снять со счета банка\n"
                "• /promo - ввести промокод\n"
                "• /buyvip - купить VIP статус\n"
                "• /шар - спросить вероятность у шара\n"
                "• /дуэль - начать дуэль\n"
                "• /казино - играть в казино\n"
                "• /пожертвовать - в благотворительность\n"
                "• /топблаго - топ благотворительности\n"
                "• /myblago - сумма пожертвований\n"
                "• /передать - передать рубли\n"
                "• /топ - топ богатых игроков\n"
                "• /профиль - посмотреть профиль"
            )

            await message.reply(main_text, keyboard=keyboard, disable_mentions=1)
            return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'создать':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            if len(arguments) < 4:
                await message.reply(
                    "❌ Использование: /клан создать [название] [тег]\n"
                    "Пример: /клан создать ВоиныСвета [WAR]\n\n"
                    "Тег должен быть в квадратных скобках, например [WAR]",
                    disable_mentions=1
                )
                return True

            # Получаем название и тег
            name_parts = []
            tag = ""

            for i in range(2, len(arguments)):
                if arguments[i].startswith('[') and arguments[i].endswith(']'):
                    tag = arguments[i][1:-1]
                    break
                else:
                    name_parts.append(arguments[i])

            if not name_parts or not tag:
                await message.reply(
                    "❌ Укажите название и тег клана!\n"
                    "Пример: /клан создать ВоиныСвета [WAR]",
                    disable_mentions=1
                )
                return True

            name = " ".join(name_parts)

            # Проверяем длину
            if len(name) > 30:
                await message.reply("❌ Название клана не должно превышать 30 символов!", disable_mentions=1)
                return True

            if len(tag) > 5:
                await message.reply("❌ Тег клана не должен превышать 5 символов!", disable_mentions=1)
                return True

            # Проверяем баланс (создание клана стоит 100к)
            balance = await get_balance(user_id)
            if balance < 100000:
                await message.reply(f"❌ Для создания клана нужно 100,000₽! У вас: {balance:,}₽", disable_mentions=1)
                return True

            # Создаём клан
            result = await create_clan(user_id, name, tag)

            if result["success"]:
                # Списываем деньги
                await setmoney(user_id, -100000)
                await log_economy(user_id=user_id, target_id=None, amount=100000, log=f"создал клан {name} [{tag}]")
                await message.reply(f"✅ {result['message']}", disable_mentions=1)
            else:
                await message.reply(f"❌ {result['message']}", disable_mentions=1)

            return True
        if command in ['клан', 'clan'] and (len(arguments) == 1 or arguments_lower[1] == 'инфо'):
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Определяем, чей клан смотрим
            target_id = user_id
            if message.reply_message:
                target_id = message.reply_message.from_id

            clan_data = await get_user_clan(target_id)

            if not clan_data:
                if target_id == user_id:
                    await message.reply(
                        "❌ Вы не состоите в клане!\n"
                        "💡 Создайте клан: /клан создать [название] [тег]\n"
                        "💡 Посмотрите топ кланов: /клан топ",
                        disable_mentions=1
                    )
                else:
                    await message.reply(f"❌ {await get_user_or_group_mention(target_id)} не состоит в клане!",
                                        disable_mentions=1)
                return True

            # Получаем участников
            members = await get_clan_members(clan_data["clan_id"])

            # Разделяем по ролям
            leader = None
            deputies = []
            regular_members = []

            for member in members:
                if member[1] == 'leader':
                    leader = member
                elif member[1] == 'deputy':
                    deputies.append(member)
                else:
                    regular_members.append(member)

            # Формируем списки
            members_list = []

            # Лидер
            if leader:
                members_list.append(
                    f"👑 {await get_user_or_group_mention(leader[0])} (Лидер) | Пожертвовано: {leader[3]:,}₽")

            # Заместители
            for dep in deputies[:3]:  # Показываем до 3 заместителей
                members_list.append(
                    f"⭐ {await get_user_or_group_mention(dep[0])} (Зам. лидера) | Пожертвовано: {dep[3]:,}₽")

            # Обычные участники (топ 5 по пожертвованиям)
            for member in regular_members[:5]:
                members_list.append(
                    f"👤 {await get_user_or_group_mention(member[0])} | Пожертвовано: {member[3]:,}₽")

            if len(regular_members) > 5:
                members_list.append(f"...и ещё {len(regular_members) - 5} участников")

            members_text = "\n".join(members_list)

            # Статистика побед/поражений
            win_rate = 0
            if clan_data["wins"] + clan_data["losses"] > 0:
                win_rate = round(clan_data["wins"] / (clan_data["wins"] + clan_data["losses"]) * 100, 1)

            # Следующий уровень
            exp_needed = clan_data["level"] * 1000
            exp_progress = clan_data["exp"] / exp_needed * 100 if exp_needed > 0 else 0

            await message.reply(
                f"🏰 Клан: {clan_data['name']} {clan_data['tag']}\n"
                f"👑 Лидер: {await get_user_or_group_mention(clan_data['leader_id'])}\n"
                f"📊 Уровень: {clan_data['level']} (опыт: {clan_data['exp']}/{exp_needed})\n"
                f"💰 Казна: {clan_data['bank']:,}₽\n"
                f"👥 Участников: {clan_data['members_count']}\n"
                f"⚔️ Побед/Поражений: {clan_data['wins']}/{clan_data['losses']} ({win_rate}%)\n\n"
                f"📋 Участники (топ 10):\n{members_text}",
                disable_mentions=1
            )

            return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'пригласить':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Проверяем, состоит ли пользователь в клане
            user_clan = await get_user_clan(user_id)
            if not user_clan:
                await message.reply("❌ Вы не состоите в клане!", disable_mentions=1)
                return True

            # Проверяем права (только лидер и зам могут приглашать)
            if user_clan["role"] not in ['leader', 'deputy']:
                await message.reply("❌ Только лидер и его заместитель могут приглашать в клан!", disable_mentions=1)
                return True

            # Определяем цель
            target_id = None
            if message.reply_message:
                target_id = message.reply_message.from_id
            elif len(arguments) >= 3 and await getID(arguments[2]):
                target_id = await getID(arguments[2])
            else:
                await message.reply("❌ Укажите пользователя!", disable_mentions=1)
                return True

            if target_id == user_id:
                await message.reply("❌ Нельзя пригласить самого себя!", disable_mentions=1)
                return True

            # Создаём приглашение
            result = await create_clan_invite(user_clan["clan_id"], user_id, target_id)

            if result["success"]:
                await message.reply(
                    f"✅ Приглашение отправлено {await get_user_or_group_mention(target_id)}!\n"
                    f"Пользователь может принять его командой: /клан принять",
                    disable_mentions=1
                )

                # Отправляем личное сообщение приглашённому (если бот может)
                try:
                    clan_name = user_clan["name"]
                    await bot.api.messages.send(
                        user_id=target_id,
                        random_id=0,
                        message=f"🏰 Вас пригласили в клан '{clan_name}'!\n"
                                f"Чтобы принять приглашение, напишите в любом чате: /клан принять"
                    )
                except:
                    pass
            else:
                await message.reply(f"❌ {result['message']}", disable_mentions=1)

            return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'поиск':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            if len(arguments) < 3:
                await message.reply("❌ Укажите название для поиска!\nПример: /клан поиск воины", disable_mentions=1)
                return True

            search_query = " ".join(arguments[2:])
            clans = await find_clans_by_name(search_query)

            if not clans:
                await message.reply(f"❌ Кланы по запросу '{search_query}' не найдены.", disable_mentions=1)
                return True

            clans_list = []
            for clan in clans:
                clan_id, name, tag, level, members = clan
                clans_list.append(f"• {name} {tag} | ID: {clan_id} | Ур.{level} | 👥 {members}")

            clans_text = "\n".join(clans_list)
            await message.reply(f"🔍 Найденные кланы:\n\n{clans_text}", disable_mentions=1)

            return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'принять':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Получаем все приглашения пользователя
            sql.execute("""
                    SELECT ci.invite_id, ci.clan_id, ci.user_id, ci.inviter_id, ci.date, c.name, c.tag 
                    FROM clan_invites ci
                    JOIN clans c ON ci.clan_id = c.clan_id
                    WHERE ci.user_id = ?
                """, (user_id,))

            invites = sql.fetchall()

            if not invites:
                await message.reply("❌ У вас нет активных приглашений в кланы!", disable_mentions=1)
                return True

            # Если указан номер приглашения
            if len(arguments) >= 3:
                try:
                    invite_num = int(arguments[2]) - 1
                    if 0 <= invite_num < len(invites):
                        invite = invites[invite_num]
                        invite_id = invite[0]
                        clan_id = invite[1]
                        clan_name = invite[5]

                        # Проверяем, не в клане ли уже пользователь
                        existing_clan = await get_user_clan(user_id)
                        if existing_clan:
                            await message.reply(
                                "❌ Вы уже состоите в клане! Покиньте текущий клан перед вступлением в новый.",
                                disable_mentions=1)
                            return True

                        # Добавляем в клан
                        result = await add_clan_member(clan_id, user_id, user_id)

                        if result["success"]:
                            # Удаляем приглашение
                            sql.execute("DELETE FROM clan_invites WHERE invite_id = ?", (invite_id,))

                            # Удаляем все остальные приглашения этого пользователя
                            sql.execute("DELETE FROM clan_invites WHERE user_id = ?", (user_id,))

                            database.commit()

                            await message.reply(f"✅ Вы вступили в клан '{clan_name}'!", disable_mentions=1)
                        else:
                            await message.reply(f"❌ {result['message']}", disable_mentions=1)
                    else:
                        await message.reply("❌ Неверный номер приглашения!", disable_mentions=1)
                except ValueError:
                    await message.reply("❌ Укажите корректный номер приглашения!", disable_mentions=1)
            else:
                # Показываем список приглашений
                invites_list = []
                for i, invite in enumerate(invites, 1):
                    clan_name = invite[5]
                    clan_tag = invite[6]
                    inviter_id = invite[3]
                    date_str = invite[4].split('.')[0] if invite[4] else "неизвестно"

                    try:
                        inviter_name = await get_user_or_group_name(inviter_id)
                        invites_list.append(f"{i}. {clan_name} {clan_tag} | от: {inviter_name} | {date_str}")
                    except:
                        invites_list.append(f"{i}. {clan_name} {clan_tag} | от: ID{inviter_id} | {date_str}")

                invites_text = "\n".join(invites_list)
                await message.reply(
                    f"📨 Ваши приглашения в кланы:\n\n{invites_text}\n\n"
                    f"Чтобы принять, напишите: /клан принять [номер]",
                    disable_mentions=1
                )

            return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'кикнуть':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Проверяем, состоит ли пользователь в клане
            user_clan = await get_user_clan(user_id)
            if not user_clan:
                await message.reply("❌ Вы не состоите в клане!", disable_mentions=1)
                return True

            # Проверяем права (только лидер и зам могут кикать)
            if user_clan["role"] not in ['leader', 'deputy']:
                await message.reply("❌ Только лидер и его заместитель могут кикать участников!", disable_mentions=1)
                return True

            # Определяем цель
            target_id = None
            if message.reply_message:
                target_id = message.reply_message.from_id
            elif len(arguments) >= 3 and await getID(arguments[2]):
                target_id = await getID(arguments[2])
            else:
                await message.reply("❌ Укажите пользователя!", disable_mentions=1)
                return True

            if target_id == user_id:
                await message.reply("❌ Нельзя кикнуть самого себя! Используйте /клан покинуть", disable_mentions=1)
                return True

            # Проверяем, что цель в том же клане
            target_clan = await get_user_clan(target_id)
            if not target_clan or target_clan["clan_id"] != user_clan["clan_id"]:
                await message.reply("❌ Этот пользователь не состоит в вашем клане!", disable_mentions=1)
                return True

            # Нельзя кикнуть лидера
            if target_clan["role"] == 'leader':
                await message.reply("❌ Нельзя кикнуть лидера клана!", disable_mentions=1)
                return True

            # Кикаем
            result = await remove_clan_member(target_id, user_clan["clan_id"])

            if result["success"]:
                await message.reply(f"✅ {await get_user_or_group_mention(target_id)} удалён из клана!",
                                    disable_mentions=1)
            else:
                await message.reply(f"❌ {result['message']}", disable_mentions=1)

            return True
        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'покинуть':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Проверяем, состоит ли пользователь в клане
            user_clan = await get_user_clan(user_id)
            if not user_clan:
                await message.reply("❌ Вы не состоите в клане!", disable_mentions=1)
                return True

            # Если пользователь - лидер
            if user_clan["role"] == 'leader':
                # Получаем информацию о клане
                clan = await get_clan_by_id(user_clan["clan_id"])
                members_count = clan["members_count"]

                # Подтверждение удаления клана
                if len(arguments) >= 3 and arguments_lower[2] == 'confirm':
                    # Проверяем, есть ли другие участники в клане
                    if members_count > 1:
                        await message.reply(
                            f"❌ В вашем клане есть другие участники ({members_count - 1} человек)!\n"
                            f"Сначала передайте права лидера другому участнику:\n"
                            f"/клан передать @пользователь confirm",
                            disable_mentions=1
                        )
                        return True

                    # Удаляем клан
                    result = await delete_clan(user_clan["clan_id"])

                    if result["success"]:
                        await log_economy(
                            user_id=user_id,
                            target_id=None,
                            amount=None,
                            log=f"распустил клан {clan['name']}"
                        )
                        await message.reply(
                            f"✅ Клан '{clan['name']}' успешно распущен!\n"
                            f"Все данные клана удалены.",
                            disable_mentions=1
                        )
                    else:
                        await message.reply(f"❌ {result['message']}", disable_mentions=1)
                else:
                    if members_count > 1:
                        await message.reply(
                            f"⚠️ Вы лидер клана и хотите его покинуть?\n\n"
                            f"👥 В клане есть другие участники ({members_count - 1} человек)!\n\n"
                            f"📋 Варианты действий:\n"
                            f"1️⃣ Передать права лидера: /клан передать @пользователь confirm\n"
                            f"2️⃣ Если вы один в клане, клан будет удалён.\n\n"
                            f"❗ Если вы один в клане и хотите удалить его, напишите:\n"
                            f"/клан покинуть confirm",
                            disable_mentions=1
                        )
                    else:
                        await message.reply(
                            f"⚠️ Вы лидер клана и хотите его покинуть?\n\n"
                            f"👤 В клане только вы.\n"
                            f"🏰 Клан будет полностью удалён.\n\n"
                            f"Для подтверждения напишите: /клан покинуть confirm",
                            disable_mentions=1
                        )
                return True

            # Обычный участник покидает клан
            # Подтверждение
            if len(arguments) >= 3 and arguments_lower[2] == 'confirm':
                result = await remove_clan_member(user_id, user_clan["clan_id"])

                if result["success"]:
                    await message.reply("✅ Вы покинули клан!", disable_mentions=1)
                else:
                    await message.reply(f"❌ {result['message']}", disable_mentions=1)
            else:
                await message.reply(
                    "⚠️ Вы уверены, что хотите покинуть клан?\n"
                    "Для подтверждения напишите: /клан покинуть confirm",
                    disable_mentions=1
                )

            return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'удалить':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Проверяем, состоит ли пользователь в клане
            user_clan = await get_user_clan(user_id)
            if not user_clan:
                await message.reply("❌ Вы не состоите в клане!", disable_mentions=1)
                return True

            # Только лидер может удалить клан
            if user_clan["role"] != 'leader':
                await message.reply("❌ Только лидер может удалить клан!", disable_mentions=1)
                return True

            # Получаем информацию о клане
            clan = await get_clan_by_id(user_clan["clan_id"])
            clan_name = clan["name"]
            members_count = clan["members_count"]
            bank = clan["bank"]

            # Подтверждение удаления
            if len(arguments) >= 3 and arguments_lower[2] == 'confirm':
                # Проверяем, есть ли другие участники
                if members_count > 1:
                    await message.reply(
                        f"❌ Нельзя удалить клан, в котором есть другие участники!\n"
                        f"👥 В клане {members_count} человек.\n"
                        f"Сначала исключите всех участников или передайте права.",
                        disable_mentions=1
                    )
                    return True

                # Удаляем клан
                result = await delete_clan(user_clan["clan_id"])

                if result["success"]:
                    await log_economy(
                        user_id=user_id,
                        target_id=None,
                        amount=None,
                        log=f"удалил клан {clan_name}"
                    )
                    await message.reply(
                        f"✅ Клан '{clan_name}' успешно удалён!\n"
                        f"💰 Казна клана ({bank}₽) была утеряна.",
                        disable_mentions=1
                    )
                else:
                    await message.reply(f"❌ {result['message']}", disable_mentions=1)
            else:
                warning_text = (
                    f"⚠️ ВЫ УВЕРЕНЫ, ЧТО ХОТИТЕ УДАЛИТЬ КЛАН?\n\n"
                    f"🏰 Клан: {clan_name}\n"
                    f"👥 Участников: {members_count}\n"
                    f"💰 Казна: {bank:,}₽\n\n"
                    f"❗️ Это действие НЕОБРАТИМО!\n"
                    f"Все данные клана будут безвозвратно удалены.\n\n"
                    f"Для подтверждения напишите: /клан удалить confirm"
                )
                await message.reply(warning_text, disable_mentions=1)

            return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'передать':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Проверяем, состоит ли пользователь в клане
            user_clan = await get_user_clan(user_id)
            if not user_clan:
                await message.reply("❌ Вы не состоите в клане!", disable_mentions=1)
                return True

            # Только лидер может передавать права
            if user_clan["role"] != 'leader':
                await message.reply("❌ Только лидер может передавать права!", disable_mentions=1)
                return True

            # Определяем цель
            target_id = None
            if message.reply_message:
                target_id = message.reply_message.from_id
            elif len(arguments) >= 3 and await getID(arguments[2]):
                target_id = await getID(arguments[2])
            else:
                await message.reply("❌ Укажите пользователя!", disable_mentions=1)
                return True

            if target_id == user_id:
                await message.reply("❌ Нельзя передать права самому себе!", disable_mentions=1)
                return True

            # Проверяем, что цель в том же клане
            target_clan = await get_user_clan(target_id)
            if not target_clan or target_clan["clan_id"] != user_clan["clan_id"]:
                await message.reply("❌ Этот пользователь не состоит в вашем клане!", disable_mentions=1)
                return True

            # Подтверждение
            if len(arguments) >= 4 and arguments_lower[3] == 'confirm':
                result = await transfer_leadership(user_clan["clan_id"], target_id, user_id)

                if result["success"]:
                    await message.reply(f"✅ Права лидера переданы {await get_user_or_group_mention(target_id)}!",
                                        disable_mentions=1)
                else:
                    await message.reply(f"❌ {result['message']}", disable_mentions=1)
            else:
                await message.reply(
                    f"⚠️ Вы уверены, что хотите передать права лидера {await get_user_or_group_mention(target_id)}?\n"
                    f"Для подтверждения напишите: /клан передать @пользователь confirm",
                    disable_mentions=1
                )

            return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'заместитель':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Проверяем, состоит ли пользователь в клане
            user_clan = await get_user_clan(user_id)
            if not user_clan:
                await message.reply("❌ Вы не состоите в клане!", disable_mentions=1)
                return True

            # Только лидер может назначать заместителя
            if user_clan["role"] != 'leader':
                await message.reply("❌ Только лидер может назначать заместителя!", disable_mentions=1)
                return True

            if len(arguments) < 3:
                await message.reply(
                    "❌ Использование:\n"
                    "/клан заместитель добавить @пользователь - назначить заместителя\n"
                    "/клан заместитель удалить @пользователь - снять заместителя\n"
                    "/клан заместитель список - список заместителей",
                    disable_mentions=1
                )
                return True

            subcommand = arguments_lower[2]

            if subcommand == 'добавить':
                if len(arguments) < 4:
                    await message.reply("❌ Укажите пользователя!", disable_ments=1)
                    return True

                # Определяем цель
                target_id = None
                if message.reply_message:
                    target_id = message.reply_message.from_id
                elif len(arguments) >= 4 and await getID(arguments[3]):
                    target_id = await getID(arguments[3])
                else:
                    await message.reply("❌ Укажите пользователя!", disable_mentions=1)
                    return True

                if target_id == user_id:
                    await message.reply("❌ Нельзя назначить заместителем самого себя!", disable_mentions=1)
                    return True

                # Проверяем, что цель в том же клане
                target_clan = await get_user_clan(target_id)
                if not target_clan or target_clan["clan_id"] != user_clan["clan_id"]:
                    await message.reply("❌ Этот пользователь не состоит в вашем клане!", disable_mentions=1)
                    return True

                # Проверяем, не лидер ли уже
                if target_clan["role"] == 'leader':
                    await message.reply("❌ Нельзя назначить лидера заместителем!", disable_mentions=1)
                    return True

                # Назначаем заместителем
                sql.execute("UPDATE clan_members SET role = 'deputy' WHERE user_id = ? AND clan_id = ?",
                            (target_id, user_clan["clan_id"]))
                database.commit()

                await message.reply(
                    f"✅ {await get_user_or_group_mention(target_id)} назначен заместителем лидера клана!\n\n"
                    f"Теперь он может:\n"
                    f"• Приглашать новых участников\n"
                    f"• Исключать участников\n"
                    f"• Снимать деньги из казны\n"
                    f"• Управлять кланом в отсутствие лидера",
                    disable_mentions=1
                )

                # Уведомляем нового заместителя
                try:
                    clan_name = user_clan["name"]
                    await bot.api.messages.send(
                        user_id=target_id,
                        random_id=0,
                        message=f"🏰 Вас назначили заместителем лидера клана '{clan_name}'!\n"
                                f"Теперь у вас есть права управления кланом."
                    )
                except:
                    pass

                return True

            elif subcommand == 'удалить':
                if len(arguments) < 4:
                    await message.reply("❌ Укажите пользователя!", disable_mentions=1)
                    return True

                # Определяем цель
                target_id = None
                if message.reply_message:
                    target_id = message.reply_message.from_id
                elif len(arguments) >= 4 and await getID(arguments[3]):
                    target_id = await getID(arguments[3])
                else:
                    await message.reply("❌ Укажите пользователя!", disable_mentions=1)
                    return True

                # Проверяем, что цель в том же клане
                target_clan = await get_user_clan(target_id)
                if not target_clan or target_clan["clan_id"] != user_clan["clan_id"]:
                    await message.reply("❌ Этот пользователь не состоит в вашем клане!", disable_mentions=1)
                    return True

                # Проверяем, что цель действительно заместитель
                if target_clan["role"] != 'deputy':
                    await message.reply("❌ Этот пользователь не является заместителем!", disable_mentions=1)
                    return True

                # Снимаем заместителя
                sql.execute("UPDATE clan_members SET role = 'member' WHERE user_id = ? AND clan_id = ?",
                            (target_id, user_clan["clan_id"]))
                database.commit()

                await message.reply(
                    f"✅ {await get_user_or_group_mention(target_id)} снят с должности заместителя.",
                    disable_mentions=1)
                return True

            elif subcommand == 'список':
                # Получаем список заместителей
                sql.execute("""
                        SELECT user_id, joined_date, donated 
                        FROM clan_members 
                        WHERE clan_id = ? AND role = 'deputy'
                        ORDER BY joined_date
                    """, (user_clan["clan_id"],))

                deputies = sql.fetchall()

                if not deputies:
                    await message.reply("📋 В клане пока нет заместителей.", disable_mentions=1)
                    return True

                deputies_list = []
                for i, dep in enumerate(deputies, 1):
                    dep_id, joined, donated = dep
                    donated_formatted = f"{donated:,}₽" if donated > 0 else "0₽"
                    deputies_list.append(
                        f"{i}. {await get_user_or_group_mention(dep_id)} | Пожертвовано: {donated_formatted}")

                deputies_text = "\n".join(deputies_list)

                await message.reply(
                    f"📋 Заместители клана '{user_clan['name']}':\n\n{deputies_text}",
                    disable_mentions=1
                )
                return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'казна':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Проверяем, состоит ли пользователь в клане
            user_clan = await get_user_clan(user_id)
            if not user_clan:
                await message.reply("❌ Вы не состоите в клане!", disable_mentions=1)
                return True

            if len(arguments) < 3:
                # Просто показываем казну
                clan = await get_clan_by_id(user_clan["clan_id"])
                await message.reply(
                    f"💰 Казна клана '{clan['name']}': {clan['bank']:,}₽\n"
                    f"💎 Ваш вклад: {user_clan['donated']:,}₽\n\n"
                    f"📥 Положить: /клан казна положить [сумма]\n"
                    f"📤 Снять: /клан казна снять [сумма] (только лидер/зам)",
                    disable_mentions=1
                )
                return True

            subcommand = arguments_lower[2]

            if subcommand == 'положить':
                if len(arguments) < 4:
                    await message.reply("❌ Укажите сумму!", disable_mentions=1)
                    return True

                try:
                    amount = int(arguments[3])
                except ValueError:
                    await message.reply("❌ Укажите корректную сумму!", disable_mentions=1)
                    return True

                result = await clan_deposit(user_id, user_clan["clan_id"], amount)

                if result["success"]:
                    await message.reply(f"✅ {result['message']}", disable_mentions=1)
                else:
                    await message.reply(f"❌ {result['message']}", disable_mentions=1)

            elif subcommand == 'снять':
                # Проверяем права (лидер ИЛИ заместитель могут снимать)
                if user_clan["role"] not in ['leader', 'deputy']:
                    await message.reply("❌ Только лидер и его заместитель могут снимать из казны!",
                                        disable_mentions=1)
                    return True
                if len(arguments) < 4:
                    await message.reply("❌ Укажите сумму!", disable_mentions=1)
                    return True

                try:
                    amount = int(arguments[3])
                except ValueError:
                    await message.reply("❌ Укажите корректную сумму!", disable_mentions=1)
                    return True

                result = await clan_withdraw(user_id, user_clan["clan_id"], amount)

                if result["success"]:
                    await message.reply(f"✅ {result['message']}", disable_mentions=1)
                else:
                    await message.reply(f"❌ {result['message']}", disable_mentions=1)

            return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'топ':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            top_clans = await get_top_clans(15)

            if not top_clans:
                await message.reply("❌ Пока нет ни одного клана! Создайте первый: /клан создать [название] [тег]",
                                    disable_mentions=1)
                return True

            clans_list = []
            for i, clan in enumerate(top_clans, 1):
                clan_id, name, tag, level, exp, bank, members, wins, losses = clan
                win_rate = 0
                if wins + losses > 0:
                    win_rate = round(wins / (wins + losses) * 100, 1)

                clans_list.append(f"{i}. {name} {tag} | Ур. {level} | 👥 {members} | 💰 {bank:,}₽ | ⚔️ {win_rate}%")

            clans_text = "\n".join(clans_list)

            await message.reply(
                f"🏆 ТОП КЛАНОВ 🏆\n\n{clans_text}",
                disable_mentions=1
            )

            return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'переименовать':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Проверяем, состоит ли пользователь в клане
            user_clan = await get_user_clan(user_id)
            if not user_clan:
                await message.reply("❌ Вы не состоите в клане!", disable_mentions=1)
                return True

            # Только лидер может переименовывать клан
            if user_clan["role"] != 'leader':
                await message.reply("❌ Только лидер может изменять название клана!", disable_mentions=1)
                return True

            if len(arguments) < 3:
                await message.reply(
                    "❌ Использование:\n"
                    "/клан переименовать [новое название] - изменить только название\n"
                    "/клан переименовать [новое название] [новый тег] - изменить название и тег\n"
                    "/клан переименовать тег [новый тег] - изменить только тег\n\n"
                    f"Текущее название: {user_clan['name']}\n"
                    f"Текущий тег: {user_clan['tag']}",
                    disable_mentions=1
                )
                return True

            # Проверяем, нужно ли менять тег отдельно
            if arguments_lower[2] == 'тег' and len(arguments) >= 4:
                new_tag = arguments[3]

                # Проверяем длину тега
                if len(new_tag) > 5:
                    await message.reply("❌ Тег клана не должен превышать 5 символов!", disable_mentions=1)
                    return True
                if len(new_tag) < 1:
                    await message.reply("❌ Тег не может быть пустым!", disable_mentions=1)
                    return True

                # Проверяем стоимость (переименование тега стоит 25,000₽)
                balance = await get_balance(user_id)
                cost = 25000
                if balance < cost:
                    await message.reply(f"❌ Для изменения тега нужно {cost}₽! У вас: {balance:,}₽",
                                        disable_mentions=1)
                    return True

                # Списываем деньги
                await setmoney(user_id, -cost)

                # Меняем тег
                result = await rename_clan(user_clan["clan_id"], None, new_tag)

                if result["success"]:
                    await log_economy(user_id=user_id, target_id=None, amount=cost,
                                      log=f"изменил тег клана на {new_tag}")
                    await message.reply(f"✅ Тег клана успешно изменён на {new_tag}!", disable_mentions=1)
                else:
                    await message.reply(f"❌ {result['message']}", disable_mentions=1)

                return True

            # Изменение названия (и возможно тега)
            if len(arguments) >= 3:
                new_name = arguments[2]

                # Проверяем длину названия
                if len(new_name) > 30:
                    await message.reply("❌ Название клана не должно превышать 30 символов!", disable_mentions=1)
                    return True
                if len(new_name) < 2:
                    await message.reply("❌ Название должно содержать минимум 2 символа!", disable_mentions=1)
                    return True

                # Проверяем, указан ли новый тег
                new_tag = None
                if len(arguments) >= 4:
                    new_tag = arguments[3]
                    if len(new_tag) > 5:
                        await message.reply("❌ Тег клана не должен превышать 5 символов!", disable_mentions=1)
                        return True

                # Определяем стоимость
                cost = 50000  # Базовая стоимость смены названия
                if new_tag:
                    cost = 75000  # Если меняем и название, и тег

                balance = await get_balance(user_id)
                if balance < cost:
                    await message.reply(f"❌ Для переименования нужно {cost}₽! У вас: {balance:,}₽",
                                        disable_mentions=1)
                    return True

                # Подтверждение
                if len(arguments) >= 5 and arguments_lower[4] == 'confirm':
                    # Списываем деньги
                    await setmoney(user_id, -cost)

                    # Меняем название
                    result = await rename_clan(user_clan["clan_id"], new_name, new_tag)

                    if result["success"]:
                        log_text = f"переименовал клан в {new_name}"
                        if new_tag:
                            log_text += f" с тегом {new_tag}"
                        await log_economy(user_id=user_id, target_id=None, amount=cost, log=log_text)

                        reply_text = f"✅ Клан успешно переименован в {new_name}"
                        if new_tag:
                            reply_text += f" {new_tag}"
                        reply_text += "!"
                        await message.reply(reply_text, disable_mentions=1)
                    else:
                        await message.reply(f"❌ {result['message']}", disable_mentions=1)
                else:
                    confirm_text = (
                        f"⚠️ Подтвердите переименование клана:\n\n"
                        f"Текущее название: {user_clan['name']} {user_clan['tag']}\n"
                        f"Новое название: {new_name}"
                    )
                    if new_tag:
                        confirm_text += f" {new_tag}"
                    confirm_text += f"\n💰 Стоимость: {cost}₽\n\n"
                    confirm_text += "Для подтверждения напишите: /клан переименовать [название]"
                    if new_tag:
                        confirm_text += f" {new_tag}"
                    confirm_text += " confirm"

                    await message.reply(confirm_text, disable_mentions=1)

                return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'сменитьтег':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Проверяем, состоит ли пользователь в клане
            user_clan = await get_user_clan(user_id)
            if not user_clan:
                await message.reply("❌ Вы не состоите в клане!", disable_mentions=1)
                return True

            # Только лидер может менять тег
            if user_clan["role"] != 'leader':
                await message.reply("❌ Только лидер может изменять тег клана!", disable_mentions=1)
                return True

            if len(arguments) < 3:
                await message.reply(
                    f"❌ Укажите новый тег!\n"
                    f"Текущий тег: {user_clan['tag']}\n"
                    f"Пример: /клан сменитьтег [WAR]",
                    disable_mentions=1
                )
                return True

            new_tag = arguments[2]

            # Проверяем формат тега (должен быть в квадратных скобках)
            if not (new_tag.startswith('[') and new_tag.endswith(']')):
                await message.reply("❌ Тег должен быть в квадратных скобках! Например: [WAR]", disable_mentions=1)
                return True

            # Очищаем от скобок для проверки длины
            tag_without_brackets = new_tag[1:-1]
            if len(tag_without_brackets) > 5:
                await message.reply("❌ Тег клана не должен превышать 5 символов (без учёта скобок)!",
                                    disable_mentions=1)
                return True
            if len(tag_without_brackets) < 1:
                await message.reply("❌ Тег не может быть пустым!", disable_mentions=1)
                return True

            # Проверяем стоимость
            balance = await get_balance(user_id)
            cost = 25000
            if balance < cost:
                await message.reply(f"❌ Для смены тега нужно {cost}₽! У вас: {balance:,}₽", disable_mentions=1)
                return True

            # Подтверждение
            if len(arguments) >= 4 and arguments_lower[3] == 'confirm':
                # Списываем деньги
                await setmoney(user_id, -cost)

                # Меняем тег
                result = await rename_clan(user_clan["clan_id"], None, new_tag)

                if result["success"]:
                    await log_economy(user_id=user_id, target_id=None, amount=cost,
                                      log=f"сменил тег клана на {new_tag}")
                    await message.reply(f"✅ Тег клана успешно изменён на {new_tag}!", disable_mentions=1)
                else:
                    await message.reply(f"❌ {result['message']}", disable_mentions=1)
            else:
                await message.reply(
                    f"⚠️ Подтвердите смену тега клана:\n\n"
                    f"Текущий тег: {user_clan['tag']}\n"
                    f"Новый тег: {new_tag}\n"
                    f"💰 Стоимость: {cost}₽\n\n"
                    f"Для подтверждения напишите: /клан сменитьтег {new_tag} confirm",
                    disable_mentions=1
                )

            return True

        if command in ['setexp', 'выдатьнавык', 'setskill']:
            # Проверяем права (только из списка ruk)
            admin_list = await ruklist()
            if user_id not in admin_list:  # ИСПРАВЛЕНО: было 'is not excludeduser_ids'
                await message.reply("❌ Недостаточно прав! Команда доступна только Руководителю (9+)",
                                    disable_mentions=1)
                return True

            if len(arguments) < 3:
                await message.reply(
                    "❌ Использование: /setexp [пользователь] [количество]\n"
                    "Пример: /setexp @durov 100\n"
                    "Пример с реплаем: /setexp 50 (ответив на сообщение)",
                    disable_mentions=1
                )
                return True

            # Определяем пользователя
            target_id = None
            amount_index = 1

            if message.reply_message:
                target_id = message.reply_message.from_id
                amount_index = 1
            else:
                # Пытаемся получить ID из аргументов
                try:
                    # Проверяем, может быть первый аргумент - это число (количество)
                    test_amount = int(arguments[1])
                    # Если это число, значит пользователь не указан
                    await message.reply("❌ Укажите пользователя!", disable_mentions=1)
                    return True
                except ValueError:
                    # Первый аргумент - не число, значит это пользователь
                    potential_id = await getID(arguments[1])
                    if potential_id:
                        target_id = potential_id
                        amount_index = 2
                    else:
                        await message.reply("❌ Не удалось определить пользователя!", disable_mentions=1)
                        return True

            if not target_id:
                await message.reply("❌ Укажите пользователя!", disable_mentions=1)
                return True

            # Получаем количество навыка
            try:
                amount = int(arguments[amount_index])
            except (ValueError, IndexError):
                await message.reply("❌ Укажите корректное количество навыка!", disable_mentions=1)
                return True

            if amount < 1:
                await message.reply("❌ Количество навыка должно быть положительным!", disable_mentions=1)
                return True

            if amount > 10000:
                await message.reply("❌ Максимальное количество навыка за раз: 10,000", disable_mentions=1)
                return True

            # Получаем информацию о пользователе
            target_name = await get_user_or_group_name(target_id)

            # Проверяем, есть ли у пользователя запись в jobs
            sql.execute("SELECT skill FROM jobs WHERE user_id = ?", (target_id,))
            job_data = sql.fetchone()

            if job_data:
                # Обновляем существующий навык
                current_skill = job_data[0]
                new_skill = current_skill + amount
                sql.execute("UPDATE jobs SET skill = ? WHERE user_id = ?", (new_skill, target_id))
            else:
                # Создаём новую запись
                new_skill = amount
                current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')
                sql.execute("INSERT INTO jobs (user_id, skill, last_work_time) VALUES (?, ?, ?)",
                            (target_id, new_skill, current_time))

            # Также сохраняем в user_skills для бед
            sql.execute("INSERT OR REPLACE INTO user_skills (user_id, skill) VALUES (?, ?)", (target_id, new_skill))

            database.commit()

            # Логируем
            await log_economy(
                user_id=user_id,
                target_id=target_id,
                amount=None,
                log=f"выдал {amount} навыка пользователю {target_id}"
            )

            # Отправляем подтверждение
            await message.reply(
                f"✅ Навык успешно выдан!\n\n"
                f"👤 Пользователь: {await get_user_or_group_mention(target_id)}\n"
                f"📊 Получил: +{amount} навыка\n"
                f"📈 Текущий навык: {new_skill}",
                disable_mentions=1
            )

            # Отправляем уведомление пользователю (если это не тот же чат)
            try:
                await bot.api.messages.send(
                    user_id=target_id,
                    random_id=0,
                    message=f"🎁 Вам выдали навык для работы!\n\n"
                            f"👤 Выдал: {await get_user_or_group_mention(user_id)}\n"
                            f"📊 Получено: +{amount} навыка\n"
                            f"📈 Текущий навык: {new_skill}"
                )
            except:
                pass

            return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'война':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Проверяем, состоит ли пользователь в клане
            user_clan = await get_user_clan(user_id)
            if not user_clan:
                await message.reply("❌ Вы не состоите в клане!", disable_mentions=1)
                return True

            # Только лидер может объявлять войну
            if user_clan["role"] != 'leader':
                await message.reply("❌ Только лидер может объявлять войну!", disable_mentions=1)
                return True

            if len(arguments) < 4:
                await message.reply(
                    "❌ Использование: /клан война [название или ID клана] [ставка]\n"
                    "Пример: /клан война ВоиныСвета 50000\n"
                    "Пример по ID: /клан война 5 50000",
                    disable_mentions=1
                )
                return True

            # Определяем клан-противник
            target_input = arguments[2]
            bet_index = 3

            # Пытаемся найти клан по ID
            try:
                target_clan_id = int(target_input)
                target_clan = await get_clan_by_id(target_clan_id)
            except ValueError:
                # Это не ID, ищем по названию
                target_clan = None

                # Собираем название клана (может быть из нескольких слов)
                clan_name_parts = []
                for i in range(3, len(arguments)):
                    try:
                        # Проверяем, не ставка ли это
                        int(arguments[i])
                        bet_index = i
                        break
                    except ValueError:
                        clan_name_parts.append(arguments[i])

                # Если не нашли число до конца, значит последнее слово не ставка
                if not clan_name_parts:
                    clan_name_parts.append(arguments[2])
                    bet_index = 3
                elif bet_index == len(arguments):
                    # Значит не было числа-ставки, берём последнее слово как ставку?
                    bet_index = len(arguments) - 1
                    clan_name_parts = clan_name_parts[:-1]

                clan_name = " ".join(clan_name_parts) if clan_name_parts else target_input

                # Ищем клан по названию (без учёта регистра)
                sql.execute("SELECT clan_id FROM clans WHERE LOWER(name) LIKE LOWER(?)", (f"%{clan_name}%",))
                result = sql.fetchone()

                if result:
                    target_clan = await get_clan_by_id(result[0])
                else:
                    # Пробуем найти по тегу
                    sql.execute("SELECT clan_id FROM clans WHERE LOWER(tag) LIKE LOWER(?)", (f"%{clan_name}%",))
                    result = sql.fetchone()
                    if result:
                        target_clan = await get_clan_by_id(result[0])

            if not target_clan:
                # Показываем похожие кланы
                sql.execute("SELECT clan_id, name, tag FROM clans WHERE name LIKE ? ORDER BY name LIMIT 5",
                            (f"%{target_input}%",))
                similar = sql.fetchall()

                if similar:
                    similar_list = []
                    for s in similar:
                        similar_list.append(f"• {s[1]} {s[2]} (ID: {s[0]})")
                    similar_text = "\n".join(similar_list)
                    await message.reply(
                        f"❌ Клан не найден!\n\n"
                        f"Похожие кланы:\n{similar_text}\n\n"
                        f"Используйте ID клана для точного указания.",
                        disable_mentions=1
                    )
                else:
                    await message.reply("❌ Клан не найден! Проверьте название или используйте ID клана.",
                                        disable_mentions=1)
                return True

            if target_clan["clan_id"] == user_clan["clan_id"]:
                await message.reply("❌ Нельзя объявить войну самому себе!", disable_mentions=1)
                return True

            # Получаем ставку
            try:
                bet = int(arguments[bet_index])
            except (ValueError, IndexError):
                await message.reply("❌ Укажите корректную ставку числом!", disable_mentions=1)
                return True

            if bet < 10000:
                await message.reply("❌ Минимальная ставка для войны: 10,000₽", disable_mentions=1)
                return True

            # Проверяем, не превышает ли ставка казну
            if user_clan["bank"] < bet:
                await message.reply(
                    f"❌ В казне вашего клана недостаточно средств! Доступно: {user_clan['bank']:,}₽",
                    disable_mentions=1)
                return True

            # Создаём войну
            result = await create_clan_war(user_clan["clan_id"], target_clan["clan_id"], bet, user_id)

            if result["success"]:
                # Блокируем средства в казне
                sql.execute("UPDATE clans SET bank = bank - ? WHERE clan_id = ?", (bet, user_clan["clan_id"]))
                database.commit()

                await message.reply(
                    f"⚔️ ВОЙНА ОБЪЯВЛЕНА! ⚔️\n\n"
                    f"🏰 {user_clan['name']} {user_clan.get('tag', '')} vs {target_clan['name']} {target_clan.get('tag', '')}\n"
                    f"💰 Ставка: {bet:,}₽\n\n"
                    f"Ожидайте подтверждения от клана {target_clan['name']}\n"
                    f"ID войны: {result['war_id']}",
                    disable_mentions=1
                )

                # Уведомляем лидера противника
                try:
                    leader_name = await get_user_or_group_name(target_clan["leader_id"])
                    await bot.api.messages.send(
                        user_id=target_clan["leader_id"],
                        random_id=0,
                        message=f"⚔️ ВАШЕМУ КЛАНУ ОБЪЯВИЛИ ВОЙНУ!\n\n"
                                f"Противник: {user_clan['name']}\n"
                                f"Ставка: {bet:,}₽\n"
                                f"ID войны: {result['war_id']}\n\n"
                                f"Чтобы принять войну: /клан принятьвойну {result['war_id']}\n"
                                f"Чтобы отклонить: /клан отклонитьвойну {result['war_id']}"
                    )
                except Exception as e:
                    print(f"Не удалось уведомить лидера: {e}")
            else:
                await message.reply(f"❌ {result['message']}", disable_mentions=1)

            return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'войны':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Проверяем, состоит ли пользователь в клане
            user_clan = await get_user_clan(user_id)
            if not user_clan:
                await message.reply("❌ Вы не состоите в клане!", disable_mentions=1)
                return True

            # Получаем активные войны клана
            sql.execute("""
                    SELECT w.*, c1.name as clan1_name, c1.tag as clan1_tag, 
                           c2.name as clan2_name, c2.tag as clan2_tag
                    FROM clan_wars w
                    JOIN clans c1 ON w.clan1_id = c1.clan_id
                    JOIN clans c2 ON w.clan2_id = c2.clan_id
                    WHERE (w.clan1_id = ? OR w.clan2_id = ?) AND w.status IN ('pending', 'active')
                    ORDER BY w.start_time DESC
                """, (user_clan["clan_id"], user_clan["clan_id"]))

            wars = sql.fetchall()

            if not wars:
                await message.reply("✅ У вашего клана нет активных войн.", disable_mentions=1)
                return True

            wars_list = []
            for war in wars:
                war_id = war[0]
                clan1_name = war[11]
                clan1_tag = war[12] or ""
                clan2_name = war[13]
                clan2_tag = war[14] or ""
                bet = war[3]
                status = war[5]
                score1 = war[8] or 0
                score2 = war[9] or 0

                status_emoji = "⏳" if status == "pending" else "⚔️"
                status_text = "ожидание" if status == "pending" else "в процессе"

                wars_list.append(
                    f"{status_emoji} Война #{war_id}\n"
                    f"   {clan1_name} {clan1_tag} [{score1}] vs {clan2_name} {clan2_tag} [{score2}]\n"
                    f"   Ставка: {bet:,}₽ | Статус: {status_text}"
                )

            wars_text = "\n\n".join(wars_list)
            await message.reply(f"⚔️ Активные войны клана:\n\n{wars_text}", disable_mentions=1)

            return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'принятьвойну':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            if len(arguments) < 3:
                await message.reply("❌ Укажите ID войны!", disable_mentions=1)
                return True

            try:
                war_id = int(arguments[2])
            except ValueError:
                await message.reply("❌ Неверный ID войны!", disable_mentions=1)
                return True

            # Проверяем, состоит ли пользователь в клане
            user_clan = await get_user_clan(user_id)
            if not user_clan:
                await message.reply("❌ Вы не состоите в клане!", disable_mentions=1)
                return True

            # Только лидер может принимать войну
            if user_clan["role"] != 'leader':
                await message.reply("❌ Только лидер может принимать войну!", disable_mentions=1)
                return True

            result = await accept_clan_war(war_id, user_clan["clan_id"])

            if result["success"]:
                await message.reply(
                    f"✅ {result['message']}\n\n"
                    f"⚔️ ВОЙНА НАЧАЛАСЬ! ⚔️\n"
                    f"Правила:\n"
                    f"• Участники могут вызывать друг друга на дуэли\n"
                    f"• Победа в дуэли приносит очко клану\n"
                    f"• Кто наберёт 5 очков - побеждает\n"
                    f"• Победитель забирает весь банк войны",
                    disable_mentions=1
                )
            else:
                await message.reply(f"❌ {result['message']}", disable_mentions=1)

            return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'вызвать':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Проверяем, есть ли активная война у клана
            user_clan = await get_user_clan(user_id)
            if not user_clan:
                await message.reply("❌ Вы не состоите в клане!", disable_mentions=1)
                return True

            sql.execute("""
                SELECT * FROM clan_wars 
                WHERE (clan1_id = ? OR clan2_id = ?) AND status = 'active'
            """, (user_clan["clan_id"], user_clan["clan_id"]))

            war = sql.fetchone()
            if not war:
                await message.reply("❌ У вашего клана нет активной войны!", disable_mentions=1)
                return True

            columns = [description[0] for description in sql.description]
            war_data = dict(zip(columns, war))

            # Определяем цель
            target_id = None
            if message.reply_message:
                target_id = message.reply_message.from_id
            elif len(arguments) >= 3 and await getID(arguments[2]):
                target_id = await getID(arguments[2])
            else:
                await message.reply("❌ Укажите пользователя!\nПример: /клан вызвать @user 5000", disable_mentions=1)
                return True

            # Проверяем, что противник из вражеского клана
            target_clan = await get_user_clan(target_id)
            enemy_clan_id = war_data["clan2_id"] if war_data["clan1_id"] == user_clan["clan_id"] else war_data[
                "clan1_id"]

            if not target_clan or target_clan["clan_id"] != enemy_clan_id:
                await message.reply("❌ Этот пользователь не из вражеского клана!", disable_mentions=1)
                return True

            # Получаем ставку
            if len(arguments) < 4:
                await message.reply("❌ Укажите ставку для дуэли!\nПример: /клан вызвать @user 5000", disable_mentions=1)
                return True

            try:
                bet = int(arguments[3])
            except ValueError:
                await message.reply("❌ Укажите корректную ставку!", disable_mentions=1)
                return True

            if bet < 1000:
                await message.reply("❌ Минимальная ставка: 1000₽", disable_mentions=1)
                return True

            # Проверяем, что ставка не превышает баланс вызывающего
            balance = await get_balance(user_id)
            if balance < bet:
                await message.reply(f"❌ У вас недостаточно средств для ставки! Нужно: {bet}₽", disable_mentions=1)
                return True

            # 💰💵 СПИСЫВАЕМ ДЕНЬГИ С ЛИЧНОГО БАЛАНСА 💵💰
            await setmoney(user_id, -bet)

            # Деньги поступают в казну КЛАНА ВЫЗЫВАЮЩЕГО (не в казну войны!)
            sql.execute("UPDATE clans SET bank = bank + ? WHERE clan_id = ?", (bet, user_clan["clan_id"]))
            database.commit()

            # Создаём сражение
            result = await create_clan_battle(war_data["war_id"], user_id, target_id, bet)

            if result["success"]:
                await message.reply(
                    f"⚔️ Вы вызвали {await get_user_or_group_mention(target_id)} на дуэль во время войны!\n"
                    f"💰 Ставка {bet}₽ зачислена в казну вашего клана.\n"
                    f"💰 Победитель заберёт эту сумму в казну своего клана.\n\n"
                    f"Ожидайте ответа противника...",
                    disable_mentions=1
                )

                # Создаём клавиатуру для принятия вызова
                keyboard = (
                    Keyboard(inline=True)
                    .add(Callback("✅ Принять вызов",
                                  {"cmd": "accept_clan_battle", "battle_id": result["battle_id"],
                                   "user_id": target_id}),
                         color=KeyboardButtonColor.POSITIVE)
                    .row()
                    .add(Callback("❌ Отклонить",
                                  {"cmd": "reject_clan_battle", "battle_id": result["battle_id"]}),
                         color=KeyboardButtonColor.NEGATIVE)
                )

                # Отправляем личное сообщение противнику
                try:
                    await bot.api.messages.send(
                        user_id=target_id,
                        random_id=0,
                        message=f"⚔️ Вас вызвали на дуэль во время клановой войны!\n"
                                f"Противник: {await get_user_or_group_mention(user_id)}\n"
                                f"💰 Ставка: {bet}₽ (победитель заберёт в казну клана)\n\n"
                                f"Деньги уже зачислены в казну вашего клана.",
                        keyboard=keyboard
                    )
                except Exception as e:
                    print(f"Не удалось отправить сообщение: {e}")
            else:
                await message.reply(f"❌ {result['message']}", disable_mentions=1)

            return True

        if command in ['клан', 'clan'] and len(arguments) >= 2 and arguments_lower[1] == 'войнастат':
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            if len(arguments) < 3:
                await message.reply("❌ Укажите ID войны!\nПример: /клан войнастат 1", disable_mentions=1)
                return True

            try:
                war_id = int(arguments[2])
            except ValueError:
                await message.reply("❌ Неверный ID войны!", disable_mentions=1)
                return True

            sql.execute("""
                    SELECT w.*, c1.name as clan1_name, c1.tag as clan1_tag, c1.bank as clan1_bank,
                           c2.name as clan2_name, c2.tag as clan2_tag, c2.bank as clan2_bank
                    FROM clan_wars w
                    JOIN clans c1 ON w.clan1_id = c1.clan_id
                    JOIN clans c2 ON w.clan2_id = c2.clan_id
                    WHERE w.war_id = ?
                """, (war_id,))

            war = sql.fetchone()
            if not war:
                await message.reply("❌ Война не найдена!", disable_mentions=1)
                return True

            # Получаем все битвы в этой войне
            sql.execute("SELECT * FROM clan_battles WHERE war_id = ? ORDER BY battle_id", (war_id,))
            battles = sql.fetchall()

            war_id = war[0]
            clan1_name = war[10]
            clan1_tag = war[11] or ""
            clan1_bank = war[12]
            clan2_name = war[13]
            clan2_tag = war[14] or ""
            clan2_bank = war[15]
            bet = war[3]
            status = war[5]
            score1 = war[8] or 0
            score2 = war[9] or 0

            status_text = "⏳ Ожидание" if status == "pending" else "⚔️ В процессе" if status == "active" else "🏁 Завершена"

            battles_list = []
            for battle in battles:
                battle_id = battle[0]
                user1 = battle[2]
                user2 = battle[3]
                winner = battle[4]
                battle_bet = battle[5]
                battle_status = battle[6]

                if battle_status == "finished" and winner:
                    try:
                        winner_name = await get_user_or_group_name(winner)
                        battles_list.append(
                            f"• Битва #{battle_id}: {await get_user_or_group_mention(user1)} vs {await get_user_or_group_mention(user2)} | Победил {await get_user_or_group_mention(winner)} | Ставка: {battle_bet}₽")
                    except:
                        battles_list.append(
                            f"• Битва #{battle_id}: {await get_user_or_group_mention(user1)} vs {await get_user_or_group_mention(user2)} | Завершена | Ставка: {battle_bet}₽")
                elif battle_status == "pending":
                    battles_list.append(
                        f"• Битва #{battle_id}: {await get_user_or_group_mention(user1)} vs {await get_user_or_group_mention(user2)} | ⏳ Ожидает принятия | Ставка: {battle_bet}₽")

            battles_text = "\n".join(battles_list) if battles_list else "Нет завершённых битв"

            await message.reply(
                f"⚔️ СТАТИСТИКА ВОЙНЫ #{war_id} ⚔️\n\n"
                f"🏰 {clan1_name} {clan1_tag} [{score1}] vs {clan2_name} {clan2_tag} [{score2}]\n"
                f"💰 Ставка за войну: {bet}₽\n"
                f"💰 Казна {clan1_name}: {clan1_bank:,}₽\n"
                f"💰 Казна {clan2_name}: {clan2_bank:,}₽\n"
                f"📊 Статус: {status_text}\n\n"
                f"📋 Битвы:\n{battles_text}",
                disable_mentions=1
            )

            return True

        if command in ['job', 'jobs', 'вакансии', 'работы']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Получаем навык пользователя из отдельной таблицы или jobs
            user_skill = await get_user_skill(user_id)

            # Проверяем, есть ли у пользователя уже работа
            user_job = await get_user_job(user_id)

            if user_job and user_job["job_id"] is not None:  # У пользователя ЕСТЬ работа
                current_job = JOBS_DATA[user_job["job_id"]]

                # Проверяем время до следующей зарплаты
                can_work, hours, minutes = await check_work(user_id)
                time_status = "✅ Можно получить зарплату сейчас!" if can_work else f"⏳ До зарплаты: {hours} ч {minutes} мин"

                await message.reply(
                    f"⚠️ У вас уже есть работа!\n\n"
                    f"💼 Текущая работа: {current_job['name']}\n"
                    f"📊 Ваш навык: {user_skill}\n"
                    f"💰 Зарплата: {current_job['salary']:,}₽\n"
                    f"🕐 {time_status}\n\n"
                    f"Чтобы уволиться, используйте /уволиться\n"
                    f"Чтобы сменить работу, сначала увольтесь",
                    disable_mentions=1
                )
                return True

            # Если пользователь БЕЗ работы - показываем список вакансий
            if len(arguments) < 2:
                jobs_text = ""
                for job_id, job_data in JOBS_DATA.items():
                    jobs_text += f"{job_id}. {job_data['name']}\n"
                    jobs_text += f"   📝 {job_data['description']}\n"
                    jobs_text += f"   🎯 Требуемый навык: {job_data['min_skill']}\n"
                    jobs_text += f"   💰 Зарплата: {job_data['salary']:,}₽\n"
                    jobs_text += f"   📈 Навык за работу: +{job_data['skill_gain']}\n\n"

                jobs_text += f"\n🔹 Ваш текущий навык: {user_skill}\n"
                jobs_text += "🔹 Чтобы устроиться на работу, напишите: /job [номер работы]\n"
                jobs_text += "🔹 Например: /job 1"

                await message.reply(jobs_text, disable_mentions=1)
                return True

            # Пытаемся устроить на выбранную работу
            try:
                job_id = int(arguments[1])
                if job_id not in JOBS_DATA:
                    await message.reply(
                        f"❌ Такой работы не существует! Выберите номер от {min(JOBS_DATA)} до {max(JOBS_DATA)}.",
                        disable_mentions=1
                    )
                    return True

                job_data = JOBS_DATA[job_id]

                # Проверяем навык
                if user_skill < job_data["min_skill"]:
                    await message.reply(
                        f"❌ Вам не хватает навыка для этой работы!\n"
                        f"🎯 Требуется: {job_data['min_skill']} навыка\n"
                        f"📊 У вас: {user_skill} навыка\n\n"
                        f"⚡ Устройтесь на более простую работу и повышайте навык!",
                        disable_mentions=1
                    )
                    return True

                # Устраиваем на работу
                current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')

                # Проверяем, есть ли уже запись в таблице jobs
                sql.execute("SELECT * FROM jobs WHERE user_id = ?", (user_id,))
                existing = sql.fetchone()

                if existing:
                    # Обновляем существующую запись
                    sql.execute("UPDATE jobs SET job_id = ?, last_work_time = ? WHERE user_id = ?",
                                (job_id, current_time, user_id))
                else:
                    # Создаём новую запись
                    sql.execute("INSERT INTO jobs (user_id, job_id, skill, last_work_time) VALUES (?, ?, ?, ?)",
                                (user_id, job_id, user_skill, current_time))

                database.commit()

                await log_economy(user_id=user_id, target_id=None, amount=None,
                                  log=f"устроился на работу {job_data['name']}")

                await message.reply(
                    f"✅ Поздравляем! Вы устроились на работу \"{job_data['name']}\"!\n\n"
                    f"💰 Зарплата: {job_data['salary']:,}₽\n"
                    f"📈 Навык за работу: +{job_data['skill_gain']}\n"
                    f"📊 Ваш навык: {user_skill}\n"
                    f"⏰ Получать зарплату можно каждые 3 часа\n\n"
                    f"💼 Чтобы получить зарплату, используйте /работа",
                    disable_mentions=1
                )

            except ValueError:
                await message.reply("❌ Укажите номер работы цифрой!", disable_mentions=1)
            except Exception as e:
                print(f"Ошибка при устройстве на работу: {e}")
                await message.reply("❌ Произошла ошибка при устройстве на работу. Попробуйте позже.",
                                    disable_mentions=1)

            return True

        if command in ['работа', 'work', 'зарплата']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Проверяем, есть ли у пользователя работа
            sql.execute("SELECT job_id, skill, last_work_time FROM jobs WHERE user_id = ?", (user_id,))
            user_job = sql.fetchone()

            if not user_job or not user_job[0]:
                await message.reply(
                    "❌ У вас нет работы!\n"
                    "📋 Посмотрите доступные вакансии: /job",
                    disable_mentions=1
                )
                return True

            job_id = user_job[0]
            current_skill = user_job[1]
            last_work_time = user_job[2]

            job_data = JOBS_DATA[job_id]

            # Проверяем, можно ли работать сейчас (3 часа с последней зарплаты)
            can_work_result, hours_left, minutes_left = await check_work(user_id)

            if not can_work_result:
                await message.reply(
                    f"⏰ Вы уже получали зарплату недавно или только устроились!\n"
                    f"💼 Ваша работа: {job_data['name']}\n"
                    f"⏳ До следующей зарплаты: {hours_left} ч {minutes_left} мин",
                    disable_mentions=1
                )
                return True

            # Начисляем зарплату
            salary = job_data["salary"]
            skill_gain = job_data["skill_gain"]
            new_skill = current_skill + skill_gain

            current_time = moscow_now().strftime('%Y-%m-%d %H:%M:%S.%f')

            # Обновляем навык и время последней работы
            sql.execute("UPDATE jobs SET skill = ?, last_work_time = ? WHERE user_id = ?",
                        (new_skill, current_time, user_id))

            # Начисляем деньги
            await setmoney(user_id, salary)
            database.commit()

            await log_economy(
                user_id=user_id,
                target_id=None,
                amount=salary,
                log=f"получил зарплату на работе {job_data['name']}"
            )

            salary_formatted = f'{salary:,d}'.replace(',', '.')

            await message.reply(
                f"💼 Вы отработали смену на работе \"{job_data['name']}\"!\n\n"
                f"💰 Получено: {salary_formatted}₽\n"
                f"📈 Навык увеличился на: +{skill_gain}\n"
                f"📊 Текущий навык: {new_skill}\n\n"
                f"⏰ Следующая зарплата через 3 часа",
                disable_mentions=1
            )

            return True

        if command in ['бизнесы', 'businesses', 'бизнессписок']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            text = "🏢 ДОСТУПНЫЕ БИЗНЕСЫ ДЛЯ ПОКУПКИ:\n\n"

            for biz_id, biz in BUSINESS_TYPES.items():
                text += f"{biz_id}. {biz['emoji']} {biz['name']}\n"
                text += f"   💰 Цена: {biz['price']:,}₽\n"
                text += f"   📈 Прибыль в день: {biz['min_profit']:,} - {biz['max_profit']:,}₽\n\n"

            text += "💡 Чтобы купить бизнес: /купбиз [номер]"

            await message.reply(text, disable_mentions=1)
            return True

        if command in ['бизнес', 'mybusiness', 'моибизнесы']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            businesses = await get_user_businesses(user_id)

            if not businesses:
                await message.reply(
                    "❌ У вас нет бизнесов!\n"
                    "Посмотрите доступные: /бизнесы",
                    disable_mentions=1
                )
                return True

            text = f"🏬 БИЗНЕСЫ {await get_user_or_group_mention(user_id)}:\n\n"

            for biz in businesses:
                # id, user_id, biz_id, purchase_date, last_collected, balance, name, emoji, min_profit, max_profit
                biz_id = biz[2]
                biz_name = biz[6] if len(biz) > 6 else "Неизвестный бизнес"
                biz_emoji = biz[7] if len(biz) > 7 else "🏢"
                balance = biz[5] if len(biz) > 5 else 0
                last_collected = biz[4] if len(biz) > 4 else None

                if last_collected:
                    try:
                        last_time = datetime.strptime(last_collected, '%Y-%m-%d %H:%M:%S.%f')
                        current_time = moscow_now()
                        time_diff = current_time - last_time
                        hours_passed = time_diff.total_seconds() / 3600

                        if hours_passed >= 24:
                            time_left = "✅ Можно собрать!"
                        else:
                            hours_left = 24 - hours_passed
                            hours = int(hours_left)
                            minutes = int((hours_left - hours) * 60)
                            time_left = f"⏰ {hours}ч {minutes}мин"
                    except:
                        time_left = "⏰ Информация недоступна"
                else:
                    time_left = "⏰ Информация недоступна"

                text += f"{biz_id}. {biz_emoji} {biz_name}\n"
                text += f"   💸 На счету: {balance:,}₽\n"
                text += f"   ⏳ {time_left}\n\n"

            text += "💡 Команды:\n"
            text += "• /собратьбиз [номер] - собрать прибыль\n"
            text += "• /снятьбиз [номер] [сумма] - снять деньги\n"
            text += "• /продбиз [номер] - продать бизнес"

            await message.reply(text, disable_mentions=1)
            return True

        if command in ['купбиз', 'buybusiness', 'купитьбизнес']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            if len(arguments) < 2:
                await message.reply(
                    "❌ Укажите номер бизнеса!\n"
                    "Пример: /купбиз 1\n"
                    "Посмотреть список: /бизнесы",
                    disable_mentions=1
                )
                return True

            try:
                biz_id = int(arguments[1])
            except ValueError:
                await message.reply("❌ Укажите корректный номер бизнеса!", disable_mentions=1)
                return True

            if biz_id not in BUSINESS_TYPES:
                await message.reply("❌ Бизнеса с таким номером не существует!", disable_mentions=1)
                return True

            result = await buy_business(user_id, biz_id)

            if result["success"]:
                await message.reply(result["message"], disable_mentions=1)
            else:
                await message.reply(f"❌ {result['message']}", disable_mentions=1)

            return True

        if command in ['продбиз', 'sellbusiness', 'продатьбизнес']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            if len(arguments) < 2:
                await message.reply(
                    "❌ Укажите номер бизнеса!\n"
                    "Пример: /продбиз 1\n"
                    "Ваши бизнесы: /бизнес",
                    disable_mentions=1
                )
                return True

            try:
                biz_id = int(arguments[1])
            except ValueError:
                await message.reply("❌ Укажите корректный номер бизнеса!", disable_mentions=1)
                return True

            # Подтверждение
            if len(arguments) >= 3 and arguments_lower[2] == 'confirm':
                result = await sell_business(user_id, biz_id)

                if result["success"]:
                    await message.reply(result["message"], disable_mentions=1)
                else:
                    await message.reply(f"❌ {result['message']}", disable_mentions=1)
            else:
                business = BUSINESS_TYPES.get(biz_id)
                if not business:
                    await message.reply("❌ Бизнеса с таким номером не существует!", disable_mentions=1)
                    return True

                # Проверяем, есть ли у пользователя такой бизнес
                user_biz = await get_business_by_id(user_id, biz_id)
                if not user_biz:
                    await message.reply("❌ У вас нет такого бизнеса!", disable_mentions=1)
                    return True

                refund = int(business["price"] * 0.7)
                balance = user_biz[5]

                await message.reply(
                    f"⚠️ ПРОДАЖА БИЗНЕСА\n\n"
                    f"{business['emoji']} {business['name']}\n"
                    f"💰 Цена покупки: {business['price']:,}₽\n"
                    f"💵 Вы получите: {refund:,}₽ (70%)\n"
                    f"💸 На счету бизнеса: {balance:,}₽\n"
                    f"💎 Итого: {refund + balance:,}₽\n\n"
                    f"❗ Продажа необратима!\n\n"
                    f"Для подтверждения: /продбиз {biz_id} confirm",
                    disable_mentions=1
                )

            return True

        if command in ['собратьбиз', 'collectbusiness', 'собратьприбыль']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            biz_id = None

            if len(arguments) >= 2:
                try:
                    biz_id = int(arguments[1])
                except ValueError:
                    await message.reply("❌ Укажите корректный номер бизнеса!", disable_mentions=1)
                    return True

            if biz_id:
                # Собираем с конкретного бизнеса
                result = await collect_business_profit(user_id, biz_id)

                if result["success"]:
                    await message.reply(
                        f"{result['message']}\n"
                        f"💰 Текущий баланс бизнеса: {result['new_balance']:,}₽",
                        disable_mentions=1
                    )
                else:
                    if "balance" in result:
                        await message.reply(
                            f"{result['message']}\n"
                            f"💰 Баланс бизнеса: {result['balance']:,}₽",
                            disable_mentions=1
                        )
                    else:
                        await message.reply(f"❌ {result['message']}", disable_mentions=1)
            else:
                # Собираем со всех бизнесов
                businesses = await get_user_businesses(user_id)

                if not businesses:
                    await message.reply("❌ У вас нет бизнесов!", disable_mentions=1)
                    return True

                total_profit = 0
                results = []

                for biz in businesses:
                    biz_id = biz[2]
                    result = await collect_business_profit(user_id, biz_id)

                    if result["success"]:
                        total_profit += result["profit"]
                        results.append(f"{biz[7]} {biz[6]}: +{result['profit']:,}₽")

                if results:
                    await message.reply(
                        f"✅ СОБРАНА ПРИБЫЛЬ СО ВСЕХ БИЗНЕСОВ\n\n"
                        f"{chr(10).join(results)}\n\n"
                        f"💰 Итого: +{total_profit:,}₽",
                        disable_mentions=1
                    )
                else:
                    await message.reply("❌ Не удалось собрать прибыль ни с одного бизнеса!", disable_mentions=1)

            return True

        if command in ['снятьбиз', 'withdrawbusiness', 'снятьсбизнеса']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Если указан номер бизнеса - снимаем с конкретного
            if len(arguments) >= 2:
                try:
                    biz_id = int(arguments[1])
                except ValueError:
                    await message.reply("❌ Укажите корректный номер бизнеса!", disable_mentions=1)
                    return True

                amount = None
                if len(arguments) >= 3:
                    try:
                        amount = int(arguments[2])
                        if amount < 1000:
                            await message.reply("❌ Минимальная сумма снятия: 1,000₽", disable_mentions=1)
                            return True
                    except ValueError:
                        await message.reply("❌ Укажите корректную сумму!", disable_mentions=1)
                        return True

                result = await withdraw_business_profit(user_id, biz_id, amount)

                if result["success"]:
                    await message.reply(
                        f"{result['message']}\n"
                        f"💰 Остаток на счету бизнеса: {result['new_balance']:,}₽",
                        disable_mentions=1
                    )
                else:
                    await message.reply(f"❌ {result['message']}", disable_mentions=1)

                return True

            # Если номер не указан - снимаем со всех бизнесов сразу
            else:
                # Получаем все бизнесы пользователя
                businesses = await get_user_businesses(user_id)

                if not businesses:
                    await message.reply("❌ У вас нет бизнесов!", disable_mentions=1)
                    return True

                total_withdrawn = 0
                results = []

                for biz in businesses:
                    biz_id = biz[2]
                    biz_name = biz[6]
                    biz_emoji = biz[7]
                    balance = biz[5]

                    if balance <= 0:
                        continue

                    # Снимаем все деньги с этого бизнеса
                    result = await withdraw_business_profit(user_id, biz_id, balance)

                    if result["success"]:
                        total_withdrawn += result["withdrawn"]
                        results.append(f"{biz_emoji} {biz_name}: +{result['withdrawn']:,}₽")

                if results:
                    await message.reply(
                        f"✅ СНЯТЫ ДЕНЬГИ СО ВСЕХ БИЗНЕСОВ\n\n"
                        f"{chr(10).join(results)}\n\n"
                        f"💰 Итого снято: +{total_withdrawn:,}₽",
                        disable_mentions=1
                    )
                else:
                    await message.reply("❌ На счетах ваших бизнесов нет денег для снятия!", disable_mentions=1)

                return True

        if command in ['addwhiteruk']:
            admin_list = await ruklist()
            if user_id not in [574393629, 597064735]:  # ИСПРАВЛЕНО: было 'is not excludeduser_ids'
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
            admin_list = await ruklist()
            if user_id not in [574393629, 597064735]:  # ИСПРАВЛЕНО: было 'is not excludeduser_ids'
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
            if user_id not in [574393629, 597064735]:
                return
            i = await ruklist()
            await message.reply(f'{i}')
            return True

        # КОМАНДА /buyvip - ИСПРАВЛЕННАЯ ВЕРСИЯ
        if command in ['buyvip', 'купитьвип']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            if len(arguments) < 2:
                await message.reply(
                    "Для покупки VIP статуса укажите количество дней:\n/buyvip 30 (300,000₽)\n/buyvip 60 (600,000₽)\n/buyvip 90 (900,000₽)",
                    disable_mentions=1)
                return True

            try:
                days = int(arguments[1])
            except ValueError:
                await message.reply("Укажите корректное количество дней (30, 60 или 90)!")
                return True

            if days not in [30, 60, 90]:
                await message.reply("Доступные варианты: 30, 60 или 90 дней!")
                return True

            # Определяем стоимость
            if days == 30:
                cost = 300000
            elif days == 60:
                cost = 600000
            else:  # 90 дней
                cost = 900000

            # Проверяем баланс
            balance = await get_balance(user_id)
            if balance < cost:
                await message.reply(f'У вас недостаточно средств! Нужно {cost:,}₽, а у вас {balance:,}₽')
                return True

            # Списание денег
            await setmoney(user_id, -cost)

            # Установка VIP статуса
            await set_user_date(user_id, days)
            await log_economy(user_id=user_id, target_id=None, amount=None, log=f"купил(-а) вип-статус")
            cost_formatted = f'{cost:,}'.replace(',', '.')
            await message.reply(f'✅ Вы успешно купили VIP статус на {days} дней за {cost_formatted}₽!')
            return True

        SUBS_FILE = "SUBS_FILE.json"

        if command in ['подписка']:
            SUBS_FILE = "SUBS_FILE.json"
            PUB_ID = "232598001"
            subs = load_data(SUBS_FILE)
            user_key = str(user_id)
            if subs.get(user_key):
                await message.reply("Вы уже активировали подписку и получили награду.", disable_mentions=1)
                return True

            try:
                resp = await bot.api.groups.is_member(group_id=PUB_ID, user_id=user_id)
                member = getattr(resp, "member", None)
                if member is None:
                    member = bool(resp)
            except Exception as e:
                print(f"[подписка] is_member error: {e}")
                member = False

            if not member:
                await message.reply("❗ Подпишитесь на сообщество, https://vk.ru/public232598001",
                                    disable_mentions=1)
                return True

            await set_user_date(user_id, 10)
            await setmoney(user_id, 1000000)
            subs[user_key] = {
                "time": moscow_now().isoformat(),
                "reward": {"money": 1000000, "vip": 10}
            }
            save_data(SUBS_FILE, subs)
            await message.reply(
                f"✅ {await get_user_or_group_mention(user_id)} вы подписались на сообщество и получили бонус: 1.000.000$ и VIP на 10 дней.",
                disable_mentions=1)
            return True

        if command in ['allpromo', 'promolist']:
            admin_list = await ruklist()
            if user_id not in admin_list:  # ИСПРАВЛЕНО: было 'is not excludeduser_ids'
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            await gcheckpromo(message)
            return True

        if command in ['setmoney', 'givemoney']:
            if user_id not in [574393629, 597064735]:
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
            umoney = int(arguments[2])
            await log_economy(user_id=user_id, target_id=user, amount=umoney,
                              log=f"выдал(-а) {umoney}p пользователю {user}")
            await setmoney(user, umoney)
            umoney = f'{umoney:,d}'.replace(',', '.')
            await message.answer(
                f"{await get_user_or_group_mention(user_id)} выдал {umoney}₽ {await get_user_or_group_mention(user)}!",
                disable_mentions=1)
            return True

        if command in ['newpromo', 'setpromo']:
            admin_list = await ruklist()
            if user_id not in [574393629, 597064735]:  # ИСПРАВЛЕНО: было 'is not excludeduser_ids'
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            table_name = str(arguments[1])
            column_name = str(arguments[2])
            column_type = int(arguments[3])
            money = int(arguments[4])
            print(table_name, column_name, column_type, money)
            try:
                await setpromo(table_name, column_name, column_type, money)
                await message.reply(
                    f"Успешно создан промокод {table_name} со статусом {column_name}, ВИП {column_type}, Деньги {money}")
                return True
            except:
                await message.reply("Ошибка")
                return True

        # ================== КОМАНДЫ БРАКОВ ==================
        if command in ['брак', 'marry', 'женитьба']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Показываем справку, если нет аргументов
            if len(arguments) < 2:
                marriage = await get_user_marriage(user_id)

                if marriage:
                    spouse_id = marriage["spouse_id"]
                    spouse_name = marriage["spouse_name"]
                    marriage_date = marriage["marriage_date"][:10] if marriage["marriage_date"] else "неизвестно"

                    await message.reply(
                        f"💍 ВЫ В БРАКЕ\n\n"
                        f"👰 Супруг(а): {await get_user_or_group_mention(spouse_id)}\n"
                        f"📅 Дата брака: {marriage_date}\n\n"
                        f"Команды:\n"
                        f"• /развод - расторгнуть брак\n"
                        f"• /брак предложить @пользователь - сделать предложение\n"
                        f"• /брак принять - принять предложение",
                        disable_mentions=1
                    )
                else:
                    await message.reply(
                        "💍 СИСТЕМА БРАКОВ\n\n"
                        "Команды:\n"
                        "• /брак предложить @пользователь - сделать предложение\n"
                        "• /брак принять - принять предложение\n"
                        "• /брак список - список предложений\n"
                        "• /развод - развестись\n"
                        "• /брак топ - статистика браков",
                        disable_mentions=1
                    )
                return True

            subcommand = arguments_lower[1]

            # ПРЕДЛОЖИТЬ БРАК
            if subcommand in ['предложить', 'offer', 'предложение']:
                # Определяем цель
                target_id = None
                if message.reply_message:
                    target_id = message.reply_message.from_id
                elif len(arguments) >= 3 and await getID(arguments[2]):
                    target_id = await getID(arguments[2])
                else:
                    await message.reply("❌ Укажите пользователя!\nПример: /брак предложить @user", disable_mentions=1)
                    return True

                # Создаём предложение
                result = await create_marriage_proposal(user_id, target_id)

                if result["success"]:
                    # Отправляем уведомление в личку (если возможно)
                    try:
                        user_name = await get_user_or_group_name(user_id)
                        await bot.api.messages.send(
                            user_id=target_id,
                            random_id=0,
                            message=f"💍 Вам сделали предложение!\n\n"
                                    f"От: {await get_user_or_group_mention(user_id)}\n"
                                    f"ID предложения: {result['proposal_id']}\n\n"
                                    f"Чтобы принять: /брак принять {result['proposal_id']}"
                        )
                    except:
                        pass

                    await message.reply(
                        f"✅ {result['message']}\n"
                        f"ID предложения: {result['proposal_id']}\n\n"
                        f"Пользователь может принять его командой: /брак принять {result['proposal_id']}",
                        disable_mentions=1
                    )
                else:
                    await message.reply(f"❌ {result['message']}", disable_mentions=1)

                return True

            # ПРИНЯТЬ ПРЕДЛОЖЕНИЕ
            elif subcommand in ['принять', 'accept', 'да']:
                if len(arguments) < 3:
                    # Показываем список предложений
                    proposals = await get_user_proposals(user_id)

                    if not proposals:
                        await message.reply("❌ У вас нет активных предложений!", disable_mentions=1)
                        return True

                    proposals_list = []
                    for prop in proposals:
                        prop_id = prop[0]
                        from_id = prop[1]
                        from_name = await get_user_or_group_name(from_id)
                        date_str = prop[3][:16] if prop[3] else "неизвестно"
                        proposals_list.append(
                            f"• ID: {prop_id} | От: {await get_user_or_group_mention(from_id)} | {date_str}")

                    proposals_text = "\n".join(proposals_list)
                    await message.reply(
                        f"📨 ВАШИ ПРЕДЛОЖЕНИЯ\n\n{proposals_text}\n\n"
                        f"Чтобы принять: /брак принять [ID]\n"
                        f"Чтобы отклонить: /брак отклонить [ID]",
                        disable_mentions=1
                    )
                    return True

                try:
                    proposal_id = int(arguments[2])
                except ValueError:
                    await message.reply("❌ Укажите корректный ID предложения!", disable_mentions=1)
                    return True

                result = await accept_marriage_proposal(proposal_id, user_id)

                if result["success"]:
                    # Получаем имена
                    user1_name = await get_user_or_group_name(result["user1"])
                    user2_name = await get_user_or_group_name(result["user2"])

                    await message.reply(
                        f"💍 ПОЗДРАВЛЯЕМ С БРАКОМ!\n\n"
                        f"👰 {await get_user_or_group_mention(result['user1'])}\n"
                        f"🤵 {await get_user_or_group_mention(result['user2'])}\n\n"
                        f"💞 Теперь вы муж и жена!\n"
                        f"💍 Брак отображается в профиле и балансе!",
                        disable_mentions=1
                    )

                    # Рассылаем уведомление во все чаты, где есть бот


                else:
                    await message.reply(f"❌ {result['message']}", disable_mentions=1)

                return True

            # ОТКЛОНИТЬ ПРЕДЛОЖЕНИЕ
            elif subcommand in ['отклонить', 'reject', 'нет']:
                if len(arguments) < 3:
                    await message.reply("❌ Укажите ID предложения!", disable_mentions=1)
                    return True

                try:
                    proposal_id = int(arguments[2])
                except ValueError:
                    await message.reply("❌ Укажите корректный ID предложения!", disable_mentions=1)
                    return True

                result = await reject_marriage_proposal(proposal_id, user_id)

                if result["success"]:
                    await message.reply(f"✅ {result['message']}", disable_mentions=1)
                else:
                    await message.reply(f"❌ {result['message']}", disable_mentions=1)

                return True

            # СПИСОК ПРЕДЛОЖЕНИЙ
            elif subcommand in ['список', 'list', 'мои']:
                proposals = await get_user_proposals(user_id)

                if not proposals:
                    await message.reply("❌ У вас нет активных предложений!", disable_mentions=1)
                    return True

                proposals_list = []
                for prop in proposals:
                    prop_id = prop[0]
                    from_id = prop[1]
                    to_id = prop[2]
                    date_str = prop[3][:16] if prop[3] else "неизвестно"

                    if from_id == user_id:
                        # Исходящие
                        to_name = await get_user_or_group_name(to_id)
                        proposals_list.append(
                            f"📤 Исходящее ID:{prop_id} → {await get_user_or_group_mention(to_id)} | {date_str}")
                    else:
                        # Входящие
                        from_name = await get_user_or_group_name(from_id)
                        proposals_list.append(
                            f"📥 Входящее ID:{prop_id} ← {await get_user_or_group_mention(from_id)} | {date_str}")

                proposals_text = "\n".join(proposals_list)
                await message.reply(
                    f"📨 ВАШИ ПРЕДЛОЖЕНИЯ\n\n{proposals_text}",
                    disable_mentions=1
                )
                return True

            # ТОП БРАКОВ
            elif subcommand in ['топ', 'top', 'статистика']:
                stats = await get_marriage_stats()
                await message.reply(stats, disable_mentions=1)
                return True

        # КОМАНДА РАЗВОД
        if command in ['развод', 'divorce', 'развестись']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            confirm = len(arguments) >= 2 and arguments_lower[1] == 'confirm'

            result = await divorce(user_id, confirm)

            if result.get("need_confirm"):
                await message.reply(result["message"], disable_mentions=1)
            elif result["success"]:
                await message.reply(result["message"], disable_mentions=1)


            else:
                await message.reply(f"❌ {result['message']}", disable_mentions=1)

            return True

        if command in ['delpromo']:
            admin_list = await ruklist()
            if user_id not in [574393629, 597064735]:  # ИСПРАВЛЕНО: было 'is not excludeduser_ids'
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            table_name = str(arguments[1])
            try:
                await ensure_column_delete(table_name)
                await message.reply(f"Успешно")
                return True
            except:
                await message.reply("Ошибка")
                return True

        if command in ['delmoney', 'delbalance']:
            if user_id not in [574393629, 597064735]:
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
            balance = await get_balance(user)
            await delmoney(user)
            await log_economy(user_id=user_id, target_id=user, amount=balance,
                              log=f"обнулил(-а) весь баланс {balance}$ у пользователя {user}")

            await message.answer(
                f"{await get_user_or_group_mention(user_id)} удалил баланс {balance}p y {await get_user_or_group_mention(user)}!",
                disable_mentions=1)
            return True

        if command in ['вьебать']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
                arguments = message.text.split()
                try:
                    umoney = int(arguments[1])
                except:
                    print('error')
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if user == user_id:
                await message.answer('⛔ Вы не можете взаимодествовать сами с собой')
                return True
            await message.reply(
                f"{await get_user_or_group_mention(user_id)} жестко ударил {await get_user_or_group_mention(user)}!",
                attachment='photo-234187998_457239026', disable_mentions=1)
            return True

        if command in ['выебать']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
                arguments = message.text.split()
                try:
                    umoney = int(arguments[1])
                except:
                    print('error')
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if user == user_id:
                await message.answer('⛔ Вы не можете взаимодествовать сами с собой')
                return True
            await message.reply(
                f"{await get_user_or_group_mention(user_id)} смачно трахнул {await get_user_or_group_mention(user)}!",
                attachment='photo-228388169_457239582', disable_mentions=1)
            return True

        if command in ['обоссать']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
                arguments = message.text.split()
                try:
                    umoney = int(arguments[1])
                except:
                    print('error')
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if user == user_id:
                await message.answer('⛔ Вы не можете взаимодествовать сами с собой')
                return True
            await message.reply(
                f"{await get_user_or_group_mention(user_id)} обоссал {await get_user_or_group_mention(user)}!",
                disable_mentions=1)
            return True

        if command in ['отлизать']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
                arguments = message.text.split()
                try:
                    umoney = int(arguments[1])
                except:
                    print('error')
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if user == user_id:
                await message.answer('⛔ Вы не можете взаимодествовать сами с собой')
                return True
            await message.reply(
                f"{await get_user_or_group_mention(user_id)} отлизал(а) {await get_user_or_group_mention(user)}!",
                attachment='photo-228388169_457239048', disable_mentions=1)
            return True

        if command in ['отсосать']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
                arguments = message.text.split()
                try:
                    umoney = int(arguments[1])
                except:
                    print('error')
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if user == user_id:
                await message.answer('⛔ Вы не можете взаимодествовать сами с собой')
                return True
            await message.reply(
                f"{await get_user_or_group_mention(user_id)} отсосал(а) {await get_user_or_group_mention(user)}!",
                attachment='photo-228388169_457239025', disable_mentions=1)
            return True

        if command in ['обнять']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
                arguments = message.text.split()
                try:
                    umoney = int(arguments[1])
                except:
                    print('error')
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if user == user_id:
                await message.answer('⛔ Вы не можете взаимодествовать сами с собой')
                return True
            await message.reply(
                f"{await get_user_or_group_mention(user_id)} обнял(а) {await get_user_or_group_mention(user)}!",
                attachment='photo-228388169_457239026', disable_mentions=1)
            return True

        if command in ['застрелить']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
                arguments = message.text.split()
                try:
                    umoney = int(arguments[1])
                except:
                    print('error')
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if user == user_id:
                await message.answer('⛔ Вы не можете взаимодествовать сами с собой')
                return True
            await message.reply(
                f"{await get_user_or_group_mention(user_id)} застрелил {await get_user_or_group_mention(user)}. Покойся с миром!",
                disable_mentions=1)
            return True

        if command in ['пнуть']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
                arguments = message.text.split()
                try:
                    umoney = int(arguments[1])
                except:
                    print('error')
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if user == user_id:
                await message.answer('⛔ Вы не можете взаимодествовать сами с собой')
                return True
            await message.reply(
                f"{await get_user_or_group_mention(user_id)} пнул {await get_user_or_group_mention(user)}",
                disable_mentions=1)
            return True

        if command in ['поцеловать', 'kiss']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
                arguments = message.text.split()
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if user == user_id:
                await message.answer('⛔ Вы не можете взаимодествовать сами с собой')
                return True
            r = random.randint(2, 1)
            if r == 2:
                await message.reply(
                    f"{await get_user_or_group_mention(user_id)} поцеловал в засос {await get_user_or_group_mention(user)}!",
                    attachment='photo-228388169_457239030', disable_mentions=1)
                return True
            if r == 1:
                await message.reply(
                    f"{await get_user_or_group_mention(user_id)} поцеловал в губы {await get_user_or_group_mention(user)}!",
                    attachment='photo-234187998_457239024', disable_mentions=1)
                return True

        if command in ['трахнуть']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
                arguments = message.text.split()
                try:
                    umoney = int(arguments[1])
                except:
                    print('error')
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if user == user_id:
                await message.answer('⛔ Вы не можете взаимодествовать сами с собой')
                return True
            await message.reply(
                f"{await get_user_or_group_mention(user_id)} трахнул {await get_user_or_group_mention(user)}!",
                attachment='photo-228388169_457239028',
                disable_mentions=1)
            return True

        if command in ['ударить']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
                arguments = message.text.split()
                try:
                    umoney = int(arguments[1])
                except:
                    print('error')
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if user == user_id:
                await message.answer('⛔ Вы не можете взаимодествовать сами с собой')
                return True
            await message.reply(
                f"{await get_user_or_group_mention(user_id)} ударил {await get_user_or_group_mention(user)}!",
                attachment='photo-234187998_457239025', disable_mentions=1)
            return True

        # КОМАНДА /передать С УЧЕТОМ VIP СТАТУСА
        if command in ['передать', 'перевести', 'pay']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            user = int
            umoney = int
            if message.reply_message:
                user = message.reply_message.from_id
                arguments = message.text.split()
                try:
                    umoney = int(arguments[1])
                except:
                    print('error')
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                umoney = int(arguments[2])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True
            if user == user_id:
                await message.answer('⛔ Вы не можете перевести деньги самому себе.')
                return True
            balance = await get_balance(user_id)
            umoney1 = str(umoney)
            if umoney1.startswith('-'):
                await message.answer('Ваше число не может быть отрицательным')
                return True
            if umoney < 10:
                await message.answer('Минимальная сумма для перевода составляет 10₽!')
                return True
            if umoney > balance:
                await message.answer('У вас недостаточно средств')
                return True
            if user < 0:
                await message.reply("Нельзя передавать деньги сообществу!")
                return True
            # Проверяем VIP статус отправителя
            is_vip = await is_vip_active(user_id)

            if is_vip:
                # VIP: комиссия 0%
                commission = 0
                pitog5 = umoney
            else:
                # Обычный пользователь: комиссия 2%
                commission = 2
                pitog4 = umoney * commission / 100
                pitog5 = umoney - pitog4
                pitog5 = int(pitog5)

            pitog = 0 - umoney
            balances = load_data(BALANCES_FILE)

            sender = balances.get(str(user_id), get_balanc(user_id))
            recipient = balances.get(str(user), get_balanc(user))

            # Обновляем статистику
            sender["sent_total"] += umoney
            recipient["received_total"] += pitog5

            balances[str(user_id)] = sender
            balances[str(user)] = recipient

            # Немедленно сохраняем
            save_data(BALANCES_FILE, balances)

            await log_economy(user_id=user_id, target_id=user, amount=pitog5,
                              log=f"передал(-а) {pitog5}р пользователю {user}")
            await log_economy(user_id=user, target_id=None, amount=pitog5,
                              log=f"получил(-а) на баланс {pitog5}р от пользователя {user_id}")
            await setmoney(user_id, -umoney)
            await setmoney(user, pitog5)
            pitog5 = f'{pitog5:,d}'.replace(',', '.')
            umoney_formatted = f'{umoney:,d}'.replace(',', '.')

            await message.answer(
                f"💵 {await get_user_or_group_mention(user_id)} передал {await get_user_or_group_mention(user)} {pitog5}₽, с учетом коммисии {commission}%!",
                disable_mentions=1)
            return True

        if command in ['положить']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            if not arguments:
                await message.answer('Использование: /положить [сумма]')
                return True
            try:
                umoney = int(arguments[1])
            except (IndexError, ValueError):
                await message.answer('Укажите корректную сумму!')
                return True
            umoney1 = str(umoney)
            if umoney1.startswith('-'):
                await message.answer('Ваше число не может быть отрицательным')
                return True
            balance = await get_balance(user_id)
            if balance < umoney:
                await message.reply('У вас недостаточно средств')
                return True
            await setmoney(user_id, -umoney)
            await setbank(user_id, umoney)
            await log_economy(user_id=user_id, target_id=None, amount=umoney, log=f"положил(-а) {umoney}$ в банк")
            umoney = f'{umoney:,d}'.replace(',', '.')
            await message.reply(f'📥 Вы положили на счет банка: {umoney}р')
            return True

        if command in ['снять']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            if not arguments:
                await message.answer('Использование: /снять [сумма]')
                return True
            try:
                umoney = int(arguments[1])
            except (IndexError, ValueError):
                await message.answer('Укажите корректную сумму!')
                return True
            umoney1 = str(umoney)
            if umoney1.startswith('-'):
                await message.answer('Ваше число не может быть отрицательным')
                return True
            bank = await get_bank(user_id)
            if bank < umoney:
                await message.reply('У вас недостаточно средств на счете')
                return True
            await setmoney(user_id, umoney)
            await setbank(user_id, -umoney)
            await log_economy(user_id=user_id, target_id=None, amount=umoney, log=f"снял(-а) {umoney}$ с банка")
            umoney = f'{umoney:,d}'.replace(',', '.')
            await message.reply(f'📤 Вы сняли со счёта в банке: {umoney}р')
            return True

        if command in ['шар', 'Шар', 'грейтинфа', 'инфачто']:
            text = str(arguments[1])
            if not text:
                await message.reply("Вы ничего не спросили")
                return
            procent = random.randint(1, 100)
            await message.reply(f'🤔 Я думаю, что вероятность {procent}%!')
            return

        if command in ['promo', 'промо']:
            try:
                promo = str(arguments[1])
                res = await getpromo(promo)
                print(res)
                print(res)
                if not res:
                    await message.reply('Промокод не найден')
                    return True
                if res:
                    res1 = await getpromo1(promo)
                    print('status:', res1)
                    if res1 == noactive:
                        await message.reply('К сожалению данный промокод больше неактивен, попробуйте другой')
                        return True
                    else:
                        check = await getpromo5(user_id, res)
                        print(check)
                        if check < 2:
                            await message.reply('Вы уже активировали этот промокод')
                            return True
                        print(1233)
                        print(1233)
                        res2 = await getpromo2(promo)
                        print(1233)
                        res3 = await getpromo3(promo)
                        if res2 == 0:
                            await setmoney(user_id, res3)
                            await message.reply(
                                f'Промокод {promo} успешно активирован!\nВам начислено на баланс {res3} рублей')
                            await setpromo5(user_id, promo)
                            return True
                        else:
                            await setmoney(user_id, res3)
                            await set_user_date(user_id, res2)
                            await message.reply(
                                f'Промокод {promo} успешно активирован!\nВам начислено на баланс {res3} рублей и выдан вип статус на {res2} дней.')
                            await setpromo5(user_id, promo)
                            return True
            except:
                await message.reply('Укажите промокод')
                return True

        # ================== КОМАНДА /balance ==================
        if command in ['balance', 'баланс', 'профиль', 'profile']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            admin_list = await ruklist()

            # Определяем, чей профиль смотрим
            target_id = user_id
            if message.reply_message:
                target_id = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                target_id = await getID(arguments[1])
            if target_id < 0:
                await message.reply("Нельзя получать баланс сообщества!")
                return True
            if target_id != user_id:
                sql.execute("SELECT level FROM global_managers WHERE user_id = ?", (target_id,))
                protected_role = sql.fetchone()
                if protected_role and protected_role[0] >= 8:
                    await message.reply("⛔ Баланс пользователей на должности ЗР и выше скрыт.", disable_mentions=1)
                    return True
            # Получаем данные
            balance = await get_balance(target_id)
            bank = await get_bank(target_id)

            # Имущество: дома
            houses = await get_user_houses(target_id)
            houses_count = len(houses)
            most_expensive_house = await get_most_expensive_house(target_id)
            residence = f"{most_expensive_house['emoji']} {most_expensive_house['name']}" if most_expensive_house else "Нет жилья"

            # Имущество: машины
            cars = await get_user_cars(target_id)
            cars_count = len(cars)

            # Имущество: бизнесы
            businesses = await get_user_businesses(target_id)
            businesses_count = len(businesses)

            # Карьера
            sql.execute("SELECT job_id, skill FROM jobs WHERE user_id = ?", (target_id,))
            user_job = sql.fetchone()

            if user_job and user_job[0]:
                job_id = user_job[0]
                if job_id in JOBS_DATA:
                    job_name = JOBS_DATA[job_id]["name"]
                else:
                    job_name = "Неизвестная работа"
                skill = user_job[1] if user_job[1] else 0
            else:
                job_name = "Безработный"
                skill = await get_user_skill(target_id)

            # Клан
            clan_data = await get_user_clan(target_id)
            if clan_data:
                clan_name = f"{clan_data['name']} {clan_data.get('tag', '')}"
            else:
                clan_name = "Отсутствует"

            # Семья (брак)
            marriage = await get_user_marriage(target_id)
            if marriage:
                spouse_id = marriage["spouse_id"]
                spouse_name = marriage["spouse_name"]
                marriage_date = marriage["marriage_date"][:10] if marriage["marriage_date"] else "неизвестно"
                marriage_text = f"💍 В браке с: {spouse_name}\n📅 С: {marriage_date}"
            else:
                marriage_text = "💍 В браке: Нет"

            # VIP статус
            vip_active = await is_vip_active(target_id)
            if vip_active:
                vip_end_date = await get_user_data1(target_id)
                try:
                    end_date = datetime.strptime(vip_end_date, '%Y-%m-%d %H:%M:%S.%f')
                    vip_text = f"⭐ VIP: Активен\n⏳ До: {end_date.strftime('%d.%m.%Y')}"
                except:
                    vip_text = "⭐ VIP: Активен"
            else:
                vip_text = "⭐ VIP: Неактивен"

            # Статистика дуэлей и переводов
            bal = load_data(BALANCES_FILE).get(str(target_id), get_balanc(target_id))

            won_total = bal.get('won_total', 0)
            lost_total = bal.get('lost_total', 0)
            sent_total = bal.get('sent_total', 0)
            received_total = bal.get('received_total', 0)

            # Форматирование чисел
            def fmt(n):
                return f"{n:,}".replace(",", ".")

            # Собираем профиль
            profile_text = (
                f"👤 ПРОФИЛЬ ИГРОКА: {await get_user_or_group_mention(target_id)}\n\n"
                f"💠 ФИНАНСЫ:\n"
                f"💰 Баланс: {fmt(balance)}₽\n"
                f"🏦 В банке: {fmt(bank)}₽\n\n"
                f"💠 ИМУЩЕСТВО:\n"
                f"🚘 Машины: {cars_count}\n"
                f"🏠 Дома: {houses_count}\n"
                f"🏘️ Проживание: {residence}\n"
                f"🏢 Бизнесов: {businesses_count}\n\n"
                f"💠 КАРЬЕРА:\n"
                f"💼 Работа: {job_name}\n"
                f"📊 Навык: {fmt(skill)}\n"
                f"🏰 Клан: {clan_name}\n\n"
                f"💠 СЕМЬЯ:\n"
                f"{marriage_text}\n\n"
                f"💠 СТАТУС:\n"
                f"{vip_text}\n\n"
                f"💠 ДУЭЛИ:\n"
                f"🏆 Победы: {bal.get('won', 0)}\n"
                f"💔 Поражения: {bal.get('lost', 0)}\n\n"
                f"💠 ФИНАНСОВАЯ СТАТИСТИКА:\n"
                f"🎉 Всего выиграно: {fmt(won_total)}₽\n"
                f"💸 Всего проиграно: {fmt(lost_total)}₽\n\n"
                f"💠 ПЕРЕВОДЫ:\n"
                f"📤 Отправлено: {fmt(sent_total)}₽\n"
                f"📥 Получено: {fmt(received_total)}₽"
            )

            await message.reply(profile_text, disable_mentions=1)
            return True

        if command in ['проверитьбиз', 'checkbiz']:
            # Проверяем таблицу business_types
            sql.execute("SELECT * FROM business_types ORDER BY biz_id")
            types = sql.fetchall()
            text = "📊 Бизнесы в таблице business_types:\n"
            for t in types:
                text += f"ID: {t[0]}, {t[1]}, {t[2]}, {t[3]}₽\n"

            # Проверяем бизнесы пользователя
            sql.execute("SELECT * FROM user_businesses WHERE user_id = ?", (user_id,))
            user_biz = sql.fetchall()
            text += f"\n📊 Ваши бизнесы (user_businesses):\n"
            if user_biz:
                for ub in user_biz:
                    text += f"ID: {ub[0]}, biz_id: {ub[2]}, balance: {ub[5]}₽\n"
            else:
                text += "Нет бизнесов\n"

            await message.reply(text, disable_mentions=1)
            return True

        if command in ['пожертвовать']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            money = get_string(arguments, 1)
            money = int(money)
            if not money:
                await message.reply("Укажите cумму пожертвования!")
                return True
            balance = await get_balance(user_id)
            if money > balance:
                await message.answer('У вас недостаточно средств')
                return True
            await setmoney(user_id, -money)
            await setblago(user_id, money)
            await log_economy(user_id=user_id, target_id=None, amount=money,
                              log=f"благотворил(-а) {money}$ в благотворительность")
            await message.reply(
                f'{await get_user_or_group_mention(user_id)} cделал пожертвование в {money}p')

        async def chats_log(user_id=None, target_id=None, role=None, log=None):
            try:
                sql.execute(
                    "INSERT INTO logchats (user_id, target_id, role, log) VALUES (?, ?, ?, ?)",
                    (user_id, target_id, role, log)
                )
                database.commit()
                print(f"[CHATS LOG] {user_id} -> {target_id} | {role} | {log}")
            except Exception as e:
                print(f"[CHATS LOG ERROR] {e}")

        if command in ['логэкономики', 'logeco', 'logeconomy', 'логиэко']:
            if await get_role(user_id, chat_id) < 9:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            target = None
            if message.reply_message:
                target = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                target = await getID(arguments[1])

            if target:
                sql.execute("SELECT * FROM economy WHERE user_id = ? ORDER BY rowid DESC LIMIT 9999999999999", (target,))
                logs = sql.fetchall()

                if not logs:
                    await message.reply(f"У {await get_user_or_group_mention(target)} отсутствуют записи в логах экономики.", disable_mentions=1)
                    return True

                total = len(logs)
                per_page = MAX_LOGS
                max_page = (total + per_page - 1) // per_page

                async def get_economy_page(page: int):
                    start = (page - 1) * per_page
                    end = start + per_page
                    selected = logs[start:end]
                    formatted = []
                    for idx, entry in enumerate(selected, start=start + 1):
                        u_id, t_id, amount, log_text, *rest = entry
                        try:
                            u_info = await bot.api.users.get(user_ids=u_id)
                            u_name = f"{u_info[0].first_name} {u_info[0].last_name}"
                        except:
                            u_name = str(u_id)
                        if t_id:
                            try:
                                t_info = await bot.api.users.get(user_ids=t_id)
                                t_name = f"{t_info[0].first_name} {t_info[0].last_name}"
                                t_display = f"@id{t_id} ({t_name})"
                            except:
                                t_display = f"@id{t_id}"
                        else:
                            t_display = "None"
                        a_display = f"{format_number(amount)}₽" if amount else "None"
                        l_display = log_text if log_text else "—"
                        created_at = rest[0] if rest else "Дата не записана"
                        formatted.append(f"{idx}. @id{u_id} ({u_name}) | Кому: {t_display} | Сколько: {a_display} | Дата: {created_at} | Лог: {l_display}")
                    return formatted

                page = 1
                economy_page = await get_economy_page(page)
                economy_text = "\n\n".join(economy_page)

                keyboard = (
                    Keyboard(inline=True)
                    .add(Callback("⏪", {"command": "economyMinus", "target": target, "page": 1}), color=KeyboardButtonColor.NEGATIVE)
                    .add(Callback("⏩", {"command": "economyPlus", "target": target, "page": 1}), color=KeyboardButtonColor.POSITIVE)
                )

                await message.reply(
                    f"📊 Логи экономики {await get_user_or_group_mention(target)} [1/{max_page}]:\n\n{economy_text}",
                    disable_mentions=1, keyboard=keyboard
                )
                return True

            else:
                sql.execute("SELECT * FROM economy ORDER BY rowid DESC LIMIT 9999999999999")
                logs = sql.fetchall()

                if not logs:
                    await message.reply(f"Логи экономики отсутствуют!", disable_mentions=1)
                    return True

                total = len(logs)
                per_page = MAX_LOGS
                max_page = (total + per_page - 1) // per_page

                async def get_economy_page(page: int):
                    start = (page - 1) * per_page
                    end = start + per_page
                    selected = logs[start:end]
                    formatted = []
                    for idx, entry in enumerate(selected, start=start + 1):
                        u_id, t_id, amount, log_text, *rest = entry
                        try:
                            u_info = await bot.api.users.get(user_ids=u_id)
                            u_name = f"{u_info[0].first_name} {u_info[0].last_name}"
                        except:
                            u_name = str(u_id)
                        if t_id:
                            try:
                                t_info = await bot.api.users.get(user_ids=t_id)
                                t_name = f"{t_info[0].first_name} {t_info[0].last_name}"
                                t_display = f"@id{t_id} ({t_name})"
                            except:
                                t_display = f"@id{t_id}"
                        else:
                            t_display = "None"
                        a_display = f"{format_number(amount)}₽" if amount else "None"
                        l_display = log_text if log_text else "—"
                        created_at = rest[0] if rest else "Дата не записана"
                        formatted.append(f"{idx}. @id{u_id} ({u_name}) | Кому: {t_display} | Сколько: {a_display} | Дата: {created_at} | Лог: {l_display}")
                    return formatted

                page = 1
                economy_page = await get_economy_page(page)
                economy_text = "\n\n".join(economy_page)

                keyboard = (
                    Keyboard(inline=True)
                    .add(Callback("⏪", {"command": "economyAllMinus", "page": 1}), color=KeyboardButtonColor.NEGATIVE)
                    .add(Callback("⏩", {"command": "economyAllPlus", "page": 1}), color=KeyboardButtonColor.POSITIVE)
                )

                await message.reply(
                    f"📊 Общие логи экономики [1/{max_page}]:\n\n{economy_text}",
                    disable_mentions=1, keyboard=keyboard
                )
                return True

        if command in ['topblago', 'топблаго']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            top_10 = await topblago()
            await message.reply(top_10, disable_mentions=1)

        if command in ['porno', 'порно']:
            await message.reply(f'🍆 https://x.yaebymob.com/ - горячая милфа Ярик уже ждет вас))')
            return True

        # КОМАНДА /bonus С УЧЕТОМ VIP СТАТУСА
        if command in ['bonus', 'бонус', 'приз']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            last_bonus = await get_user_data(user_id)
            print('1 last', last_bonus)

            if last_bonus is not None and last_bonus != 0:
                try:
                    lastdate = datetime.strptime(last_bonus, '%Y-%m-%d %H:%M:%S.%f')
                    currentdate = moscow_now()
                    last_bonus = currentdate - lastdate
                    print('l', last_bonus)
                    hours_passed = last_bonus.total_seconds() / 3600

                    if hours_passed < 10:
                        hours_left = 10 - hours_passed
                        hours = int(hours_left)
                        minutes = int((hours_left - hours) * 60)
                        await message.reply(f'⏰ До следующего бонуса осталось: {hours} ч {minutes} мин!')
                        return True
                except Exception as e:
                    print(f'Ошибка парсинга даты: {e}')

            bonus_amount = 200000
            bonus_type = "ежедневный"
            await log_economy(user_id=user_id, target_id=None, amount=bonus_amount,
                              log=f"получил(-а) приз на {bonus_amount}$")
            await setmoney(user_id, bonus_amount)
            await update_last_bonus_time(user_id)
            bonus_amount = f'{bonus_amount:,d}'.replace(',', '.')

            await message.reply(
                f'🎁 Ваш {bonus_type} бонус составляет {bonus_amount}₽!\n'
                f'⏰ Следующий бонус через 10 часов'
            )
            return True

        if command in ['top', 'топ']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            top_10 = await topbalance()
            await message.reply(top_10, disable_mentions=1)

        if command in ['gameon']:
            admin_list = await ruklist()
            if user_id not in admin_list:  # ИСПРАВЛЕНО: было 'is not excluded_user_ids'
                await message.reply('Недостаточно прав', disable_mentions=1)
                return True
            game = await getgame(chat_id)
            await setgame(chat_id, 0)
            await message.reply('Вы включили игровые команды в беседе')
            return True

        if command in ['gameoff']:
            admin_list = await ruklist()
            if user_id not in admin_list:  # ИСПРАВЛЕНО: было 'is not excludeduser_ids'
                await message.reply('Недостаточно прав', disable_mentions=1)
                return True
            game = await getgame(chat_id)
            await setgame(chat_id, 1)
            await message.reply('Вы выключили игровые команды в беседе')
            return True

        if command in ['казино', 'додеп', 'додэп']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            if not arguments:
                await message.answer('Использование: /казино [ставка]')
                return True
            try:
                umoney = int(arguments[1])
            except (IndexError, ValueError):
                await message.answer('🎰 Укажите корректную ставку!')
                return True
            balance = await get_balance(user_id)
            if umoney < 1000:
                await message.reply('Минимальная ставка составляет 1000₽')
                return True
            if umoney > balance:
                await message.reply('🚫 У вас недостаточно средств')
                return True

            # Проверяем VIP статус
            is_vip = await is_vip_active(user_id)

            win = random.randint(1, 2)
            if win == 1:
                # ПРОИГРЫШ
                await setmoney(user_id, -umoney)

                # ОБНОВЛЯЕМ СТАТИСТИКУ ПРОИГРЫША
                balances = load_data(BALANCES_FILE)
                if str(user_id) not in balances:
                    balances[str(user_id)] = get_balanc(user_id)

                user_bal = balances[str(user_id)]
                user_bal["lost_total"] += umoney

                balances[str(user_id)] = user_bal
                save_data(BALANCES_FILE, balances)
                await log_economy(user_id=user_id, target_id=None, amount=umoney,
                                  log=f"сыграл(-а) в игру «Казино» на {umoney}р")
                umoney = f'{umoney:,d}'.replace(',', '.')
                await message.reply(f'🥹 К сожалению, ваша ставка не сыграла, вы проиграли {umoney}₽')
                return True
            else:
                # ВЫИГРЫШ
                if is_vip:
                    # VIP: комиссия 0%
                    commission = 0
                    win_amount = umoney
                else:
                    # Обычный пользователь: комиссия 20%
                    commission = 20
                    win_amount = umoney / 100 * (100 - commission)

                win_amount = int(win_amount)
                await setmoney(user_id, win_amount)

                # ОБНОВЛЯЕМ СТАТИСТИКУ ВЫИГРЫША
                balances = load_data(BALANCES_FILE)
                if str(user_id) not in balances:
                    balances[str(user_id)] = get_balanc(user_id)

                user_bal = balances[str(user_id)]
                user_bal["won_total"] += win_amount

                balances[str(user_id)] = user_bal
                save_data(BALANCES_FILE, balances)
                await log_economy(user_id=user_id, target_id=None, amount=umoney,
                                  log=f"сыграл(-а) в игру «Казино» на {umoney}р")

                win_amount = f'{win_amount:,d}'.replace(',', '.')
                umoney_formatted = f'{umoney:,d}'.replace(',', '.')

                await message.reply(f'🏆 Вы выиграли, вам начислено {win_amount}₽, с учетом комиссии {commission}%')
                return True

        # КОМАНДА /дуэль УЖЕ ОБНОВЛЕНА В КОЛБЭКЕ
        if command in ['duel', 'дуэль']:
            game = await getgame(chat_id)
            print('j', game)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True
            if not arguments:
                await message.answer('Использование: /дуэль [ставка]')
                return True

            try:
                umoney = int(arguments[1])
            except (IndexError, ValueError):
                await message.answer('Укажите корректную ставку!')
                return True

            balance = await get_balance(user_id)

            if umoney < 50:
                await message.answer('Минимальная ставка составляет 50₽')
                return True
            if umoney > balance:
                await message.answer('У вас недостаточно средств')
                return True

            # Создаем клавиатуру для дуэли
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("⚔️ Сразиться",
                              payload={"cmd": "duel_join", "creator": user_id, "stake": umoney, "chat": chat_id}),
                     color=KeyboardButtonColor.POSITIVE)
            )

            user_name = await get_user_or_group_name(user_id)
            umoney1 = f'{umoney:,d}'.replace(',', '.')

            # Отправляем сообщение
            sent_message = await message.answer(
                f'{await get_user_or_group_mention(user_id)} начал дуэль на {umoney1}₽!\n\nЖелающие сразиться - нажимайте кнопку!',
                keyboard=keyboard
            )

            # Получаем ID отправленного сообщения
            try:
                # Пытаемся получить conversation_message_id
                msg_info = await bot.api.messages.get_by_conversation_message_id(
                    peer_id=message.peer_id,
                    conversation_message_ids=[sent_message.conversation_message_id],
                    group_id=message.group_id
                )
                msg_id = msg_info.items[
                    0].conversation_message_id if msg_info.items else sent_message.conversation_message_id
            except:
                msg_id = sent_message.conversation_message_id

            # Сохраняем дуэль
            current_duel[chat_id] = {
                'initiator': user_id,
                'stake': umoney,
                'message_id': msg_id,
                'creator': user_id,
                'chat_id': chat_id
            }

            await log_economy(
                user_id=user_id,
                target_id=None,
                amount=umoney,
                log=f"создал дуэль на {umoney}₽ в чате {chat_id}"
            )

            return True

        if command in ['инфобиз', 'businessinfo', 'инфобизнес']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            if len(arguments) < 2:
                await message.reply(
                    "❌ Укажите номер бизнеса!\n"
                    "Пример: /инфобиз 1",
                    disable_mentions=1
                )
                return True

            try:
                biz_id = int(arguments[1])
            except ValueError:
                await message.reply("❌ Укажите корректный номер бизнеса!", disable_mentions=1)
                return True

            if biz_id not in BUSINESS_TYPES:
                await message.reply("❌ Бизнеса с таким номером не существует!", disable_mentions=1)
                return True

            biz = BUSINESS_TYPES[biz_id]

            # Проверяем, есть ли у пользователя этот бизнес
            user_biz = await get_business_by_id(user_id, biz_id)

            text = f"🏢 ИНФОРМАЦИЯ О БИЗНЕСЕ\n\n"
            text += f"{biz['emoji']} {biz['name']}\n"
            text += f"💰 Цена: {biz['price']:,}₽\n"
            text += f"📈 Прибыль в день: {biz['min_profit']:,} - {biz['max_profit']:,}₽\n"
            text += f"💎 Окупаемость: ~{biz['price'] // biz['min_profit']} дней\n\n"

            if user_biz:
                text += f"✅ У ВАС ЕСТЬ ЭТОТ БИЗНЕС\n"
                text += f"💸 На счету: {user_biz[5]:,}₽\n"
                text += f"📅 Куплен: {user_biz[3][:10]}\n"
            else:
                text += f"❌ У вас нет этого бизнеса\n"
                text += f"💡 Купить: /купбиз {biz_id}"

            await message.reply(text, disable_mentions=1)
            return True

        if command in ['уволиться', 'leavejob', 'увольнение']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Проверяем, есть ли у пользователя работа
            sql.execute("SELECT job_id, skill FROM jobs WHERE user_id = ?", (user_id,))
            current_job = sql.fetchone()

            if not current_job or not current_job[0]:
                await message.reply("❌ Вы и так безработный! Устроиться можно через /job", disable_mentions=1)
                return True

            job_name = JOBS_DATA[current_job[0]]["name"]
            skill = current_job[1]

            # Подтверждение увольнения
            if len(arguments) < 2 or arguments_lower[1] != "confirm":
                await message.reply(
                    f"⚠️ Вы уверены, что хотите уволиться с работы \"{job_name}\"?\n"
                    f"Ваш навык ({skill}) сохранится.\n\n"
                    f"Для подтверждения напишите: /уволиться confirm",
                    disable_mentions=1
                )
                return True

            # Сохраняем навык перед увольнением
            sql.execute("INSERT OR REPLACE INTO user_skills (user_id, skill) VALUES (?, ?)", (user_id, skill))

            # Увольняем (удаляем только работу, но не навык)
            sql.execute("UPDATE jobs SET job_id = NULL WHERE user_id = ?", (user_id,))
            database.commit()

            await log_economy(user_id=user_id, target_id=None, amount=None, log=f"уволился с работы {job_name}")

            await message.reply(
                f"✅ Вы успешно уволились с работы \"{job_name}\"!\n"
                f"📊 Ваш навык сохранён: {skill}\n"
                f"💼 Чтобы найти новую работу, используйте /job",
                disable_mentions=1
            )

            return True

        # ВСТАВЬТЕ ЭТОТ БЛОК КОМАНД В ФУНКЦИЮ on_chat_message
        # (лучше после команды /бизнесы или в соответствующем разделе)

        # ================== КОМАНДЫ ДЛЯ ДОМОВ ==================
        if command in ['дома', 'houses', 'списокдомов']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            text = "🏠 ДОСТУПНЫЕ ДОМА ДЛЯ ПОКУПКИ:\n\n"

            # Показываем первые 20 домов (чтобы не превысить лимит сообщения)
            count = 0
            for house_id, house in HOUSES_DATA.items():
                text += f"{house_id}. {house['emoji']} {house['name']} — {house['price']:,}₽\n"
                count += 1
                if count >= 30:
                    text += f"\n...и ещё {len(HOUSES_DATA) - 30} домов (всего {len(HOUSES_DATA)})"
                    break

            text += "\n\n💡 Чтобы купить дом: /купдом [номер]"
            await message.reply(text, disable_mentions=1)
            return True

        if command in ['купдом', 'buyhouse']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            if len(arguments) < 2:
                await message.reply("❌ Укажите номер дома!\nПример: /купдом 1\nСписок домов: /дома", disable_mentions=1)
                return True

            try:
                house_id = int(arguments[1])
            except ValueError:
                await message.reply("❌ Укажите корректный номер дома!", disable_mentions=1)
                return True

            result = await buy_house(user_id, house_id)

            if result["success"]:
                await message.reply(result["message"], disable_mentions=1)
            else:
                await message.reply(result["message"], disable_mentions=1)

            return True

        if command in ['проддом', 'sellhouse']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            if len(arguments) < 2:
                await message.reply("❌ Укажите номер дома!\nПример: /проддом 1\nВаши дома: /имущ", disable_mentions=1)
                return True

            try:
                house_id = int(arguments[1])
            except ValueError:
                await message.reply("❌ Укажите корректный номер дома!", disable_mentions=1)
                return True

            # Подтверждение
            if len(arguments) >= 3 and arguments_lower[2] == 'confirm':
                result = await sell_house(user_id, house_id)

                if result["success"]:
                    await message.reply(result["message"], disable_mentions=1)
                else:
                    await message.reply(result["message"], disable_mentions=1)
            else:
                if house_id not in HOUSES_DATA:
                    await message.reply("❌ Дома с таким номером не существует!", disable_mentions=1)
                    return True

                # Проверяем, есть ли у пользователя такой дом
                sql.execute("SELECT * FROM houses WHERE user_id = ? AND house_id = ?", (user_id, house_id))
                if not sql.fetchone():
                    await message.reply("❌ У вас нет такого дома!", disable_mentions=1)
                    return True

                price = HOUSES_DATA[house_id]["price"]
                refund = int(price * 0.7)

                await message.reply(
                    f"⚠️ ПРОДАЖА ДОМА\n\n"
                    f"{HOUSES_DATA[house_id]['emoji']} {HOUSES_DATA[house_id]['name']}\n"
                    f"💰 Цена покупки: {price:,}₽\n"
                    f"💵 Вы получите: {refund:,}₽ (70%)\n\n"
                    f"❗ Продажа необратима!\n\n"
                    f"Для подтверждения: /проддом {house_id} confirm",
                    disable_mentions=1
                )

            return True

        # ================== КОМАНДЫ ДЛЯ МАШИН ==================
        if command in ['машины', 'cars', 'списокмашин']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            text = "🚗 ДОСТУПНЫЕ МАШИНЫ ДЛЯ ПОКУПКИ:\n\n"

            # Показываем все машины
            count = 0
            for car_id, car in CARS_DATA.items():
                text += f"{car_id}. {car['emoji']} {car['name']} — {car['price']:,}₽\n"
                count += 1
                if count >= 30:
                    text += f"\n...и ещё {len(CARS_DATA) - 30} машин (всего {len(CARS_DATA)})"
                    break

            text += "\n\n💡 Чтобы купить машину: /купмашин [номер]"
            await message.reply(text, disable_mentions=1)
            return True

        if command in ['купмашин', 'buycar']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            if len(arguments) < 2:
                await message.reply("❌ Укажите номер машины!\nПример: /купмашин 1\nСписок машин: /машины",
                                    disable_mentions=1)
                return True

            try:
                car_id = int(arguments[1])
            except ValueError:
                await message.reply("❌ Укажите корректный номер машины!", disable_mentions=1)
                return True

            result = await buy_car(user_id, car_id)

            if result["success"]:
                await message.reply(result["message"], disable_mentions=1)
            else:
                await message.reply(result["message"], disable_mentions=1)

            return True

        if command in ['продмашин', 'sellcar']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            if len(arguments) < 2:
                await message.reply("❌ Укажите номер машины!\nПример: /продмашин 1\nВаши машины: /имущ",
                                    disable_mentions=1)
                return True

            try:
                car_id = int(arguments[1])
            except ValueError:
                await message.reply("❌ Укажите корректный номер машины!", disable_mentions=1)
                return True

            # Подтверждение
            if len(arguments) >= 3 and arguments_lower[2] == 'confirm':
                result = await sell_car(user_id, car_id)

                if result["success"]:
                    await message.reply(result["message"], disable_mentions=1)
                else:
                    await message.reply(result["message"], disable_mentions=1)
            else:
                if car_id not in CARS_DATA:
                    await message.reply("❌ Машины с таким номером не существует!", disable_mentions=1)
                    return True

                # Проверяем, есть ли у пользователя такая машина
                sql.execute("SELECT * FROM cars WHERE user_id = ? AND car_id = ?", (user_id, car_id))
                if not sql.fetchone():
                    await message.reply("❌ У вас нет такой машины!", disable_mentions=1)
                    return True

                price = CARS_DATA[car_id]["price"]
                refund = int(price * 0.7)

                await message.reply(
                    f"⚠️ ПРОДАЖА МАШИНЫ\n\n"
                    f"{CARS_DATA[car_id]['emoji']} {CARS_DATA[car_id]['name']}\n"
                    f"💰 Цена покупки: {price:,}₽\n"
                    f"💵 Вы получите: {refund:,}₽ (70%)\n\n"
                    f"❗ Продажа необратима!\n\n"
                    f"Для подтверждения: /продмашин {car_id} confirm",
                    disable_mentions=1
                )

            return True

        # ================== ПРОСМОТР ИМУЩЕСТВА ==================
        if command in ['имущ', 'property', 'имущество', 'моё']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Определяем, чьё имущество смотрим
            target_id = user_id
            if message.reply_message:
                target_id = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                target_id = await getID(arguments[1])

            target_name = await get_user_or_group_name(target_id)

            # Получаем дома
            houses = await get_user_houses(target_id)
            houses_count = len(houses)

            houses_text = ""
            if houses:
                for i, house in enumerate(houses[:10], 1):  # Показываем первые 10
                    house_id = house[2]
                    if house_id in HOUSES_DATA:
                        houses_text += f"{i}. {HOUSES_DATA[house_id]['emoji']} {HOUSES_DATA[house_id]['name']}\n"
                if len(houses) > 10:
                    houses_text += f"...и ещё {len(houses) - 10} домов\n"
            else:
                houses_text = "Нет домов\n"

            # Получаем машины
            cars = await get_user_cars(target_id)
            cars_count = len(cars)

            cars_text = ""
            if cars:
                for i, car in enumerate(cars[:10], 1):  # Показываем первые 10
                    car_id = car[2]
                    if car_id in CARS_DATA:
                        cars_text += f"{i}. {CARS_DATA[car_id]['emoji']} {CARS_DATA[car_id]['name']}\n"
                if len(cars) > 10:
                    cars_text += f"...и ещё {len(cars) - 10} машин\n"
            else:
                cars_text = "Нет машин\n"

            # Самое дорогое имущество
            most_expensive_house = await get_most_expensive_house(target_id)
            most_expensive_car = await get_most_expensive_car(target_id)

            residence = "🏠 Нет жилья"
            if most_expensive_house:
                residence = f"{most_expensive_house['emoji']} {most_expensive_house['name']}"

            top_vehicle = "🚗 Нет транспорта"
            if most_expensive_car:
                top_vehicle = f"{most_expensive_car['emoji']} {most_expensive_car['name']}"

            # Рассчитываем общую стоимость имущества
            houses_value = sum(HOUSES_DATA[house[2]]["price"] for house in houses if house[2] in HOUSES_DATA)
            cars_value = sum(CARS_DATA[car[2]]["price"] for car in cars if car[2] in CARS_DATA)
            total_value = houses_value + cars_value

            await message.reply(
                f"🏠 ИМУЩЕСТВО {await get_user_or_group_mention(target_id)}\n\n"
                f"🏘️ Место проживания: {residence}\n"
                f"🚘 Основной транспорт: {top_vehicle}\n"
                f"💰 Общая стоимость имущества: {total_value:,}₽\n\n"
                f"🏠 ДОМА ({houses_count} шт.):\n{houses_text}\n"
                f"🚗 МАШИНЫ ({cars_count} шт.):\n{cars_text}",
                disable_mentions=1
            )
            return True

        if command in ['whitelist', 'вайтлист']:
            sql.execute("SELECT level FROM global_managers WHERE user_id = ?", (user_id,))
            global_role = sql.fetchone()
            if user_id not in (574393629, 597064735) and (not global_role or global_role[0] < 9):
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True
            ensure_top_whitelist_table()
            if len(arguments) >= 2 and arguments_lower[1] in ['list', 'список']:
                sql.execute("SELECT user_id FROM top_whitelist ORDER BY user_id")
                rows = sql.fetchall()
                text = "📋 Исключены из экономических топов:\n" + ("\n".join(f"• {await get_user_or_group_mention(row[0])}" for row in rows) if rows else "Список пуст")
                await message.reply(text, disable_mentions=1)
                return True
            target_id = None
            if message.reply_message:
                target_id = message.reply_message.from_id
            elif len(arguments) >= 2:
                target_id = await getID(arguments[-1])
            if not target_id or target_id < 0:
                await message.reply("Укажите пользователя ответом или ссылкой/ID. Для возврата: /whitelist remove пользователь", disable_mentions=1)
                return True
            remove = len(arguments) >= 3 and arguments_lower[1] in ['remove', 'del', 'удалить', 'вернуть']
            if remove:
                sql.execute("DELETE FROM top_whitelist WHERE user_id = ?", (target_id,))
                action_text = "возвращён в экономические топы"
            else:
                sql.execute("INSERT OR IGNORE INTO top_whitelist (user_id) VALUES (?)", (target_id,))
                action_text = "исключён из экономических топов"
            database.commit()
            await message.reply(f"✅ {await get_user_or_group_mention(target_id)} {action_text}.", disable_mentions=1)
            return True

        if command in ['try', 'трай']:
            phrase = get_string(arguments, 1).strip()
            if not phrase:
                await message.reply("Использование: /try Я везучий", disable_mentions=1)
                return True
            result_try = random.choice(["Удачно", "Неудачно"])
            await message.reply(f"🎲 {phrase} — {result_try}", disable_mentions=1)
            return True

        # ================== КОМАНДЫ МАФИИ В ЧАТЕ ==================
        if command in ['мафия', 'mafia']:
            game_status = await getgame(chat_id)
            if game_status != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Помощь
            if len(arguments) < 2 or arguments_lower[1] in ['помощь', 'help']:
                help_text = (
                    "🎭 ИГРА В МАФИЮ 🎭\n\n"
                    "📋 КОМАНДЫ ДЛЯ ЧАТА:\n"
                    "• /мафия создать - создать новую игру\n"
                    "• /мафия войти - присоединиться к игре\n"
                    "• /мафия выйти - выйти из игры\n"
                    "• /мафия начать - начать игру (только создатель)\n"
                    "• /мафия статус - статус игры\n\n"
                    "🎮 ИГРОВОЙ ПРОЦЕСС:\n"
                    "• Ночью: доктор → комиссар → мафия (выбор через кнопки в ЛС)\n"
                    "• Днём: все голосуют за казнь (выбор через кнопки в ЛС)\n"
                    "• Бот пишет в чат о смене фаз и результатах\n\n"
                    "⚠️ ВАЖНО: Напишите боту любое сообщение в ЛС для начала диалога!"
                )
                await message.reply(help_text, disable_mentions=1)
                return True

            # СОЗДАТЬ ИГРУ
            elif arguments_lower[1] in ['создать', 'create']:
                if chat_id in active_mafia_games:
                    await message.reply("❌ В этом чате уже идёт игра!", disable_mentions=1)
                    return True

                # Проверяем диалог
                try:
                    await bot.api.messages.send(user_id=user_id, message="🔍", random_id=0)
                except:
                    await message.reply("❌ Напишите боту любое сообщение в ЛС, чтобы начать диалог!",
                                        disable_mentions=1)
                    return True

                game = MafiaGame(chat_id, user_id)
                active_mafia_games[chat_id] = game

                await message.reply(
                    f"✅ Игра в мафию создана!\n\n"
                    f"👑 Создатель: {await get_user_or_group_mention(user_id)}\n"
                    f"📋 Вход: /мафия войти\n"
                    f"🚀 Начать: /мафия начать (минимум 4 игрока)",
                    disable_mentions=1
                )
                return True

            # ВОЙТИ В ИГРУ
            elif arguments_lower[1] in ['войти', 'join']:
                if chat_id not in active_mafia_games:
                    await message.reply("❌ Нет активной игры! Создайте: /мафия создать", disable_mentions=1)
                    return True
                async with get_mafia_lock(chat_id):
                    game = active_mafia_games.get(chat_id)
                    if not game:
                        result = {"success": False, "message": "Игра уже была удалена!"}
                    elif game.status != "waiting":
                        result = {"success": False, "message": "Игра уже началась!"}
                    elif user_id in game.players:
                        result = {"success": False, "message": "Вы уже в игре!"}
                    else:
                        result = await join_mafia_game(chat_id, user_id)
                if result["success"]:
                    await message.reply(
                        f"✅ {await get_user_or_group_mention(user_id)} присоединился!\n👥 Игроков: {result['players_count']}/{MAFIA_MIN_PLAYERS}+",
                        disable_mentions=1)
                else:
                    await message.reply(f"❌ {result['message']}", disable_mentions=1)
                return True

            # ВЫЙТИ ИЗ ИГРЫ
            elif arguments_lower[1] in ['выйти', 'leave']:
                if chat_id not in active_mafia_games:
                    await message.reply("❌ Нет активной игры!", disable_mentions=1)
                    return True
                result = await leave_mafia_game(chat_id, user_id)
                if result["success"]:
                    await message.reply(
                        f"✅ {await get_user_or_group_mention(user_id)} покинул игру\n👥 Осталось: {result.get('players_count', 0)}",
                        disable_mentions=1)
                else:
                    await message.reply(f"❌ {result['message']}", disable_mentions=1)
                return True

            # НАЧАТЬ ИГРУ
            elif arguments_lower[1] in ['начать', 'start']:
                result = await start_mafia_game(chat_id, user_id)
                if result["success"]:
                    await message.reply("🎭 ИГРА НАЧАЛАСЬ! 🎭\n\nРоли отправлены в ЛС!", disable_mentions=1)
                else:
                    await message.reply(f"❌ {result['message']}", disable_mentions=1)
                return True

            # СТАТУС ИГРЫ
            elif arguments_lower[1] in ['статус', 'status']:
                if chat_id not in active_mafia_games:
                    await message.reply("❌ Нет активной игры!", disable_mentions=1)
                    return True
                game = active_mafia_games[chat_id]
                current_time_val = time.time()
                time_left = MAFIA_INACTIVE_TIMEOUT - (current_time_val - game.last_action_time)
                if time_left < 0:
                    time_left = 0
                minutes_left = int(time_left // 60)
                seconds_left = int(time_left % 60)
                timer_text = f"⏰ Автоудаление: {minutes_left} мин {seconds_left} сек"
                if game.status == "waiting":
                    status_text = f"🎭 ЛОББИ МАФИИ\n\n{timer_text}\n\n👥 Игроков: {len(game.players)}/{MAFIA_MIN_PLAYERS}+\n"
                    for p in game.players:
                        status_text += f"\n• {await get_user_or_group_mention(p)}"
                    if len(game.players) >= MAFIA_MIN_PLAYERS:
                        status_text += "\n\n✅ Можно начинать: /мафия начать"
                    else:
                        status_text += f"\n\n⏳ Нужно ещё {MAFIA_MIN_PLAYERS - len(game.players)} игроков"
                    status_text += "\n\n🛑 Остановить: /мафия остановить"
                else:
                    alive = [p for p in game.players if game.alive.get(p, False)]
                    dead = [p for p in game.players if not game.alive.get(p, False)]
                    status_text = f"🎭 ИГРА В МАФИЮ\n\n{timer_text}\n\n📊 День {game.day}\n👥 Живых: {len(alive)}/{len(game.players)}\n\n✅ Живые:\n"
                    for p in alive[:10]:
                        status_text += f"• {await get_user_or_group_mention(p)}\n"
                    if dead:
                        status_text += "\n💀 Мёртвые:\n"
                        for p in dead[:5]:
                            status_text += f"• {await get_user_or_group_mention(p)}\n"
                    status_text += f"\n🛑 Остановить: /мафия остановить"
                await message.reply(status_text, disable_mentions=1)
                return True

            # ОСТАНОВИТЬ ИГРУ
            elif arguments_lower[1] in ['остановить', 'stop', 'стоп']:
                if chat_id not in active_mafia_games:
                    await message.reply("❌ Нет активной игры!", disable_mentions=1)
                    return True
                game = active_mafia_games[chat_id]
                if len(arguments) < 3 or arguments_lower[2] != 'confirm':
                    await message.reply(
                        f"⚠️ ВЫ УВЕРЕНЫ, ЧТО ХОТИТЕ ОСТАНОВИТЬ ИГРУ?\n\n👥 Игроков: {len(game.players)}\n📊 Статус: {'Ожидание' if game.status == 'waiting' else f'В процессе (День {game.day})'}\n\n❗ Игра будет полностью остановлена, все данные потеряны.\n\nДля подтверждения: /мафия остановить confirm",
                        disable_mentions=1)
                    return True
                cancel_mafia_timer(game)
                await clear_mafia_mutes(chat_id)
                del active_mafia_games[chat_id]
                await message.reply(
                    f"🛑 ИГРА В МАФИЮ ОСТАНОВЛЕНА!\n\nСоздатель {await get_user_or_group_mention(user_id)} остановил игру.\n\nЧтобы начать новую игру: /мафия создать",
                    disable_mentions=1)
                return True

            # ВРЕМЯ ДО АВТОУДАЛЕНИЯ
            elif arguments_lower[1] in ['время', 'time', 'таймер']:
                if chat_id not in active_mafia_games:
                    await message.reply("❌ Нет активной игры!", disable_mentions=1)
                    return True
                game = active_mafia_games[chat_id]
                current_time_val = time.time()
                time_left = MAFIA_INACTIVE_TIMEOUT - (current_time_val - game.last_action_time)
                if time_left < 0:
                    time_left = 0
                minutes_left = int(time_left // 60)
                seconds_left = int(time_left % 60)
                await message.reply(
                    f"⏱️ ТАЙМЕР НЕАКТИВНОСТИ ИГРЫ\n\n📊 Статус: {'Ожидание' if game.status == 'waiting' else 'В процессе'}\n⏰ Игра будет автоматически удалена через: {minutes_left} мин {seconds_left} сек\n\n💡 Активность обновляется при:\n   • Создании/присоединении/выходе\n   • Начале игры\n   • Любых действиях игроков",
                    disable_mentions=1)
                return True

        # ================== ТОП ПО ИМУЩЕСТВУ ==================
        if command in ['топимущ', 'topwealth', 'топбогатых']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            top_text = await top_wealth(10)
            await message.reply(top_text, disable_mentions=1)
            return True

        if command in ['statsjob', 'профильработы', 'jobstats']:
            game = await getgame(chat_id)
            if game != 0:
                await message.reply('В данной беседе выключены игровые команды')
                return True

            # Определяем, чью статистику смотрим
            target_id = user_id
            if message.reply_message:
                target_id = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                target_id = await getID(arguments[1])

            # Получаем данные о работе и навыке
            sql.execute("SELECT job_id, skill, last_work_time FROM jobs WHERE user_id = ?", (target_id,))
            user_job = sql.fetchone()

            # Получаем сохранённый навык из отдельной таблицы
            user_skill = await get_user_skill(target_id)

            target_name = await get_user_or_group_name(target_id)

            if not user_job or not user_job[0]:
                # Безработный, но с навыком
                await message.reply(
                    f"📊 Статистика {await get_user_or_group_mention(target_id)}\n\n"
                    f"💼 Статус: Безработный\n"
                    f"📊 Накопленный навык: {user_skill}\n\n"
                    f"💼 Чтобы устроиться на работу: /job",
                    disable_mentions=1
                )
                return True

            job_data = JOBS_DATA[user_job[0]]
            current_skill = user_job[1]

            # Проверяем время до следующей зарплаты
            can_work_result, hours_left, minutes_left = await check_work(target_id)

            if can_work_result:
                cooldown_status = "✅ Можно получить зарплату сейчас!"
            else:
                cooldown_status = f"⏳ До зарплаты: {hours_left} ч {minutes_left} мин"

            stats_text = (
                f"📊 Статистика работы {await get_user_or_group_mention(target_id)}\n\n"
                f"💼 Работа: {job_data['name']}\n"
                f"📝 {job_data['description']}\n\n"
                f"📊 Навык: {current_skill}\n"
                f"🎯 Требуется для этой работы: {job_data['min_skill']}\n"
                f"💰 Зарплата: {job_data['salary']:,}₽\n"
                f"📈 Навык за работу: +{job_data['skill_gain']}\n"
                f"🕐 {cooldown_status}\n\n"
            )

            # Добавляем информацию о следующей доступной работе
            next_jobs = []
            for jid, jdata in JOBS_DATA.items():
                if jid > user_job[0] and current_skill >= jdata["min_skill"]:
                    next_jobs.append(f"  {jid}. {jdata['name']} - {jdata['salary']:,}₽")

            if next_jobs:
                stats_text += "📋 Доступные для повышения работы:\n" + "\n".join(next_jobs[:3])
                if len(next_jobs) > 3:
                    stats_text += f"\n  ...и ещё {len(next_jobs) - 3}"
            else:
                # Показываем, сколько нужно до следующей работы
                next_level = None
                for jid, jdata in JOBS_DATA.items():
                    if jid > user_job[0] and (not next_level or jdata["min_skill"] < next_level["min_skill"]):
                        next_level = jdata
                if next_level:
                    skill_needed = next_level["min_skill"] - current_skill
                    stats_text += f"🎯 До следующей работы ({next_level['name']}) нужно: {skill_needed} навыка"

            await message.reply(stats_text, disable_mentions=1)
            return True

# ================== ОСТАЛЬНЫЕ ФУНКЦИИ БОТА ==================
# (здесь остаются все ваши существующие функции: getID, get_user_name, database, sql и т.д.)

# ================== КОМАНДЫ МАФИИ В ЧАТЕ ==================
# Добавьте эти команды в функцию on_chat_message

# ================== ЗАПУСК ФОНОВЫХ ЗАДАЧ ==================
async def start_mafia_cleanup():
    asyncio.create_task(cleanup_inactive_mafia_games())
    print("✅ Система автоочистки игр в мафию запущена")

# В конце файла, перед bot.run_forever():
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
loop.create_task(start_mafia_cleanup())

if __name__ == "__main__":
    print("🚀 Бот запускается...")
    bot.run_forever()