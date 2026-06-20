# brain.py — 核心决策层：目标选择 + BFS寻路 + 流场斥力 + 鬼步抖动 + 追击包围
import math
import heapq
from config import FLAG_Z, GOLD_Z, ARENA_X, ARENA_Z

# 监狱坐标范围 (左队 / 右队)
JAIL_LEFT = ((-18, -14), (26, 30))
JAIL_RIGHT = ((14, 18), (26, 30))

# 斥力场参数: 牛(哞菇)半径1.0, 虫/感染者半径2.5, 衰减系数k=8(极陡), 强度5.0
COW_REPEL_R = 1.0
BUG_REPEL_R = 2.5
REPEL_K = 8.0
REPEL_STRENGTH = 5.0

# 鬼步: 敌人<5格时激活 yaw抖动±6°+周期a/d平移
GHOST_RANGE = 5.0
# 攻击范围3格, 追击锁死半径2格(进入后直接冲刺贴脸)
ATTACK_RANGE = 3.0
CHASE_LOCK_R = 2.0

# 八方向偏移及代价(正交1.0, 对角1.414)
DIRS = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]


class Brain:
    """每tick由main.py调用的核心AI类。三层: 选目标→BFS寻路→流场+鬼步→输出input。"""
    def __init__(self, bot, team=None, map_fixed=None, enemy_names=None,
                 my_name="bot", role="default", coord=None, teammate_names=None):
        self.b = bot                             # Bot实例(通信框架)
        self.my_side = team or 'left'           # 队伍: left(红) / right(蓝)
        self.map_fixed = map_fixed if map_fixed is not None else True
        self.enemy_names = enemy_names or set()  # 敌方花名册
        self.my_name = my_name                   # 本bot名字
        self.coord = coord                       # TeamCoord(旗/金认领)
        self.teammate_names = teammate_names or set()
        # 敌方旗x=±22, 我方金块x=∓22
        self.enemy_flag_x = 22 if self.my_side == 'left' else -22
        self.my_gold_x = -22 if self.my_side == 'left' else 22
        # 固定地图默认旗/金位置(8对, z轴对称)
        self.enemy_flags = [(self.enemy_flag_x, z) for z in FLAG_Z]
        self.my_golds = [(self.my_gold_x, z) for z in GOLD_Z]
        # 运行时状态
        self.G = 0                               # 地面层y坐标
        self.initialized = False                 # 首帧初始化标志
        self.tick_count = 0                      # 总tick计数
        self.prev_hasFlag = False                # 上一帧持旗状态(检测拾取/上交)
        self.atk_idx = 0                         # 攻击轮询索引
        self.hunt_slot = 0                       # 追击包围槽位(0前1后2同)
        # BFS寻路缓存
        self.path = None                         # 当前路径点列表
        self.path_idx = 0                        # 已到达的路径点索引
        self.last_recompute = 0                  # 上次重算的tick
        self._pe = {}                            # 敌人上帧位置(eid→(x,z)), 用于速度估算

    # ── 地形 ──
    def detect_ground_y(self):
        """从脚底向下扫描第一个实心方块, 返回其y坐标(地面层)"""
        px, py, pz = self.b.location
        x, z = int(math.floor(px)), int(math.floor(pz))
        for yy in range(int(math.floor(py)) + 1, int(math.floor(py)) - 4, -1):
            blk = self.b.get_block(x, yy, z)
            if blk and not blk.passable:
                return yy
        return int(math.floor(py)) - 1

    def on_my_half(self, x):
        """判断x坐标是否在己方半场(左x<0,右x>0)"""
        return (x < 0) == (self.my_side == 'left')

    def in_jail(self, px, pz):
        """判断是否在监狱区域内(用于禁用冲刺)"""
        xr, zr = JAIL_LEFT if self.my_side == 'left' else JAIL_RIGHT
        return xr[0] <= px <= xr[1] and zr[0] <= pz <= zr[1]

    # ── 实体分类 ──
    def is_enemy(self, e):
        """非己方非队友的玩家→敌人"""
        if 'player' not in e.type.lower():
            return False
        nm = e.name or ""
        return nm != self.my_name and nm not in self.teammate_names and nm in self.enemy_names

    def is_infected(self, e):
        """戴皮革头盔=感染者(无法被抓/抓人, 掉旗)"""
        return e.helmet is not None and 'leather_helmet' in e.helmet.lower()

    def is_cow(self, e):
        """哞菇/牛→近场斥力(3×3区域, 半径1)"""
        t = e.type.lower()
        return 'mooshroom' in t or 'cow' in t

    def is_bug(self, e):
        """蠹虫→中等斥力(半径2.5)"""
        return 'silverfish' in e.type.lower()

    def is_mob(self, e):
        return self.is_cow(e) or self.is_bug(e)

    # ── 障碍物: G/G+1/G+2三层任一层有实心方块→该格为障碍(栅栏门除外, 始终可通行) ──
    def is_solid(self, x, y, z):
        """检测(x,y,z)是否为实心方块(排除栅栏门, 门始终可通行)"""
        blk = self.b.get_block(x, y, z)
        return blk is not None and 'fence_gate' not in blk.type.lower() and not blk.passable

    def is_obstacle(self, x, z):
        """地面格(x,z)是否为障碍: G/G+1/G+2任一层有实心方块→障碍"""
        return any(self.is_solid(x, self.G + y, z) for y in range(3))

    def get_obstacles(self):
        """收集所有障碍格: 牛所在格 + 虫/感染者半径2.25格 + 周围20格内树/墙/栅栏映射"""
        cells = set()
        # 生物障碍
        for e in self.b.entities.values():
            if self.is_cow(e):
                cells.add((int(math.floor(e.x)), int(math.floor(e.z))))
            elif self.is_bug(e) or (self.is_infected(e) and 'player' in e.type.lower()):
                cx, cz = int(math.floor(e.x)), int(math.floor(e.z))
                for dx in range(-2, 3):
                    for dz in range(-2, 3):
                        if dx * dx + dz * dz <= 5.06:   # 2.25²≈5.06
                            cells.add((cx + dx, cz + dz))
        # 地形障碍: 扫描周围20格, G/G+1/G+2实心方块映射到地面
        px, py, pz = self.b.location
        rx, rz = int(math.floor(px)), int(math.floor(pz))
        R = 20
        for x in range(max(-ARENA_X, rx - R), min(ARENA_X + 1, rx + R + 1)):
            for z in range(max(-ARENA_Z, rz - R), min(ARENA_Z + 1, rz + R + 1)):
                if (x, z) not in cells and self.is_obstacle(x, z):
                    cells.add((x, z))
        return cells

    # ── 寻路: Dijkstra(带对角线代价) ──
    def bfs(self, start, targets):
        """Dijkstra最短路。障碍=牛格+虫/感染者半径2.25格+地形实心映射。蜂蜜/水不阻。"""
        obstacles = self.get_obstacles()
        if start in targets:
            return [start]
        heap = [(0.0, start)]
        came = {start: None}
        g = {start: 0.0}
        while heap:
            cost, cell = heapq.heappop(heap)
            if cell in targets:
                path = []
                while cell is not None:
                    path.append(cell)
                    cell = came[cell]
                return path[::-1]
            if cost > g.get(cell, 1e18):
                continue
            cx, cz = cell
            for dx, dz, dc in DIRS:
                nx, nz = cx + dx, cz + dz
                if nx < -ARENA_X or nx > ARENA_X or nz < -ARENA_Z or nz > ARENA_Z:
                    continue
                if (nx, nz) in obstacles:
                    continue
                # 对角相邻需同时正交可走(防切角)
                if dx != 0 and dz != 0:
                    if (cx + dx, cz) in obstacles and (cx, cz + dz) in obstacles:
                        continue
                nc = cost + dc
                if nc < g.get((nx, nz), 1e18):
                    g[(nx, nz)] = nc
                    came[(nx, nz)] = cell
                    heapq.heappush(heap, (nc, (nx, nz)))
        return None

    # ── 旗/金扫描 ──
    def flag_ok(self, p):
        """检测旗子是否可拾取: copper底+ enemy_banner顶"""
        g0 = self.b.get_block(p[0], self.G, p[1])
        f2 = self.b.get_block(p[0], self.G + 2, p[1])
        return g0 is None or f2 is None or ('copper' in g0.type.lower() and 'banner' in f2.type.lower())

    def gold_ok(self, p):
        """检测金块是否为空(可上交): gold底 + 上方空气 + 无旗子"""
        g0 = self.b.get_block(p[0], self.G, p[1])
        if g0 is None:
            return True
        if 'gold' not in g0.type.lower():
            return False
        a1 = self.b.get_block(p[0], self.G + 1, p[1])
        a2 = self.b.get_block(p[0], self.G + 2, p[1])
        if a1 is None or a2 is None:
            return True
        if 'banner' in a1.type.lower() or 'banner' in a2.type.lower():
            return False
        return a1.passable and a2.passable

    def scan_flags(self):
        """扫描已加载区块中的敌旗(banner on copper at G+2)"""
        r = set()
        eb = 'blue_banner' if self.my_side == 'left' else 'red_banner'
        cy = self.G >> 4
        for (cx, kcy, cz), ch in self.b.chunks.items():
            if kcy != cy:
                continue
            for lx in range(16):
                for lz in range(16):
                    wx = (cx << 4) + lx
                    wz = (cz << 4) + lz
                    if wx < -ARENA_X or wx > ARENA_X or wz < -ARENA_Z or wz > ARENA_Z:
                        continue
                    fblk = ch.get_block(wx, self.G + 2, wz)
                    if fblk and eb in fblk.type.lower():
                        cblk = ch.get_block(wx, self.G, wz)
                        if cblk and 'copper' in cblk.type.lower():
                            r.add((wx, wz))
        return r

    def scan_gold(self):
        """扫描已加载区块中的空金块(gold + air + 无旗)"""
        r = set()
        cy = self.G >> 4
        for (cx, kcy, cz), ch in self.b.chunks.items():
            if kcy != cy:
                continue
            for lx in range(16):
                for lz in range(16):
                    wx = (cx << 4) + lx
                    wz = (cz << 4) + lz
                    if wx < -ARENA_X or wx > ARENA_X or wz < -ARENA_Z or wz > ARENA_Z:
                        continue
                    gblk = ch.get_block(wx, self.G, wz)
                    if gblk and 'gold' in gblk.type.lower():
                        a1 = ch.get_block(wx, self.G + 1, wz)
                        a2 = ch.get_block(wx, self.G + 2, wz)
                        if a1 and a2 and a1.passable and a2.passable:
                            if 'banner' not in a1.type.lower() and 'banner' not in a2.type.lower():
                                r.add((wx, wz))
        return r

    def all_flags(self):
        """所有可用敌旗: 固定地图预置 + 扫描发现, 排除队友认领的"""
        r = set()
        if self.map_fixed:
            for p in self.enemy_flags:
                if self.flag_ok(p):
                    r.add(p)
        r |= self.scan_flags()
        if self.coord:
            r = {f for f in r if self.coord.flags.get(f) in (None, self.my_name)}
        return r

    def all_golds(self):
        """所有空金块: 固定地图预置 + 扫描发现, 排除队友认领的; 随机地图仅己方半场"""
        if self.map_fixed:
            r = {p for p in self.my_golds if self.gold_ok(p)}
            if self.coord:
                r = {g for g in r if self.coord.gold.get(g) in (None, self.my_name)}
            return r
        r = self.scan_gold()
        mh = self.my_side == 'left'
        r = {g for g in r if (g[0] < 0) == mh}
        if self.coord:
            r = {g for g in r if self.coord.gold.get(g) in (None, self.my_name)}
        return r

    # ── 目标选择 ──
    def nearest_invader(self):
        """最近的己方半场敌人(非感染者)"""
        px, py, pz = self.b.location
        b, nd = None, 1e18
        for e in self.b.entities.values():
            if self.is_enemy(e) and not self.is_infected(e) and self.on_my_half(e.x):
                d = math.hypot(e.x - px, e.z - pz)
                if d < nd:
                    nd = d
                    b = e
        return b

    def pick_target(self, px, pz, hasFlag):
        """选目标: 持旗→最近空金块; 没旗→己方半场敌人(<10格)优先, 否则→最近敌旗(己方半场优先)"""
        if hasFlag:
            gs = self.all_golds()
            if gs:
                b = min(gs, key=lambda g: (g[0]-px)**2 + (g[1]-pz)**2)
                if not self.coord or self.coord.claim(b, self.my_name, True):
                    return b
            return (self.my_gold_x, 0)      # fallback: 己方半场中心
        inv = self.nearest_invader()
        if inv and math.hypot(inv.x - px, inv.z - pz) < 10:
            return (inv.x, inv.z)            # 优先追击入侵者
        fs = self.all_flags()
        if fs:
            dk = lambda f: (f[0]-px)**2 + (f[1]-pz)**2
            mh = sorted([f for f in fs if self.on_my_half(f[0])], key=dk)
            ot = sorted([f for f in fs if not self.on_my_half(f[0])], key=dk)
            for f in mh + ot:                # 己方半场旗优先
                if not self.coord or self.coord.claim(f, self.my_name, False):
                    return f
        return (self.enemy_flag_x, 0)        # fallback: 敌方半场中心

    def around(self, pos, inc):
        """返回目标点周围可达格(inc=True含中心, 否则8邻)"""
        s = set()
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if not inc and dx == 0 and dz == 0:
                    continue
                s.add((pos[0] + dx, pos[1] + dz))
        return s

    # ── 流场斥力: 牛/虫/感染者 极陡指数衰减 exp(-d*k) ──
    def repulse(self, px, pz):
        """计算斥力合力(牛R=1, 虫R=2.5, 衰减k=8)。返回(rx,rz,是否在斥力场内)"""
        rx = rz = 0.0
        inf = False
        for e in self.b.entities.values():
            if self.is_cow(e):
                R = COW_REPEL_R
            elif self.is_bug(e) or (self.is_infected(e) and 'player' in e.type.lower()):
                R = BUG_REPEL_R
            else:
                continue
            d = math.hypot(px - e.x, pz - e.z)
            if 0.01 < d < R:
                mag = REPEL_STRENGTH * math.exp(-d * REPEL_K)  # 极陡指数衰减
                rx += (px - e.x) / d * mag                     # 远离威胁方向
                rz += (pz - e.z) / d * mag
                inf = True
        return rx, rz, inf

    def n_enemy_dist(self, px, pz):
        """最近非感染敌人的距离(用于鬼步触发)"""
        b = 1e18
        for e in self.b.entities.values():
            if self.is_enemy(e) and not self.is_infected(e):
                d = math.hypot(e.x - px, e.z - pz)
                if d < b:
                    b = d
        return b

    # ── 攻击: 范围内敌人优先, 否则轮询生物 ──
    def atk_target(self, px, pz):
        """选择攻击目标: 攻击范围内敌人优先, 否则轮询生物(mob)"""
        b, nd = None, 1e18
        for e in self.b.entities.values():
            if (self.is_enemy(e) and not self.is_infected(e)) or self.is_mob(e):
                d = math.hypot(e.x - px, e.z - pz)
                if d < ATTACK_RANGE and d < nd:
                    nd = d
                    b = e
        if b:
            return b.id
        mobs = [e.id for e in self.b.entities.values() if self.is_mob(e)]
        if mobs:
            t = mobs[self.atk_idx % len(mobs)]
            self.atk_idx += 1
            return t
        return None

    # ── 追击: 多人包围(前/后/同格) + 锁死冲刺(<2格) ──
    def hunt(self, px, pz, inv):
        """追击入侵者: 距离≤2格→锁死冲刺; >2格→BFS到包围位(slot轮转)"""
        eid = inv.id
        ex, ez = inv.x, inv.z
        d = math.hypot(ex - px, ez - pz)
        if d <= CHASE_LOCK_R:
            return 'lock', ex, ez          # 锁死模式: 直接朝敌人冲

        slot = self.hunt_slot % 3          # 三人分三槽(0前1后2同)
        self.hunt_slot += 1

        # 估算敌人速度(位置差分)
        pex, pez = self._pe.get(eid, (ex, ez))
        evx = ex - pex
        evz = ez - pez
        self._pe[eid] = (ex, ez)

        vm = math.hypot(evx, evz)
        if vm > 0.01:
            ndx, ndz = evx / vm, evz / vm  # 敌人朝向单位向量
        else:
            ndx, ndz = (px - ex) / max(d, 0.01), (pz - ez) / max(d, 0.01)

        # 槽0→前方一格, 槽1→后方一格, 槽2→同格
        if slot == 0:
            tx, tz = int(math.floor(ex + ndx)), int(math.floor(ez + ndz))
        elif slot == 1:
            tx, tz = int(math.floor(ex - ndx)), int(math.floor(ez - ndz))
        else:
            tx, tz = int(math.floor(ex)), int(math.floor(ez))
        tx = max(-ARENA_X, min(ARENA_X, tx))
        tz = max(-ARENA_Z, min(ARENA_Z, tz))
        return 'bfs', tx, tz

    def do_bfs(self, px, pz, tx, tz, inc):
        """执行BFS寻路到目标, 并跟随路径点移动。返回下一步方向(dx,dz)。"""
        tg = self.around((int(math.floor(tx)), int(math.floor(tz))), inc)
        st = (int(math.floor(px)), int(math.floor(pz)))
        # 每10tick或路径耗完时重算
        if self.path is None or self.path_idx >= len(self.path) or self.tick_count - self.last_recompute > 10:
            self.path = self.bfs(st, tg)
            self.path_idx = 0
            if self.path and self.path[0] == st:
                self.path_idx = 1          # 跳过起点
            self.last_recompute = self.tick_count
        dx, dz = tx - px, tz - pz          # 默认直走
        if self.path and self.path_idx < len(self.path):
            # 推进路径点: 距离<1.8时到达, 移向下一个
            while self.path_idx < len(self.path):
                wx, wz = self.path[self.path_idx]
                if (wx + 0.5 - px)**2 + (wz + 0.5 - pz)**2 < 1.8**2:
                    self.path_idx += 1
                else:
                    break
            if self.path_idx < len(self.path):
                wx, wz = self.path[self.path_idx]
                dx, dz = (wx + 0.5) - px, (wz + 0.5) - pz  # 朝下一个路径点
        return dx, dz

    # ── 主循环: 每tick由main.py调用 ──
    def tick(self):
        # 首帧初始化: 检测地面层 + 判断左右队
        if not self.initialized:
            if self.b.location == (0.0, 0.0, 0.0):
                return                      # 等第一帧Status到达
            self.G = self.detect_ground_y()
            if abs(self.b.location[0]) > 1:
                self.my_side = 'left' if self.b.location[0] < 0 else 'right'
            self.initialized = True
            print(f"[{self.my_name}] G={self.G} {self.my_side}")
            return

        self.tick_count += 1
        px, py, pz = self.b.location
        hf = any('banner' in item.type.lower() for item in self.b.backpack)

        # 旗状态变化: 拾取/上交
        if not self.prev_hasFlag and hf:
            print(f"[{self.my_name}] PICKUP")
            if self.coord:
                self.coord.release_flag(self.my_name)
        if self.prev_hasFlag and not hf:
            print(f"[{self.my_name}] SUBMIT")
            if self.coord:
                self.coord.release_gold(self.my_name)
        self.prev_hasFlag = hf

        # 步骤1: 选目标(tx,tz) — 持旗→金块, 否则→入侵者/敌旗
        jl = self.in_jail(int(math.floor(px)), int(math.floor(pz)))
        inv = self.nearest_invader() if not hf else None
        hr = None
        if inv and not jl and math.hypot(inv.x - px, inv.z - pz) < 12:
            hr = self.hunt(px, pz, inv)     # 追击入侵者

        if hr and hr[0] == 'lock':
            dx = hr[1] - px                 # 锁死: 直接朝敌人冲
            dz = hr[2] - pz
            tx, tz = hr[1], hr[2]
        elif hr and hr[0] == 'bfs':
            tx, tz = hr[1], hr[2]
            dx, dz = self.do_bfs(px, pz, tx, tz, False)  # BFS包围路径
        else:
            tx, tz = self.pick_target(px, pz, hf)         # 正常目标
            dx, dz = self.do_bfs(px, pz, tx, tz, hf)

        # 步骤2: 流场斥力叠加
        rx, rz, rp = self.repulse(px, pz)
        fx = dx + rx                           # 合力 = 吸引力 + 斥力
        fz = dz + rz
        fl = math.hypot(fx, fz)

        # 步骤3: 移动执行
        if fl > 0.01:
            # yaw: MC角度, 0=+Z(南), 90=-X(西)。公式: atan2(-dx, dz)
            yw = math.degrees(math.atan2(-fx, fz)) % 360.0
            sp = not jl and self.b.hunger > 6  # 监狱内不冲刺; 冲刺需饱食度>6
            # 地形台阶: 下一格地面高于当前→跳跃
            jp = False
            nx, nz = fx / fl, fz / fl
            cx, cz = int(math.floor(px + nx)), int(math.floor(pz + nz))
            for yy in range(self.G + 2, self.G - 3, -1):
                blk = self.b.get_block(cx, yy, cz)
                if blk and not blk.passable:
                    if yy > self.G:
                        jp = True              # 台阶跳跃
                    break
            if rp and sp:
                jp = True                      # 斥力场内跑跳脱困
            # 鬼步: 敌人<5格 → yaw高频抖动+周期a/d平移
            nd = self.n_enemy_dist(px, pz)
            if nd < GHOST_RANGE:
                yw = (yw + math.sin(self.tick_count * 3.5) * 6.0) % 360.0
                sf = 'a' if self.tick_count % 6 < 3 else 'd'
            else:
                sf = None
        else:
            # 合力≈0: 原地不动, 仅调整朝向
            yw = math.degrees(math.atan2(-dx, -dz if dz != 0 else -0.01)) % 360.0 if abs(dx) + abs(dz) > 0.01 else 0.0
            sp = False
            jp = False
            sf = None

        # 步骤4: 攻击 + 执行input
        atk = self.atk_target(px, pz)
        self.b.set(yaw=yw, pitch=0.0, a=(sf == 'a'), d=(sf == 'd'),
                   sprint=sp, jump=jp, attack=atk)

        if self.tick_count % 100 == 0:
            ht = hr[0] if hr else '-'
            print(f"[{self.my_name}] #{self.tick_count} ({px:.1f},{pz:.1f}) f={hf} t=({tx:.0f},{tz:.0f}) "
                  f"jl={jl} rp={rp} ht={ht}")
