import math
from config import FLAG_Z, GOLD_Z, ARENA_X, ARENA_Z


def sub_v(v1, v2): return (v1[0]-v2[0], v1[1]-v2[1])
def len_v(v): return math.hypot(v[0], v[1])
def norm_v(v):
    l = len_v(v)
    return (0, 0) if l == 0 else (v[0]/l, v[1]/l)
def dot_v(v1, v2): return v1[0]*v2[0] + v1[1]*v2[1]


def expert_agent_tick(my_pos, my_vel, my_has_flag, enemies, target_pos, is_hunting=False):
    rel_target = sub_v(target_pos, my_pos)
    main_force = norm_v(rel_target)
    jump = False
    force_jump = False

    for e in enemies:
        rel_pos = sub_v(e['pos'], my_pos)
        dist = len_v(rel_pos)

        if is_hunting and dist < 1.5 and not e.get('is_parasitized'):
            dx, dz = abs(rel_pos[0]), abs(rel_pos[1])
            if dx > dz:
                return (0.0, math.copysign(1.0, rel_pos[1]), False, None)
            else:
                return (math.copysign(1.0, rel_pos[0]), 0.0, False, e.get('id'))

        if 0 < dist < 4.0 and not e.get('is_parasitized'):
            rel_vel = sub_v(e['vel'], my_vel)
            approach_rate = dot_v(norm_v(rel_pos), rel_vel)
            if approach_rate > 0:
                lat1 = (-rel_pos[1], rel_pos[0])
                lat2 = (rel_pos[1], -rel_pos[0])
                lat = lat1 if dot_v(norm_v(lat1), main_force) > dot_v(norm_v(lat2), main_force) else lat2
                lat = norm_v(lat)
                mag = (4.0 - dist) * approach_rate * (0.5 if is_hunting else 1.0)
                main_force = (main_force[0] + lat[0] * mag, main_force[1] + lat[1] * mag)

        if e.get('is_parasitized') and 0 < dist < 5.0:
            away = norm_v(rel_pos)
            mag = (5.0 - dist) * 2.0
            main_force = (main_force[0] + away[0] * mag, main_force[1] + away[1] * mag)

    final_vec = norm_v(main_force)
    if len_v(my_vel) < 0.1 and len_v(rel_target) > 1.0:
        jump = True
    if my_has_flag:
        force_jump = True

    atk = None
    for e in enemies:
        if e.get('is_parasitized'):
            continue
        d = len_v(sub_v(e['pos'], my_pos))
        if d < 3.0:
            atk = e.get('id')
            break

    return (final_vec[1], final_vec[0], jump or force_jump, atk)


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
        self.prev_pos = None
        self.my_vel = (0.0, 0.0)
        self.entity_prev = {}
        self.atk_idx = 0

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

    def is_mob(self, e):
        t = e.type.lower()
        return 'mooshroom' in t or 'cow' in t or 'silverfish' in t

    def flag_available(self, pos):
        fx, fz = pos
        g0 = self.b.get_block(fx, self.G, fz)
        f2 = self.b.get_block(fx, self.G + 2, fz)
        if g0 is None or f2 is None:
            return True
        return 'copper' in g0.type.lower() and 'banner' in f2.type.lower()

    def gold_empty(self, pos):
        gx, gz = pos
        g0 = self.b.get_block(gx, self.G, gz)
        if g0 is None:
            return True
        if 'gold' not in g0.type.lower():
            return False
        a1 = self.b.get_block(gx, self.G + 1, gz)
        a2 = self.b.get_block(gx, self.G + 2, gz)
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
        result = set()
        if self.map_fixed:
            for pos in self.my_golds:
                if self.gold_empty(pos):
                    result.add(pos)
        else:
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
        if invader is not None:
            d = math.hypot(invader.x - px, invader.z - pz)
            if d < 10:
                return (invader.x, invader.z)
        flags = self.available_flags()
        if flags:
            my_half = [f for f in flags if self.on_my_half(f[0])]
            other = [f for f in flags if not self.on_my_half(f[0])]
            dk = lambda f: (f[0]-px)**2 + (f[1]-pz)**2
            for f in sorted(my_half, key=dk) + sorted(other, key=dk):
                if not self.coord or self.coord.claim(f, self.my_name, False):
                    return f
        return (self.enemy_flag_x, 0)

    def build_enemies(self, px, pz):
        enemies = []
        for eid, e in self.b.entities.items():
            ex, ez = e.x, e.z
            prev = self.entity_prev.get(eid, (ex, ez))
            ev = (ex - prev[0], ez - prev[1])
            self.entity_prev[eid] = (ex, ez)

            if self.is_enemy_player(e) and not self.is_infected(e):
                has_flag = bool(e.helmet and 'banner' in e.helmet.lower())
                enemies.append({'pos': (ex, ez), 'vel': ev, 'has_flag': has_flag,
                                'is_parasitized': False, 'id': eid})
            elif self.is_mob(e):
                enemies.append({'pos': (ex, ez), 'vel': ev, 'has_flag': False,
                                'is_parasitized': False, 'id': eid})
            elif self.is_infected(e) and 'player' in e.type.lower():
                nm = e.name or ""
                if nm != self.my_name and nm not in self.teammate_names:
                    enemies.append({'pos': (ex, ez), 'vel': ev, 'has_flag': False,
                                    'is_parasitized': True, 'id': eid})
        return enemies

    def check_hunt(self, enemies, px, pz, hasFlag):
        for e in enemies:
            if e.get('is_parasitized'):
                continue
            d = len_v(sub_v(e['pos'], (px, pz)))
            if (e.get('has_flag') and d < 15) or (d < 5 and not hasFlag):
                return True, (e['pos'][0] + e['vel'][0] * 5, e['pos'][1] + e['vel'][1] * 5)
        return False, None

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

        cur_pos = (px, pz)
        if self.prev_pos is not None:
            self.my_vel = (cur_pos[0] - self.prev_pos[0], cur_pos[1] - self.prev_pos[1])
        self.prev_pos = cur_pos

        enemies = self.build_enemies(px, pz)
        target = self.pick_target(px, pz, hasFlag)
        is_hunting, hunt_pos = self.check_hunt(enemies, px, pz, hasFlag)
        if is_hunting and hunt_pos is not None:
            target = hunt_pos

        forward, strafe, jump, atk = expert_agent_tick(
            (px, pz), self.my_vel, hasFlag, enemies, target, is_hunting)

        move_x = strafe
        move_z = forward
        flen = math.hypot(move_x, move_z)
        if flen > 0.01:
            yaw = math.degrees(math.atan2(-move_x, move_z)) % 360.0
            w = True
            sprint = self.b.hunger > 6
        else:
            yaw = math.degrees(math.atan2(-(target[0]-px), target[1]-pz)) % 360.0 if (target[0]-px)**2+(target[1]-pz)**2 > 0.01 else 0.0
            w = False
            sprint = False

        nearest_enemy = min((len_v(sub_v(e['pos'], (px, pz))) for e in enemies if not e.get('is_parasitized')), default=999)
        a_key = False
        d_key = False
        if nearest_enemy < 5.0 and not is_hunting:
            yaw = (yaw + math.sin(self.tick_count * 3.5) * 6.0) % 360.0
            if self.tick_count % 6 < 3:
                a_key = True
            else:
                d_key = True
        elif strafe > 0.3:
            d_key = True
        elif strafe < -0.3:
            a_key = True

        if hasFlag and self.b.hunger > 6:
            jump = True

        if atk is None:
            mobs = [e['id'] for e in enemies if self.is_mob_by_id(e['id'])]
            if mobs:
                atk = mobs[self.atk_idx % len(mobs)]
                self.atk_idx += 1

        self.b.set(yaw=yaw, pitch=0.0, w=w, a=a_key, d=d_key,
                   sprint=sprint, jump=jump, attack=atk)

        if self.tick_count % 100 == 0:
            print(f"[{self.my_name}] #{self.tick_count} ({px:.1f},{pz:.1f}) flag={hasFlag} "
                  f"target=({target[0]:.0f},{target[1]:.0f}) hunt={is_hunting}")

    def is_mob_by_id(self, eid):
        e = self.b.entities.get(eid)
        return e is not None and self.is_mob(e)
