# team.py — 团队协调: 旗/金目标认领, 防止3个bot抢同一目标
import threading


class TeamCoord:
    """线程安全的认领协调器。共享于3个Brain实例之间。"""
    def __init__(self):
        self.flags: dict = {}       # flag_pos → bot_name (已认领的旗帜)
        self.gold: dict = {}        # gold_pos → bot_name (已认领的金块)
        self.lock = threading.Lock()

    def claim(self, pos: tuple, name: str, is_gold: bool) -> bool:
        """认领目标。若已被其他bot认领→返回False; 否则认领成功→True"""
        table = self.gold if is_gold else self.flags
        with self.lock:
            cur = table.get(pos)
            if cur is not None and cur != name:
                return False        # 已被别人认领
            table[pos] = name
            return True

    def release_flag(self, name: str) -> None:
        """释放该bot的所有旗帜认领(拾取/传给金块后调用)"""
        with self.lock:
            self.flags = {p: n for p, n in self.flags.items() if n != name}

    def release_gold(self, name: str) -> None:
        """释放该bot的所有金块认领(上交/掉旗后调用)"""
        with self.lock:
            self.gold = {p: n for p, n in self.gold.items() if n != name}
