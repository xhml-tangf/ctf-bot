# main.py — 多bot运行器: 创建3个WebSocket连接, 配对比赛, 启动Brain线程
import time
import json
import threading
import traceback
from config import server_url, player_names, enemy_name, map_name, TICK_DT
from bot import Bot
from brain import Brain
from team import TeamCoord

# 全局状态: 队伍信息 + 比赛开始标志 + 认领协调器
team_state = {'myTeam': None, 'enemy_names': set(), 'started': False, 'coord': TeamCoord()}
team_lock = threading.Lock()         # 保护team_state的多线程锁
ROLES = ['steal', 'steal', 'chase']  # 3个bot的角色分工(tang→偷旗, wang→偷旗, ling→追击)
bots_info = []                       # [(Bot, name, role), ...] 所有bot实例


def make_listener(bot: Bot, name: str):
    """为每个bot创建消息监听器闭包。处理: Are you ready? → Game start → Game over"""
    def listener(msg: str):
        print(f'[{name}] {msg}')
        if 'Are you ready?' in msg:
            bot.chat("I'm ready!")                      # 回复准备就绪
        if 'Game start: ' in msg:
            with team_lock:
                if team_state['started']:
                    return                              # 防止重复启动
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
            # 为每个bot启动独立的run线程
            for (b, n, r) in bots_info:
                threading.Thread(target=run_bot, args=(b, n, r), daemon=True).start()
        if 'Game over' in msg:
            print(f"[{name}] game over")
            for (b, n, r) in bots_info:                 # 断开所有bot
                try:
                    b.disconnect()
                except Exception:
                    pass
    return listener


def run_bot(bot: Bot, name: str, role: str):
    """单个bot的主循环: 创建Brain → 每tick调brain.tick()"""
    time.sleep(0.8)                                     # 等待Server稳定
    brain = Brain(bot, team_state['myTeam'] or 'left', map_name == 'fixed',
                  team_state['enemy_names'], name, role, team_state['coord'], set(player_names))
    while bot.connected():
        try:
            brain.tick()
        except Exception as e:
            print(f"[{name}] tick error:", e)
            traceback.print_exc()
        time.sleep(TICK_DT)                             # 0.05s = 20Hz


if __name__ == "__main__":
    # 步骤1: 为每个玩家创建Bot并连接(独立WebSocket, 各自登录)
    for i, nm in enumerate(player_names):
        bot = Bot(nm, server_url)
        if bot.connect():
            bots_info.append((bot, nm, ROLES[i % len(ROLES)]))
        time.sleep(1.0)                                 # 连接间隔, 避免冲击服务器
    if not bots_info:
        print("[main] no bot connected, exit")
        raise SystemExit
    # 步骤2: 注册消息监听器
    for (bot, nm, role) in bots_info:
        bot.on_msg(make_listener(bot, nm))
    # 步骤3: 每个bot从自己的WebSocket发送match命令(服务器分组配对)
    for (bot, nm, role) in bots_info:
        bot.chat(f'match enemy:{enemy_name} map:{map_name} players:{len(player_names)}')
        time.sleep(0.3)
    # 步骤4: 保持主线程存活直到所有bot断开
    try:
        while any(b.connected() for (b, n, r) in bots_info):
            time.sleep(1.0)
    except KeyboardInterrupt:
        for (b, n, r) in bots_info:
            try:
                b.disconnect()
            except Exception:
                pass
