import time
import json
import threading
import traceback
from config import server_url, player_names, enemy_name, map_name, TICK_DT
from bot import Bot
from brain import Brain
from team import TeamCoord

team_state = {'myTeam': None, 'enemy_names': set(), 'started': False, 'coord': TeamCoord()}
team_lock = threading.Lock()
ROLES = ['steal', 'steal', 'chase']
bots_info = []


def make_listener(bot: Bot, name: str):
    def listener(msg: str):
        print(f'[{name}] {msg}')
        if 'Are you ready?' in msg:
            bot.chat("I'm ready!")
        if 'Game start: ' in msg:
            with team_lock:
                if team_state['started']:
                    return
                team_state['started'] = True
                pd = json.loads(msg.split('Game start: ')[1])
                left = pd.get('left', [])
                right = pd.get('right', [])
                if name in left:
                    team_state['myTeam'] = 'left'
                    team_state['enemy_names'] = set(right)
                else:
                    team_state['myTeam'] = 'right'
                    team_state['enemy_names'] = set(left)
            print(f"[team] myTeam={team_state['myTeam']} enemies={team_state['enemy_names']}")
            for (b, n, r) in bots_info:
                threading.Thread(target=run_bot, args=(b, n, r), daemon=True).start()
        if 'Game over' in msg:
            print(f"[{name}] game over")
            for (b, n, r) in bots_info:
                try:
                    b.disconnect()
                except Exception:
                    pass
    return listener


def run_bot(bot: Bot, name: str, role: str):
    time.sleep(0.8)
    brain = Brain(bot, team_state['myTeam'] or 'left', map_name == 'fixed',
                  team_state['enemy_names'], name, role, team_state['coord'], set(player_names))
    while bot.connected():
        try:
            brain.tick()
        except Exception as e:
            print(f"[{name}] tick error:", e)
            traceback.print_exc()
        time.sleep(TICK_DT)


if __name__ == "__main__":
    for i, nm in enumerate(player_names):
        bot = Bot(nm, server_url)
        if bot.connect():
            bots_info.append((bot, nm, ROLES[i % len(ROLES)]))
        time.sleep(1.0)
    if not bots_info:
        print("[main] no bot connected, exit")
        raise SystemExit
    for (bot, nm, role) in bots_info:
        bot.on_msg(make_listener(bot, nm))
    for (bot, nm, role) in bots_info:
        bot.chat(f'match enemy:{enemy_name} map:{map_name} players:{len(player_names)}')
        time.sleep(0.3)
    try:
        while any(b.connected() for (b, n, r) in bots_info):
            time.sleep(1.0)
    except KeyboardInterrupt:
        for (b, n, r) in bots_info:
            try:
                b.disconnect()
            except Exception:
                pass
