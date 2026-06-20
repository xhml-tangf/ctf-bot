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

        if self.my_side == 'left':
            self.enemy_flag_x = 22
            self.my_gold_x = -22
        else:
            self.enemy_flag_x = -22
            self.my_gold_x = 22
        self.enemy_flags = [(self.enemy_flag_x, z) for z in FLAG_Z]
        self.my_golds = [(self.my_gold_x, z) for z in GOLD_Z]

        self.G = 0
        self.initialized = False
        self.tick_count = 0
        self.prev_hasFlag = False
        self.atk_idx = 0
        self.path = None
        self.path_idx = 0
        self.last_recompute = 0
        self._prev_ex = {}
        self._prev_ez = {}

    def detect_ground_y(self):
        px, py, pz = self.b.location
        x = int(math.floor(px))
        z = int(math.floor(pz))
        feet = int(math.floor(py))
        for yy in range(feet + 1, feet - 4, -1):
            blk = self.b.get_block(x, yy, z)
            if blk and not blk.passable:
                return yy
        return feet - 1

    def on_my_half(self, x):
        return (x < 0) == (self.my_side == 'left')

    def in_jail(self, px, pz):
        xr, zr = JAIL_LEFT if self.my_side == 'left' else JAIL_RIGHT
        return xr[0] <= px <= xr[1] and zr[0] <= pz <= zr[1]

    def is_enemy_player(self, e):
        if 'player' not in e.type.lower():
            return False
        nm = e.name or ""
        if nm == self.my_name or nm in self.teammate_names:
            return False
        if self.enemy_names:
            return nm in self.enemy_names
        return True

    def is_infected(self, e):
        return e.helmet is not None and 'leather_helmet' in e.helmet.lower()

    def is_cow(self, e):
        t = e.type.lower()
        return 'mooshroom' in t or 'cow' in t

    def is_bug(self, e):
        return 'silverfish' in e.type.lower()

    def is_mob(self, e):
        return self.is_cow(e) or self.is_bug(e)

    def threat_type(self, e):
        if self.is_cow(e):
            return 'cow'
        if self.is_bug(e) or (self.is_infected(e) and 'player' in e.type.lower()):
            return 'bug'
        return None

    def is_solid_at(self, x, y, z):
        blk = self.b.get_block(x, y, z)
        if blk is None:
            return False
        bt = blk.type.lower()
        if 'fence_gate' in bt:
            return False
        return not blk.passable

    def is_obstacle_cell(self, x, z):
        for yy in (self.G, self.G + 1, self.G + 2):
            if self.is_solid_at(x, yy, z):
                return True
        return False

    def get_obstacle_cells(self):
        cells = set()
        for e in self.b.entities.values():
            if self.is_cow(e):
                cells.add((int(math.floor(e.x)), int(math.floor(e.z))))
            elif self.is_bug(e) or (self.is_infected(e) and 'player' in e.type.lower()):
                cx = int(math.floor(e.x))
                cz = int(math.floor(e.z))
                for dx in range(-2, 3):
                    for dz in range(-2, 3):
                        if dx * dx + dz * dz <= 2.25 * 2.25:
                            cells.add((cx + dx, cz + dz))
        px, py, pz = self.b.location
        rx = int(math.floor(px)) + 20
        rz = int(math.floor(pz)) + 40
        for x in range(max(-ARENA_X, rx - 20), min(ARENA_X + 1, rx + 21)):
            for z in range(max(-ARENA_Z, rz - 20), min(ARENA_Z + 1, rz + 21)):
                if (x, z) not in cells and self.is_obstacle_cell(x, z):
                    cells.add((x, z))
        return cells

    def bfs(self, start, targets):
        obstacles = self.get_obstacle_cells()
        if start in targets:
            return [start]
        heap = [(0.0, start)]
        came = {start: None}
        g = {start: 0.0}
        best = None
        while heap:
            cost, cell = heapq.heappop(heap)
            if cell in targets:
                best = cell
                break
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
        if best is None:
            return None
        path = []
        c = best
        while c is not None:
            path.append(c)
            c = came[c]
        path.reverse()
        return path

    def flag_available(self, pos):
        g0 = self.b.get_block(pos[0], self.G, pos[1])
        f2 = self.b.get_block(pos[0], self.G + 2, pos[1])
        if g0 is None or f2 is None:
            return True
        return 'copper' in g0.type.lower() and 'banner' in f2.type.lower()

    def gold_empty(self, pos):
        g0 = self.b.get_block(pos[0], self.G, pos[1])
        if g0 is None:
            return True
        if 'gold' not in g0.type.lower():
            return False
        a1 = self.b.get_block(pos[0], self.G + 1, pos[1])
        a2 = self.b.get_block(pos[0], self.G + 2, pos[1])
        if a1 is None or a2 is None:
            return True
        if 'banner' in a1.type.lower() or 'banner' in a2.type.lower():
            return False
        return a1.passable and a2.passable

    def scan_flags(self):
        result = set()
        enemy_banner = 'blue_banner' if self.my_side == 'left' else 'red_banner'
        cy = self.G >> 4
        for (cx, kcy, cz), chunk in self.b.chunks.items():
            if kcy != cy:
                continue
            for lx in range(16):
                for lz in range(16):
                    wx = (cx << 4) + lx
                    wz = (cz << 4) + lz
                    if wx < -ARENA_X or wx > ARENA_X or wz < -ARENA_Z or wz > ARENA_Z:
                        continue
                    fblk = chunk.get_block(wx, self.G + 2, wz)
                    if fblk and enemy_banner in fblk.type.lower():
                        cblk = chunk.get_block(wx, self.G, wz)
                        if cblk and 'copper' in cblk.type.lower():
                            result.add((wx, wz))
        return result

    def scan_gold(self):
        result = set()
        cy = self.G >> 4
        for (cx, kcy, cz), chunk in self.b.chunks.items():
            if kcy != cy:
                continue
            for lx in range(16):
                for lz in range(16):
                    wx = (cx << 4) + lx
                    wz = (cz << 4) + lz
                    if wx < -ARENA_X or wx > ARENA_X or wz < -ARENA_Z or wz > ARENA_Z:
                        continue
                    gblk = chunk.get_block(wx, self.G, wz)
                    if gblk and 'gold' in gblk.type.lower():
                        a1 = chunk.get_block(wx, self.G + 1, wz)
                        a2 = chunk.get_block(wx, self.G + 2, wz)
                        if a1 and a2 and a1.passable and a2.passable:
                            if 'banner' not in a1.type.lower() and 'banner' not in a2.type.lower():
                                result.add((wx, wz))
        return result

    def available_flags(self):
        result = set()
        if self.map_fixed:
            for pos in self.enemy_flags:
                if self.flag_available(pos):
                    result.add(pos)
        result |= self.scan_flags()
        if self.coord:
            result = {f for f in result if self.coord.flags.get(f) in (None, self.my_name)}
        return result

    def empty_gold(self):
        if self.map_fixed:
            result = {pos for pos in self.my_golds if self.gold_empty(pos)}
            if self.coord:
                result = {g for g in result if self.coord.gold.get(g) in (None, self.my_name)}
            return result
        result = self.scan_gold()
        my_half = self.my_side == 'left'
        result = {g for g in result if (g[0] < 0) == my_half}
        if self.coord:
            result = {g for g in result if self.coord.gold.get(g) in (None, self.my_name)}
        return result

    def nearest_enemy_in_my_half(self):
        px, py, pz = self.b.location
        best = None
        nd = 1e18
        for e in self.b.entities.values():
            if not self.is_enemy_player(e) or self.is_infected(e):
                continue
            if not self.on_my_half(e.x):
                continue
            d = math.hypot(e.x - px, e.z - pz)
            if d < nd:
                nd = d
                best = e
        return best

    def pick_target(self, px, pz, hasFlag):
        if hasFlag:
            golds = self.empty_gold()
            if golds:
                best = min(golds, key=lambda g: (g[0]-px)**2 + (g[1]-pz)**2)
                if not self.coord or self.coord.claim(best, self.my_name, True):
                    return best
            return (self.my_gold_x, 0)
        invader = self.nearest_enemy_in_my_half()
        if invader and math.hypot(invader.x - px, invader.z - pz) < 10:
            return (invader.x, invader.z)
        flags = self.available_flags()
        if flags:
            dk = lambda f: (f[0]-px)**2 + (f[1]-pz)**2
            mh = sorted([f for f in flags if self.on_my_half(f[0])], key=dk)
            ot = sorted([f for f in flags if not self.on_my_half(f[0])], key=dk)
            for f in mh + ot:
                if not self.coord or self.coord.claim(f, self.my_name, False):
                    return f
        return (self.enemy_flag_x, 0)

    def targets_around(self, pos, include_center):
        cells = set()
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if not include_center and dx == 0 and dz == 0:
                    continue
                cells.add((pos[0] + dx, pos[1] + dz))
        return cells

    def compute_repulsion(self, px, pz):
        rx = rz = 0.0
        in_field = False
        for e in self.b.entities.values():
            tt = self.threat_type(e)
            if tt is None:
                continue
            d = math.hypot(px - e.x, pz - e.z)
            R = COW_REPEL_R if tt == 'cow' else BUG_REPEL_R
            if 0.01 < d < R:
                mag = REPEL_STRENGTH * math.exp(-d * REPEL_K)
                rx += (px - e.x) / d * mag
                rz += (pz - e.z) / d * mag
                in_field = True
        return rx, rz, in_field

    def nearest_enemy_dist(self, px, pz):
        best = 1e18
        for e in self.b.entities.values():
            if not self.is_enemy_player(e) or self.is_infected(e):
                continue
            d = math.hypot(e.x - px, e.z - pz)
            if d < best:
                best = d
        return best

    def nearest_attack_target(self, px, pz):
        best = None
        nd = 1e18
        for e in self.b.entities.values():
            if (self.is_enemy_player(e) and not self.is_infected(e)) or self.is_mob(e):
                d = math.hypot(e.x - px, e.z - pz)
                if d < ATTACK_RANGE and d < nd:
                    nd = d
                    best = e
        if best:
            return best.id
        mobs = [e.id for e in self.b.entities.values() if self.is_mob(e)]
        if mobs:
            t = mobs[self.atk_idx % len(mobs)]
            self.atk_idx += 1
            return t
        return None

    def _hunt(self, px, pz, invader):
        eid = invader.id
        ex, ez = invader.x, invader.z
        d = math.hypot(ex - px, ez - pz)
        if d <= CHASE_LOCK_R:
            return ('lock', ex, ez)

        slot = 0
        if self.coord:
            slot = self.coord.register_hunter(eid, self.my_name)

        pev = self._prev_ex.get(eid, ex)
        pez = self._prev_ez.get(eid, ez)
        evx = ex - pev
        evz = ez - pez
        self._prev_ex[eid] = ex
        self._prev_ez[eid] = ez

        vmag = math.hypot(evx, evz)
        if vmag > 0.01:
            ndx, ndz = evx / vmag, evz / vmag
        else:
            ndx, ndz = (px - ex) / max(d, 0.01), (pz - ez) / max(d, 0.01)

        ecx, ecz = int(math.floor(ex)), int(math.floor(ez))
        if slot == 0:
            tx = int(math.floor(ex + ndx))
            tz = int(math.floor(ez + ndz))
        elif slot == 1:
            tx = int(math.floor(ex - ndx))
            tz = int(math.floor(ez - ndz))
        else:
            tx, tz = ecx, ecz
        tx = max(-ARENA_X, min(ARENA_X, tx))
        tz = max(-ARENA_Z, min(ARENA_Z, tz))
        return ('bfs', tx, tz)

    def _do_bfs(self, px, pz, tx, tz, include_center):
        target_cells = self.targets_around((int(math.floor(tx)), int(math.floor(tz))), include_center)
        start = (int(math.floor(px)), int(math.floor(pz)))
        now = self.tick_count
        if self.path is None or self.path_idx >= len(self.path) or now - self.last_recompute > 10:
            self.path = self.bfs(start, target_cells)
            self.path_idx = 0
            if self.path and self.path[0] == start:
                self.path_idx = 1
            self.last_recompute = now
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
                dx = (wx + 0.5) - px
                dz = (wz + 0.5) - pz
        return dx, dz

    def tick(self):
        if not self.initialized:
            if self.b.location == (0.0, 0.0, 0.0):
                return
            self.G = self.detect_ground_y()
            if abs(self.b.location[0]) > 1:
                self.my_side = 'left' if self.b.location[0] < 0 else 'right'
            self.initialized = True
            print(f"[{self.my_name}] init G={self.G} side={self.my_side}")
            return

        self.tick_count += 1
        px, py, pz = self.b.location
        hasFlag = any('banner' in item.type.lower() for item in self.b.backpack)

        if not self.prev_hasFlag and hasFlag:
            print(f"[{self.my_name}] PICKUP")
            if self.coord:
                self.coord.release_flag(self.my_name)
        if self.prev_hasFlag and not hasFlag:
            print(f"[{self.my_name}] SUBMIT")
            if self.coord:
                self.coord.release_gold(self.my_name)
        self.prev_hasFlag = hasFlag

        in_jail = self.in_jail(int(math.floor(px)), int(math.floor(pz)))
        invader = self.nearest_enemy_in_my_half() if not hasFlag else None
        hunt_result = None
        if invader and not in_jail and math.hypot(invader.x - px, invader.z - pz) < 12:
            hunt_result = self._hunt(px, pz, invader)

        if hunt_result and hunt_result[0] == 'lock':
            dx = hunt_result[1] - px
            dz = hunt_result[2] - pz
            tx, tz = hunt_result[1], hunt_result[2]
        elif hunt_result and hunt_result[0] == 'bfs':
            tx, tz = hunt_result[1], hunt_result[2]
            dx, dz = self._do_bfs(px, pz, tx, tz, False)
        else:
            tx, tz = self.pick_target(px, pz, hasFlag)
            dx, dz = self._do_bfs(px, pz, tx, tz, hasFlag)

        rep_x, rep_z, in_repulsion = self.compute_repulsion(px, pz)
        final_x = dx + rep_x
        final_z = dz + rep_z
        flen = math.hypot(final_x, final_z)

        if flen > 0.01:
            yaw = math.degrees(math.atan2(-final_x, final_z)) % 360.0
            w = True
            sprint = not in_jail and self.b.hunger > 6
            jump = False
            ndx, ndz = final_x / flen, final_z / flen
            ncell_x = int(math.floor(px + ndx))
            ncell_z = int(math.floor(pz + ndz))
            for yy in range(self.G + 2, self.G - 3, -1):
                blk = self.b.get_block(ncell_x, yy, ncell_z)
                if blk and not blk.passable:
                    if yy > self.G:
                        jump = True
                    break
            if in_repulsion and sprint:
                jump = True
            n_dist = self.nearest_enemy_dist(px, pz)
            if n_dist < GHOST_RANGE:
                yaw = (yaw + math.sin(self.tick_count * 3.5) * 6.0) % 360.0
                strafe = 'a' if self.tick_count % 6 < 3 else 'd'
            else:
                strafe = None
        else:
            yaw = math.degrees(math.atan2(-dx, dz)) % 360.0 if abs(dx) + abs(dz) > 0.01 else 0.0
            w = False
            sprint = False
            jump = False
            strafe = None

        attack = self.nearest_attack_target(px, pz)
        self.b.set(yaw=yaw, pitch=0.0, w=w, a=(strafe == 'a'), d=(strafe == 'd'),
                   sprint=sprint, jump=jump, attack=attack)

        if self.tick_count % 100 == 0:
            ht = hunt_result[0] if hunt_result else 'none'
            print(f"[{self.my_name}] #{self.tick_count} ({px:.1f},{pz:.1f}) flag={hasFlag} "
                  f"target=({tx:.0f},{tz:.0f}) jail={in_jail} rep={in_repulsion} hunt={ht}")
