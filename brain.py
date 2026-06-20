import math
import heapq
from config import FLAG_Z, GOLD_Z, ARENA_X, ARENA_Z

JAIL_LEFT = ((-18, -14), (26, 30))
JAIL_RIGHT = ((14, 18), (26, 30))

COW_REPEL_R = 1.0
BUG_REPEL_R = 2.5
REPEL_K = 8.0
REPEL_STRENGTH = 5.0
GHOST_RANGE = 5.0
ATTACK_RANGE = 3.0
CHASE_LOCK_R = 2.0

DIRS = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]


class Brain:
    def __init__(self, bot, team=None, map_fixed=None, enemy_names=None,
                 my_name="bot", role="default", coord=None, teammate_names=None):
        self.b = bot
        self.my_side = team or 'left'
        self.map_fixed = map_fixed if map_fixed is not None else True
        self.enemy_names = enemy_names or set()
        self.my_name = my_name
        self.coord = coord
        self.teammate_names = teammate_names or set()
        self.enemy_flag_x = 22 if self.my_side == 'left' else -22
        self.my_gold_x = -22 if self.my_side == 'left' else 22
        self.enemy_flags = [(self.enemy_flag_x, z) for z in FLAG_Z]
        self.my_golds = [(self.my_gold_x, z) for z in GOLD_Z]
        self.G = 0
        self.initialized = False
        self.tick_count = 0
        self.prev_hasFlag = False
        self.atk_idx = 0
        self.hunt_slot = 0
        self.path = None
        self.path_idx = 0
        self.last_recompute = 0
        self._pe = {}

    def detect_ground_y(self):
        px, py, pz = self.b.location
        x, z = int(math.floor(px)), int(math.floor(pz))
        for yy in range(int(math.floor(py)) + 1, int(math.floor(py)) - 4, -1):
            blk = self.b.get_block(x, yy, z)
            if blk and not blk.passable:
                return yy
        return int(math.floor(py)) - 1

    def on_my_half(self, x):
        return (x < 0) == (self.my_side == 'left')

    def in_jail(self, px, pz):
        xr, zr = JAIL_LEFT if self.my_side == 'left' else JAIL_RIGHT
        return xr[0] <= px <= xr[1] and zr[0] <= pz <= zr[1]

    def is_enemy(self, e):
        if 'player' not in e.type.lower():
            return False
        nm = e.name or ""
        return nm != self.my_name and nm not in self.teammate_names and nm in self.enemy_names

    def is_infected(self, e):
        return e.helmet is not None and 'leather_helmet' in e.helmet.lower()

    def is_cow(self, e):
        t = e.type.lower()
        return 'mooshroom' in t or 'cow' in t

    def is_bug(self, e):
        return 'silverfish' in e.type.lower()

    def is_mob(self, e):
        return self.is_cow(e) or self.is_bug(e)

    def is_solid(self, x, y, z):
        blk = self.b.get_block(x, y, z)
        return blk is not None and 'fence_gate' not in blk.type.lower() and not blk.passable

    def is_obstacle(self, x, z):
        return any(self.is_solid(x, self.G + y, z) for y in range(3))

    def get_obstacles(self):
        cells = set()
        for e in self.b.entities.values():
            if self.is_cow(e):
                cells.add((int(math.floor(e.x)), int(math.floor(e.z))))
            elif self.is_bug(e) or (self.is_infected(e) and 'player' in e.type.lower()):
                cx, cz = int(math.floor(e.x)), int(math.floor(e.z))
                for dx in range(-2, 3):
                    for dz in range(-2, 3):
                        if dx * dx + dz * dz <= 5.06:
                            cells.add((cx + dx, cz + dz))
        px, py, pz = self.b.location
        rx, rz = int(math.floor(px)), int(math.floor(pz))
        R = 20
        for x in range(max(-ARENA_X, rx - R), min(ARENA_X + 1, rx + R + 1)):
            for z in range(max(-ARENA_Z, rz - R), min(ARENA_Z + 1, rz + R + 1)):
                if (x, z) not in cells and self.is_obstacle(x, z):
                    cells.add((x, z))
        return cells

    def bfs(self, start, targets):
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
                if dx != 0 and dz != 0:
                    if (cx + dx, cz) in obstacles and (cx, cz + dz) in obstacles:
                        continue
                nc = cost + dc
                if nc < g.get((nx, nz), 1e18):
                    g[(nx, nz)] = nc
                    came[(nx, nz)] = cell
                    heapq.heappush(heap, (nc, (nx, nz)))
        return None

    def flag_ok(self, p):
        g0 = self.b.get_block(p[0], self.G, p[1])
        f2 = self.b.get_block(p[0], self.G + 2, p[1])
        return g0 is None or f2 is None or ('copper' in g0.type.lower() and 'banner' in f2.type.lower())

    def gold_ok(self, p):
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

    def nearest_invader(self):
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
        if hasFlag:
            gs = self.all_golds()
            if gs:
                b = min(gs, key=lambda g: (g[0]-px)**2 + (g[1]-pz)**2)
                if not self.coord or self.coord.claim(b, self.my_name, True):
                    return b
            return (self.my_gold_x, 0)
        inv = self.nearest_invader()
        if inv and math.hypot(inv.x - px, inv.z - pz) < 10:
            return (inv.x, inv.z)
        fs = self.all_flags()
        if fs:
            dk = lambda f: (f[0]-px)**2 + (f[1]-pz)**2
            mh = sorted([f for f in fs if self.on_my_half(f[0])], key=dk)
            ot = sorted([f for f in fs if not self.on_my_half(f[0])], key=dk)
            for f in mh + ot:
                if not self.coord or self.coord.claim(f, self.my_name, False):
                    return f
        return (self.enemy_flag_x, 0)

    def around(self, pos, inc):
        s = set()
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if not inc and dx == 0 and dz == 0:
                    continue
                s.add((pos[0] + dx, pos[1] + dz))
        return s

    def repulse(self, px, pz):
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
                mag = REPEL_STRENGTH * math.exp(-d * REPEL_K)
                rx += (px - e.x) / d * mag
                rz += (pz - e.z) / d * mag
                inf = True
        return rx, rz, inf

    def n_enemy_dist(self, px, pz):
        b = 1e18
        for e in self.b.entities.values():
            if self.is_enemy(e) and not self.is_infected(e):
                d = math.hypot(e.x - px, e.z - pz)
                if d < b:
                    b = d
        return b

    def atk_target(self, px, pz):
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

    def hunt(self, px, pz, inv):
        eid = inv.id
        ex, ez = inv.x, inv.z
        d = math.hypot(ex - px, ez - pz)
        if d <= CHASE_LOCK_R:
            return 'lock', ex, ez

        slot = self.hunt_slot % 3
        self.hunt_slot += 1

        pex, pez = self._pe.get(eid, (ex, ez))
        evx = ex - pex
        evz = ez - pez
        self._pe[eid] = (ex, ez)

        vm = math.hypot(evx, evz)
        if vm > 0.01:
            ndx, ndz = evx / vm, evz / vm
        else:
            ndx, ndz = (px - ex) / max(d, 0.01), (pz - ez) / max(d, 0.01)

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
        tg = self.around((int(math.floor(tx)), int(math.floor(tz))), inc)
        st = (int(math.floor(px)), int(math.floor(pz)))
        if self.path is None or self.path_idx >= len(self.path) or self.tick_count - self.last_recompute > 10:
            self.path = self.bfs(st, tg)
            self.path_idx = 0
            if self.path and self.path[0] == st:
                self.path_idx = 1
            self.last_recompute = self.tick_count
        dx, dz = tx - px, tz - pz
        if self.path and self.path_idx < len(self.path):
            while self.path_idx < len(self.path):
                wx, wz = self.path[self.path_idx]
                if (wx + 0.5 - px)**2 + (wz + 0.5 - pz)**2 < 1.8**2:
                    self.path_idx += 1
                else:
                    break
            if self.path_idx < len(self.path):
                wx, wz = self.path[self.path_idx]
                dx, dz = (wx + 0.5) - px, (wz + 0.5) - pz
        return dx, dz

    def tick(self):
        if not self.initialized:
            if self.b.location == (0.0, 0.0, 0.0):
                return
            self.G = self.detect_ground_y()
            if abs(self.b.location[0]) > 1:
                self.my_side = 'left' if self.b.location[0] < 0 else 'right'
            self.initialized = True
            print(f"[{self.my_name}] G={self.G} {self.my_side}")
            return

        self.tick_count += 1
        px, py, pz = self.b.location
        hf = any('banner' in item.type.lower() for item in self.b.backpack)

        if not self.prev_hasFlag and hf:
            print(f"[{self.my_name}] PICKUP")
            if self.coord:
                self.coord.release_flag(self.my_name)
        if self.prev_hasFlag and not hf:
            print(f"[{self.my_name}] SUBMIT")
            if self.coord:
                self.coord.release_gold(self.my_name)
        self.prev_hasFlag = hf

        jl = self.in_jail(int(math.floor(px)), int(math.floor(pz)))
        inv = self.nearest_invader() if not hf else None
        hr = None
        if inv and not jl and math.hypot(inv.x - px, inv.z - pz) < 12:
            hr = self.hunt(px, pz, inv)

        if hr and hr[0] == 'lock':
            dx = hr[1] - px
            dz = hr[2] - pz
            tx, tz = hr[1], hr[2]
        elif hr and hr[0] == 'bfs':
            tx, tz = hr[1], hr[2]
            dx, dz = self.do_bfs(px, pz, tx, tz, False)
        else:
            tx, tz = self.pick_target(px, pz, hf)
            dx, dz = self.do_bfs(px, pz, tx, tz, hf)

        rx, rz, rp = self.repulse(px, pz)
        fx = dx + rx
        fz = dz + rz
        fl = math.hypot(fx, fz)

        if fl > 0.01:
            yw = math.degrees(math.atan2(-fx, fz)) % 360.0
            sp = not jl and self.b.hunger > 6
            jp = False
            nx, nz = fx / fl, fz / fl
            cx, cz = int(math.floor(px + nx)), int(math.floor(pz + nz))
            for yy in range(self.G + 2, self.G - 3, -1):
                blk = self.b.get_block(cx, yy, cz)
                if blk and not blk.passable:
                    if yy > self.G:
                        jp = True
                    break
            if rp and sp:
                jp = True
            nd = self.n_enemy_dist(px, pz)
            if nd < GHOST_RANGE:
                yw = (yw + math.sin(self.tick_count * 3.5) * 6.0) % 360.0
                sf = 'a' if self.tick_count % 6 < 3 else 'd'
            else:
                sf = None
        else:
            yw = math.degrees(math.atan2(-dx, -dz if dz != 0 else -0.01)) % 360.0 if abs(dx) + abs(dz) > 0.01 else 0.0
            sp = False
            jp = False
            sf = None

        atk = self.atk_target(px, pz)
        self.b.set(yaw=yw, pitch=0.0, a=(sf == 'a'), d=(sf == 'd'),
                   sprint=sp, jump=jp, attack=atk)

        if self.tick_count % 100 == 0:
            ht = hr[0] if hr else '-'
            print(f"[{self.my_name}] #{self.tick_count} ({px:.1f},{pz:.1f}) f={hf} t=({tx:.0f},{tz:.0f}) "
                  f"jl={jl} rp={rp} ht={ht}")
