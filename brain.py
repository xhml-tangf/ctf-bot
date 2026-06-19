import time
import math
from typing import *
from config import FLAG_Z, GOLD_Z, DEPOSIT_NEAR, SIDE_MIN, PICKUP_NEAR_SQ
from threats import ThreatField
from navigator import Navigator
from objectives import ObjectiveSelector
from mover import Mover


class Brain:
    def __init__(self, bot, team: str, map_fixed: bool, enemy_names: Optional[set],
                 my_name: str, role: str, coord, teammate_names: Optional[set] = None):
        self.b = bot
        self.team = team
        self.my_side = team
        self.map_fixed = map_fixed
        self.enemy_names = enemy_names or set()
        self.my_name = my_name
        self.role = role
        self.coord = coord
        self.teammate_names = teammate_names or set()
        if team == 'left':
            self.enemy_flag_x = 22
            self.my_gold_x = -22
        else:
            self.enemy_flag_x = -22
            self.my_gold_x = 22
        self.enemy_flags = [(self.enemy_flag_x, z) for z in FLAG_Z]
        self.my_golds = [(self.my_gold_x, z) for z in GOLD_Z]
        self.seek_center = (self.enemy_flag_x // 2, 0)
        self.return_center = (self.my_gold_x // 2, 0)
        self.G: int = 0
        self.initialized = False
        self.prev_hasFlag = False
        self.prev_infected = False
        self.score = 0
        self._carrier = None
        self.threats = ThreatField(bot, my_name, self.teammate_names, self.enemy_names, role, team)
        self.nav = Navigator(bot, self.threats)
        self.objectives = ObjectiveSelector(bot, self.my_side, team, map_fixed, coord, my_name,
                                            self.enemy_flags, self.my_golds,
                                            self.seek_center, self.return_center, self.nav)
        self.mover = Mover(bot, self.nav, self.threats, self.my_gold_x, self.enemy_flag_x)

    def tick(self) -> None:
        if not self.initialized:
            if self.b.location == (0.0, 0.0, 0.0):
                return
            self.G = self.nav.detect_ground_y()
            if abs(self.b.location[0]) > SIDE_MIN:
                self.my_side = 'left' if self.b.location[0] < 0 else 'right'
            self.nav.G = self.G
            self.threats.G = self.G
            self.threats.my_side = self.my_side
            self.objectives.G = self.G
            self.objectives.my_side = self.my_side
            self.initialized = True
            print(f"[{self.my_name}] init ground_y={self.G} side={self.my_side} role={self.role}")
            return
        self.threats.update()
        self.mover.atk_target = self.threats.next_attack_target()
        hasFlag = any('banner' in item.type.lower() for item in self.b.backpack)
        self.mover.has_flag = hasFlag
        infected = any('leather_helmet' in item.type.lower() for item in self.b.backpack)
        if infected and not self.prev_infected:
            print(f"[{self.my_name}] INFECTED")
        elif not infected and self.prev_infected:
            print(f"[{self.my_name}] RECOVERED")
        self.prev_infected = infected
        self._carrier = self.threats.enemy_carrier()
        if self.role == 'steal':
            self.mover.want_run_jump = hasFlag
        else:
            self.mover.want_run_jump = hasFlag or (self._carrier is not None)
        px, py, pz = self.b.location
        if hasFlag:
            self.objectives.locked_flag = None
            self.coord.release_flag(self.my_name)
        else:
            self.objectives.locked_gold = None
            self.coord.release_gold(self.my_name)
        self._track_transitions(hasFlag, px, pz)
        self.prev_hasFlag = hasFlag

        goal = 'return' if hasFlag else 'seek'
        objective = self.objectives.current_objective(goal, px, pz)
        if goal == 'return' and objective is not None:
            gx, gz = objective
            if math.hypot(gx + 0.5 - px, gz + 0.5 - pz) < DEPOSIT_NEAR:
                self.mover.deposit_micro(objective)
                return
        if not hasFlag and self._role_action(goal, px, pz):
            return
        exploring = False
        if objective is None:
            objective = self.objectives.explore_destination(goal)
            exploring = True
        if objective is None:
            self.mover.clear_path()
            self.mover.move_explore(goal)
            return
        include_center = (goal == 'return') or exploring
        targets = self.objectives.targets_around(objective, include_center)
        start = (int(math.floor(px)), int(math.floor(pz)))
        if self.mover.needs_recompute(objective):
            if targets:
                path = self.nav.dijkstra(start, targets)
                self.mover.set_path(path, start, objective)
            else:
                self.mover.clear_path()
                self.mover.last_objective = objective
                self.mover.last_recompute = time.time()
        if not self.mover.follow():
            self.mover.move_explore(goal)

    def _track_transitions(self, hasFlag: bool, px: float, pz: float) -> None:
        if self.map_fixed:
            if not self.prev_hasFlag and hasFlag:
                best = None
                bd = 1e18
                for pos in self.objectives.enemy_flags:
                    d = (pos[0] - px) ** 2 + (pos[1] - pz) ** 2
                    if d < bd:
                        bd = d
                        best = pos
                if best and bd < PICKUP_NEAR_SQ:
                    self.objectives.captured.add(best)
                    print(f"[{self.my_name}] pickup {best}, {len(self.objectives.captured)}/8")
            if self.prev_hasFlag and not hasFlag:
                best = None
                bd = 1e18
                for pos in self.objectives.my_golds:
                    d = (pos[0] - px) ** 2 + (pos[1] - pz) ** 2
                    if d < bd:
                        bd = d
                        best = pos
                if best and bd < PICKUP_NEAR_SQ:
                    self.objectives.used_gold.add(best)
                    self.score += 1
                    print(f"[{self.my_name}] submit {best}, score {self.score}/8")
        else:
            if not self.prev_hasFlag and hasFlag:
                print(f"[{self.my_name}] pickup (random)")
            if self.prev_hasFlag and not hasFlag:
                self.score += 1
                print(f"[{self.my_name}] submit (random), score {self.score}/8")

    def _role_action(self, goal: str, px: float, pz: float) -> bool:
        if goal == 'return' or self.role == 'steal':
            return False
        if self.role == 'chase':
            if self._carrier is not None:
                self.mover.hunt_micro(self._carrier)
                return True
            if not self.threats.on_my_half(px):
                self.mover.move_explore('return')
                return True
            invader = self.threats.nearest_enemy_in_my_half()
            if invader is not None:
                self.mover.pursue(invader)
                return True
            self.mover.patrol()
            return True
        return False
