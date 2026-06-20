import threading


class TeamCoord:
    def __init__(self):
        self.flags: dict = {}
        self.gold: dict = {}
        self.lock = threading.Lock()

    def claim(self, pos: tuple, name: str, is_gold: bool) -> bool:
        table = self.gold if is_gold else self.flags
        with self.lock:
            cur = table.get(pos)
            if cur is not None and cur != name:
                return False
            table[pos] = name
            return True

    def release_flag(self, name: str) -> None:
        with self.lock:
            self.flags = {p: n for p, n in self.flags.items() if n != name}

    def release_gold(self, name: str) -> None:
        with self.lock:
            self.gold = {p: n for p, n in self.gold.items() if n != name}
