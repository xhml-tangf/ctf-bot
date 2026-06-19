import math
import time
from typing import *
from config import (WAYPOINT_REACH, STUCK_THRESH, STUCK_JUMP, STEER_DEAD, NEAR_DOUBLED,
                    KITE_DIST, CATCH_NEAR, DEPOSIT_SLOW, PATROL_RING, RECOMPUTE_DT,
                    STUCK_MOVE, STUCK_MOVE_DIR, BLOCK_WEIGHT)


class Mover:
    def __init__(self, bot, navigator, threats, my_gold_x: int, enemy_flag_x: int):
        self.b = bot
        self.nav = navigator
        self.threats = threats
        self.my_gold_x = my_gold_x
        self.enemy_flag_x = enemy_flag_x
        self.path = None
        self.idx = 0
        self.last_objective = None
        self.last_recompute = 0.0
        self.last_pos = None
        self.stuck = 0
        self.has_flag = False
        self.atk_target: Optional[str] = None
        self.want_run_jump = False

    def stuck_check(self, px: float, pz: float, dx: float, dz: float) -> None:
        if self.last_pos is not None:
            moved = (px - self.last_pos[0]) ** 2 + (pz - self.last_pos[1]) ** 2
            if moved < STUCK_MOVE and (abs(dx) + abs(dz)) > STUCK_MOVE_DIR:
                self.stuck += 1
            else:
                self.stuck = 0
        self.last_pos = (px, pz)

    def sprint(self) -> bool:
        return True

    def steer(self, px: float, pz: float, dx: float, dz: float,
              repel_weight: float = 1.0, exclude: Optional[tuple] = None) -> tuple:
        rx, rz = self.threats.repulsion(px, pz, exclude)
        brx, brz = self.threats.block_repulsion(px, pz)
        nd = self.threats.nearest_mob_dist(px, pz, exclude)
        w = repel_weight
        if nd < NEAR_DOUBLED:
            w = repel_weight * 2.0
        bx = dx + rx * w + brx * BLOCK_WEIGHT
        bz = dz + rz * w + brz * BLOCK_WEIGHT
        if abs(bx) + abs(bz) < STEER_DEAD and self.stuck > STUCK_THRESH and (self.threats.mobs or self.threats.enemies):
            all_t = self.threats.mobs + self.threats.enemies
            nt = min(all_t, key=lambda m: (px - m[0]) ** 2 + (pz - m[1]) ** 2)
            ex, ez = nt[0], nt[1]
            bx, bz = -(pz - ez), (px - ex)
            if abs(bx) + abs(bz) < STEER_DEAD:
                bx, bz = 1.0, 0.0
        jump = (self.stuck > STUCK_THRESH)
        return bx, bz, jump

    def _move(self, dx: float, dz: float, *, repel_weight: float = 1.0,
              exclude: Optional[tuple] = None, jump: bool = False,
              sprint: Optional[bool] = None) -> None:
        px, py, pz = self.b.location
        self.stuck_check(px, pz, dx, dz)
        bx, bz, mjump = self.steer(px, pz, dx, dz, repel_weight=repel_weight, exclude=exclude)
        sp = self.sprint() if sprint is None else sprint
        j = jump or (self.stuck > STUCK_JUMP) or mjump
        yaw = math.degrees(math.atan2(-bx, bz)) % 360.0
        self.b.set(yaw=yaw, pitch=0.0, w=True, sprint=sp, jump=j, attack=self.atk_target)

    def follow(self) -> bool:
        if not self.path or self.idx >= len(self.path):
            return False
        px, py, pz = self.b.location
        while self.idx < len(self.path):
            wx, wz = self.path[self.idx]
            cx = wx + 0.5
            cz = wz + 0.5
            if (cx - px) ** 2 + (cz - pz) ** 2 < WAYPOINT_REACH ** 2:
                self.idx += 1
            else:
                break
        if self.idx >= len(self.path):
            return False
        wx, wz = self.path[self.idx]
        dx = (wx + 0.5) - px
        dz = (wz + 0.5) - pz
        run_jump = self.want_run_jump and self.sprint()
        self._move(dx, dz, jump=(run_jump or self.nav.need_jump(wx, wz)))
        return True

    def deposit_micro(self, gold: tuple) -> None:
        gx, gz = gold
        dx = (gx + 0.5) - self.b.location[0]
        dz = (gz + 0.5) - self.b.location[2]
        d = math.hypot(dx, dz)
        self._move(dx, dz, repel_weight=0.4, sprint=(self.sprint() and d > DEPOSIT_SLOW))

    def move_explore(self, goal: str) -> None:
        if goal == 'return':
            dx = (self.my_gold_x + 0.5) - self.b.location[0]
        else:
            dx = (self.enemy_flag_x + 0.5) - self.b.location[0]
        dz = 0.0 - self.b.location[2]
        self._move(dx, dz)

    def patrol(self) -> None:
        px, py, pz = self.b.location
        tx = self.my_gold_x * 0.5 + 0.5
        tz = 0.0
        dx = tx - px
        dz = tz - pz
        if math.hypot(dx, dz) < PATROL_RING:
            dx, dz = -dz, dx
        self._move(dx, dz)

    def pursue(self, target) -> None:
        px, py, pz = self.b.location
        dx = target.x - px
        dz = target.z - pz
        d = math.hypot(dx, dz)
        excl = (target.x, target.z) if self.threats.on_my_half(target.x) else None
        self._move(dx, dz, exclude=excl, jump=(d < CATCH_NEAR))

    def hunt_micro(self, carrier) -> None:
        px, py, pz = self.b.location
        dx = carrier.x - px
        dz = carrier.z - pz
        d = math.hypot(dx, dz)
        if self.threats.on_my_half(carrier.x):
            tdx, tdz = dx, dz
            excl = (carrier.x, carrier.z)
        else:
            excl = None
            if d < KITE_DIST:
                tdx, tdz = -dx, -dz
            else:
                tdx, tdz = dx, dz
        self._move(tdx, tdz, repel_weight=1.0, exclude=excl,
                   jump=(d < CATCH_NEAR or (self.want_run_jump and self.sprint())))

    def needs_recompute(self, objective) -> bool:
        now = time.time()
        return ((self.path is None) or (self.idx >= len(self.path)) or
                (now - self.last_recompute > RECOMPUTE_DT) or (objective != self.last_objective))

    def set_path(self, path, start: tuple, objective) -> None:
        self.path = path
        self.idx = 0
        if self.path and self.path[0] == start:
            self.idx = 1
        self.last_objective = objective
        self.last_recompute = time.time()

    def clear_path(self) -> None:
        self.path = None
