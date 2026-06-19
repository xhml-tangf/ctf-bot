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
RECOMPUTE_DT = 0.5
WAYPOINT_REACH = 1.8
STUCK_THRESH = 3
STUCK_JUMP = 5
STEER_DEAD = 0.3

MOOSHROOM_R = 3.5
SILVERFISH_R = 6.0
INFECTED_R = 6.0
ENEMY_R_DEFEND = 4.0
ENEMY_R_STEAL = 5.5
TEAMMATE_R = 3.0

BLOCK_REPEL_R = 0.85
NEAR_DOUBLED = 2.0
HONEY_COST = 2.5
THREAT_COST_K = 1.5

REPULSION_A = 7.0
REPULSION_B_FRAC = 0.4
REPULSION_CANCEL = 0.3

KITE_DIST = 2.0
CATCH_NEAR = 1.2
DEPOSIT_NEAR = 4.0
DEPOSIT_SLOW = 1.2
ATTACK_RANGE = 3.0
PATROL_RING = 3.0
