import math
from typing import *
from config import (MOOSHROOM_R, SILVERFISH_R, INFECTED_R,
                    ENEMY_R_DEFEND, ENEMY_R_STEAL, TEAMMATE_R, BLOCK_REPEL_R, ATTACK_RANGE,
                    REPULSION_A, REPULSION_B_FRAC, REPULSION_CANCEL, MIN_DIST, EXCLUDE_THRESH)


class ThreatField:
    def __init__(self, bot, my_name: str, teammate_names: set, enemy_names: set, role: str, team: str):
        self.b = bot
        self.my_name = my_name
        self.teammate_names = teammate_names or set()
        self.enemy_names = enemy_names or set()
        self.role = role
        self.my_side = team
        self.G: int = 0
        self.mobs: list = []
        self.enemies: list = []
        self.teammates: list = []
        self._atk_idx = 0

    def update(self) -> None:
        self.mobs = []
        self.enemies = []
        self.teammates = []
        for e in self.b.entities.values():
            t = e.type.lower()
            if e.helmet and 'leather_helmet' in e.helmet.lower():
                self.mobs.append((e.x, e.z, INFECTED_R))
            elif 'mooshroom' in t or 'cow' in t:
                self.mobs.append((e.x, e.z, MOOSHROOM_R))
            elif 'silverfish' in t:
                self.mobs.append((e.x, e.z, SILVERFISH_R))
            elif self.is_enemy_player(e):
                r = ENEMY_R_STEAL if self.role == 'steal' else ENEMY_R_DEFEND
                self.enemies.append((e.x, e.z, r))
            elif self.is_teammate(e):
                self.teammates.append((e.x, e.z, TEAMMATE_R))

    def on_my_half(self, x: float) -> bool:
        return (x < 0) == (self.my_side == 'left')

    def is_teammate(self, e) -> bool:
        if 'player' not in e.type.lower():
            return False
        nm = e.name or ""
        if nm == self.my_name:
            return False
        if self.is_infected(e):
            return False
        return nm in self.teammate_names

    def is_enemy_player(self, e) -> bool:
        if 'player' not in e.type.lower():
            return False
        nm = e.name or ""
        if nm == self.my_name:
            return False
        if nm in self.teammate_names:
            return False
        if self.enemy_names:
            return nm in self.enemy_names
        return True

    def is_infected(self, e) -> bool:
        return e.helmet is not None and 'leather_helmet' in e.helmet.lower()

    def enemy_carrier(self):
        px, py, pz = self.b.location
        best = None
        nd = 1e18
        for e in self.b.entities.values():
            if not self.is_enemy_player(e):
                continue
            if self.is_infected(e):
                continue
            if e.helmet and 'banner' in e.helmet.lower():
                d = math.hypot(e.x - px, e.z - pz)
                if d < nd:
                    nd = d
                    best = e
        return best

    def nearest_enemy_in_my_half(self):
        px, py, pz = self.b.location
        best = None
        nd = 1e18
        for e in self.b.entities.values():
            if not self.is_enemy_player(e):
                continue
            if self.is_infected(e):
                continue
            if not self.on_my_half(e.x):
                continue
            d = math.hypot(e.x - px, e.z - pz)
            if d < nd:
                nd = d
                best = e
        return best

    def next_attack_target(self) -> Optional[str]:
        px, py, pz = self.b.location
        nearest_enemy = None
        nd = 1e18
        for e in self.b.entities.values():
            if not self.is_enemy_player(e):
                continue
            if self.is_infected(e):
                continue
            d = math.hypot(e.x - px, e.z - pz)
            if d < ATTACK_RANGE and d < nd:
                nd = d
                nearest_enemy = e
        if nearest_enemy is not None:
            return nearest_enemy.id
        ids = [e.id for e in self.b.entities.values() if 'player' not in e.type.lower()]
        if ids:
            t = ids[self._atk_idx % len(ids)]
            self._atk_idx += 1
            return t
        return None

    def repulsion(self, px: float, pz: float, exclude: Optional[tuple] = None) -> tuple:
        rx = 0.0
        rz = 0.0
        best_mag = 0.0
        best_rx = 0.0
        best_rz = 0.0
        n = 0
        for (ex, ez, R) in self.mobs + self.enemies + self.teammates:
            if exclude is not None and abs(ex - exclude[0]) < EXCLUDE_THRESH and abs(ez - exclude[1]) < EXCLUDE_THRESH:
                continue
            dx = px - ex
            dz = pz - ez
            d = math.hypot(dx, dz)
            if MIN_DIST < d < R:
                mag = REPULSION_A * math.exp(-d / (R * REPULSION_B_FRAC))
                ux = dx / d
                uz = dz / d
                rx += mag * ux
                rz += mag * uz
                if mag > best_mag:
                    best_mag = mag
                    best_rx = mag * ux
                    best_rz = mag * uz
                n += 1
        if n >= 2 and (rx * rx + rz * rz) < (best_mag * REPULSION_CANCEL) ** 2:
            return best_rx, best_rz
        return rx, rz

    def nearest_mob_dist(self, px: float, pz: float, exclude: Optional[tuple] = None) -> float:
        best = 1e18
        for (ex, ez, R) in self.mobs + self.enemies:
            if exclude is not None and abs(ex - exclude[0]) < EXCLUDE_THRESH and abs(ez - exclude[1]) < EXCLUDE_THRESH:
                continue
            d = math.hypot(px - ex, pz - ez)
            if d < best:
                best = d
        return best

    def block_repulsion(self, px: float, pz: float) -> tuple:
        rx = 0.0
        rz = 0.0
        fx = int(math.floor(px))
        fz = int(math.floor(pz))
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if dx == 0 and dz == 0:
                    continue
                bx = fx + dx
                bz = fz + dz
                solid = False
                for yy in (self.G + 1, self.G + 2):
                    blk = self.b.get_block(bx, yy, bz)
                    if blk and not blk.passable:
                        solid = True
                        break
                if not solid:
                    continue
                ddx = px - (bx + 0.5)
                ddz = pz - (bz + 0.5)
                d = math.hypot(ddx, ddz)
                if d < BLOCK_REPEL_R:
                    f = (BLOCK_REPEL_R - d) / max(d, MIN_DIST)
                    rx += ddx * f
                    rz += ddz * f
        return rx, rz
