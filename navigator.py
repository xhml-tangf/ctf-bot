import math
import heapq
from typing import *
from config import DIRS, ARENA_X, ARENA_Z, HONEY_COST, THREAT_COST_K


class Navigator:
    def __init__(self, bot, threats):
        self.b = bot
        self.threats = threats
        self.G: int = 0

    def detect_ground_y(self) -> int:
        px, py, pz = self.b.location
        x = int(math.floor(px))
        z = int(math.floor(pz))
        feet = int(math.floor(py))
        for yy in range(feet + 1, feet - 4, -1):
            blk = self.b.get_block(x, yy, z)
            if blk and not blk.passable:
                return yy
        return feet - 1

    def walkable(self, x: int, z: int, optimistic: bool = True) -> bool:
        g0 = self.b.get_block(x, self.G, z)
        if g0 is None:
            return optimistic
        if g0.passable:
            return False
        g1 = self.b.get_block(x, self.G + 1, z)
        g2 = self.b.get_block(x, self.G + 2, z)
        if g1 is None or g2 is None:
            return optimistic

        def _clear(blk):
            if blk and 'fence_gate' in blk.type.lower():
                return True
            return blk.passable

        if not _clear(g1) or not _clear(g2):
            return False
        for blk in (g0, g1, g2):
            if blk:
                bt = blk.type.lower()
                if ('fence' in bt and 'gate' not in bt) or 'wall' in bt:
                    return False
        t1 = g1.type.lower()
        t2 = g2.type.lower()
        if 'water' in t1 or 'water' in t2:
            return False
        return True

    def col_ground_y(self, x: int, z: int) -> int:
        for yy in range(self.G + 2, self.G - 3, -1):
            blk = self.b.get_block(x, yy, z)
            if blk and not blk.passable:
                return yy
        return self.G

    def terrain_cost(self, x: int, z: int) -> float:
        c = 1.0
        for yy in (self.G + 1, self.G + 2):
            blk = self.b.get_block(x, yy, z)
            if blk and 'honey' in blk.type.lower():
                c *= HONEY_COST
        cx = x + 0.5
        cz = z + 0.5
        for (ex, ez, R) in self.threats.mobs + self.threats.enemies:
            d = math.hypot(cx - ex, cz - ez)
            if d < R:
                c *= 1.0 + (R - d) * THREAT_COST_K
        return c

    def dijkstra(self, start: tuple, targets: set) -> Optional[list]:
        if start in targets:
            return [start]
        heap = [(0.0, start)]
        came: dict = {start: None}
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
                if not self.walkable(nx, nz):
                    continue
                if dx != 0 and dz != 0:
                    if not self.walkable(cx + dx, cz) and not self.walkable(cx, cz + dz):
                        continue
                nc = cost + dc * self.terrain_cost(nx, nz)
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

    def need_jump(self, wx: int, wz: int) -> bool:
        px = int(math.floor(self.b.location[0]))
        pz = int(math.floor(self.b.location[2]))
        cg = self.col_ground_y(px, pz)
        tg = self.col_ground_y(wx, wz)
        if tg > cg:
            return True
        for yy in (self.G + 1, self.G + 2):
            blk = self.b.get_block(wx, yy, wz)
            if blk:
                bt = blk.type.lower()
                if 'honey' in bt:
                    return True
                if not blk.passable:
                    return True
        return False
