# config.py — 环境配置: WebSocket地址、玩家名、地图参数、竞技场常量
import os

# 比赛参数(可通过环境变量覆盖)
server_url = os.environ.get("CTF_SERVER", "ws://10.31.0.101:8080")  # WebSocket服务器地址
player_names_str = os.environ.get("CTF_PLAYERS", "tang_fuqing,wang_simu,ling_jiayou")
player_names = [n.strip() for n in player_names_str.split(",") if n.strip()]  # 逗号分隔的3个bot名
enemy_name = os.environ.get("CTF_ENEMY", "none")  # 对手: none/bot/trivial/组名
map_name = os.environ.get("CTF_MAP", "fixed")     # 地图: fixed/random/any
players = len(player_names)
player_name = player_names[0] if player_names else "tang_fuqing"  # 主bot名(兼容旧代码)

# 固定地图预置坐标: 旗z负半轴(-34~-6), 金块z正半轴(6~34), x=±22
FLAG_Z = [-34, -30, -26, -22, -18, -14, -10, -6]  # 敌方旗帜z坐标(8面)
GOLD_Z = [6, 10, 14, 18, 22, 26, 30, 34]         # 己方金块z坐标(8个)

# 八方向偏移及代价(正交1.0, 对角1.414), 用于寻路
DIRS = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]

# 竞技场: 49×73 (x:-24~24, z:-36~36)
ARENA_X = 24
ARENA_Z = 36
TICK_DT = 0.05  # 主循环间隔(秒), 20Hz
