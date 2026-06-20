import os

server_url = os.environ.get("CTF_SERVER", "ws://10.31.0.101:8080")
player_names_str = os.environ.get("CTF_PLAYERS", "tang_fuqing,wang_simu,ling_jiayou")
player_names = [n.strip() for n in player_names_str.split(",") if n.strip()]
enemy_name = os.environ.get("CTF_ENEMY", "none")
map_name = os.environ.get("CTF_MAP", "fixed")
players = len(player_names)
player_name = player_names[0] if player_names else "tang_fuqing"

FLAG_Z = [-34, -30, -26, -22, -18, -14, -10, -6]
GOLD_Z = [6, 10, 14, 18, 22, 26, 30, 34]

DIRS = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]

ARENA_X = 24
ARENA_Z = 36
TICK_DT = 0.05
