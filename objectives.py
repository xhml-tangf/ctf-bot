import math
from typing import *
from config import ARENA_X, ARENA_Z


class ObjectiveSelector:
    def __init__(self, bot, my_side: str, team: str, map_fixed: bool, coord,
                 my_name: str, enemy_flags: list, my_golds: list,
                 seek_center: tuple, return_center: tuple, navigator):
        self.b = bot
        self.my_side = my_side
        self.team = team
        self.map_fixed = map_fixed
        self.coord = coord
        self.my_name = my_name
        self.enemy_flags = enemy_flags
        self.my_golds = my_golds
        self.seek_center = seek_center
        self.return_center = return_center
        self.nav = navigator
        self.G: int = 0
        self.flag_memory: set = set()
        self.captured: set = set()
        self.used_gold: set = set()
        self.locked_flag = None
        self.locked_gold = None

    def on_my_half(self, x: float) -> bool:
        return (x < 0) == (self.my_side == 'left')

    def flag_available(self, pos: tuple) -> bool:
        fx, fz = pos
        g0 = self.b.get_block(fx, self.G, fz)
        f2 = self.b.get_block(fx, self.G + 2, fz)
        if g0 is None or f2 is None:
            return True
        if 'copper' in g0.type.lower() and 'banner' in f2.type.lower():
            return True
        return False

    def gold_empty(self, pos: tuple) -> bool:
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

    def scan_flags(self) -> set:
        result = set()
        enemy_banner = 'blue_banner' if (self.my_side or self.team) == 'left' else 'red_banner'
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

    def scan_gold(self) -> set:
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

    def available_flags(self) -> set:
        scanned = self.scan_flags()
        self.flag_memory |= scanned
        gone = {p for p in self.flag_memory
                if self.b.get_block(p[0], self.G, p[1]) is not None and not self.flag_available(p)}
        self.flag_memory -= gone
        result = {p for p in self.flag_memory if self.flag_available(p)}
        if self.map_fixed:
            for pos in self.enemy_flags:
                if pos in self.captured:
                    continue
                if self.flag_available(pos):
                    result.add(pos)
        if self.coord:
            result = {f for f in result if self.coord.flags.get(f) in (None, self.my_name)}
        return result

    def empty_gold(self) -> set:
        if self.map_fixed:
            result = set()
            for pos in self.my_golds:
                if pos in self.used_gold:
                    continue
                if self.gold_empty(pos):
                    result.add(pos)
            result = {g for g in result if self.coord.gold.get(g) in (None, self.my_name)} if self.coord else result
            return result
        my_half = ((self.my_side or self.team) == 'left')
        result = {g for g in self.scan_gold() if (g[0] < 0) == my_half}
        if self.coord:
            result = {g for g in result if self.coord.gold.get(g) in (None, self.my_name)}
        return result

    def current_objective(self, goal: str, px: float, pz: float) -> Optional[tuple]:
        if goal == 'seek':
            if self.locked_flag is not None and self.flag_available(self.locked_flag) and self.coord.claim(self.locked_flag, self.my_name, False):
                return self.locked_flag
            flags = self.available_flags()
            my_half = [f for f in flags if self.on_my_half(f[0])]
            other = [f for f in flags if not self.on_my_half(f[0])]
            dk = lambda f: (f[0] - px) ** 2 + (f[1] - pz) ** 2
            order = sorted(my_half, key=dk) + sorted(other, key=dk)
            for f in order:
                if self.coord.claim(f, self.my_name, False):
                    self.locked_flag = f
                    return f
            self.locked_flag = None
            return None
        else:
            if self.locked_gold is not None and self.gold_empty(self.locked_gold) and self.coord.claim(self.locked_gold, self.my_name, True):
                return self.locked_gold
            golds = self.empty_gold()
            order = sorted(golds, key=lambda g: (g[0] - px) ** 2 + (g[1] - pz) ** 2)
            for g in order:
                if self.coord.claim(g, self.my_name, True):
                    self.locked_gold = g
                    return g
            self.locked_gold = None
            return None

    def explore_destination(self, goal: str) -> Optional[tuple]:
        return self.seek_center if goal == 'seek' else self.return_center

    def targets_around(self, pos: tuple, include_center: bool) -> set:
        cells = set()
        fx, fz = pos
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if not include_center and dx == 0 and dz == 0:
                    continue
                if self.nav.walkable(fx + dx, fz + dz):
                    cells.add((fx + dx, fz + dz))
        return cells
