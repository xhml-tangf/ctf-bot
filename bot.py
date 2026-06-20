import websocket
import time
import json
import threading
import zstandard as zstd
import traceback
import math
from typing import *
from models import BlockInfo, EntityInfo, ItemInfo, Chunk


class Bot:
    def __init__(self, name: str, uri: str):
        self.name: str = name
        self.uri: str = uri
        self.websocket: Optional[websocket.WebSocket] = None
        self.input: dict = {}
        self.cctx: zstd.ZstdDecompressor = zstd.ZstdDecompressor()

        self.location: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.chunks: dict[tuple[int, int, int], Chunk] = {}
        self.health: int = 20
        self.hunger: int = 20
        self.entities: dict[str, EntityInfo] = {}
        self.backpack: list[ItemInfo] = []

    def connect(self, timeout: int = 10, retries: int = 4) -> bool:
        if self.websocket is not None:
            return True
        last_err = None
        for attempt in range(retries):
            try:
                print(f"[{self.name}] step1: dialing {self.uri} (attempt {attempt + 1}/{retries})")
                self.websocket = websocket.create_connection(self.uri, timeout=timeout)
                print(f"[{self.name}] step2: TCP+WS handshake OK")
                self.websocket.send(f'{{"type": "login", "name": "{self.name}"}}')
                print(f"[{self.name}] step3: login sent as {self.name}")
                self.recv_thread = threading.Thread(target=self._receive_loop, daemon=True)
                self.recv_thread.start()
                print(f"[{self.name}] step4: recv thread started, waiting for first frame...")
                return True
            except Exception as e:
                last_err = e
                print(f"[{self.name}] connect FAILED attempt {attempt + 1}/{retries}: {type(e).__name__}: {e}")
                self.websocket = None
                time.sleep(1.5)
        print(f"[{self.name}] connect PERMANENTLY FAILED: {last_err}")
        return False

    def set(self, yaw: Optional[float] = None, pitch: Optional[float] = None,
            w: Optional[bool] = None, a: Optional[bool] = None,
            s: Optional[bool] = None, d: Optional[bool] = None,
            jump: Optional[bool] = None, sneak: Optional[bool] = None,
            sprint: Optional[bool] = None, fly: Optional[bool] = None,
            attack: Optional[str] = None) -> None:

        args = {k: v for k, v in locals().items() if k != 'self' and v is not None}
        for key, value in args.items():
            self.input[key] = value

        if self.websocket:
            self.websocket.send(json.dumps({"type": "input", "input": self.input}))
        self.input.pop("attack", None)

    def set_direction(self, x: float, y: float, z: float) -> None:
        _2PI = math.pi * 2
        if x == 0 and z == 0:
            self.input['pitch'] = -90 if y > 0 else 90
        else:
            theta = math.atan2(-x, z)
            self.input['yaw'] = math.degrees((theta + _2PI) % _2PI)
            xz = math.sqrt(x * x + z * z)
            self.input['pitch'] = math.degrees(math.atan(-y / xz))
        self.set(yaw=self.input.get('yaw', 0), pitch=self.input['pitch'])

    def on_msg(self, callback: Callable[[str], None]) -> None:
        self.msg_callback = callback

    def _receive_loop(self) -> None:
        frame_count = 0
        while self.connected():
            try:
                bytes_data = self.websocket.recv()
                frame_count += 1
                if frame_count == 1:
                    print(f"[{self.name}] step5: first frame received OK")
                if frame_count % 400 == 0:
                    print(f"[{self.name}] alive: {frame_count} frames, loc={self.location[0]:.1f},{self.location[2]:.1f}")
                if bytes_data is None or bytes_data == '':
                    print(f"[{self.name}] DROPPED: empty recv after {frame_count} frames")
                    break
                if isinstance(bytes_data, str):
                    message = bytes_data
                else:
                    message = self.cctx.decompress(bytes_data).decode("utf-8")
                try:
                    j = json.loads(message)
                except json.JSONDecodeError:
                    print("[raw-non-json]", repr(message[:300]))
                    continue
                self.location = (j["playerLocation"]["x"], j["playerLocation"]["y"], j["playerLocation"]["z"])
                self.health = j["playerHealth"]
                self.hunger = j["playerFoodLevel"]
                self.entities = {e["id"]: EntityInfo(**e) for e in j["nearbyEntities"]}

                self.chunks = {k: self.chunks[k] for k in [(c["x"], c["y"], c["z"]) for c in j.get("keepChunks", [])]}

                for chunk in j.get("newChunks", []):
                    c = Chunk(chunk["x"], chunk["y"], chunk["z"])
                    c.set_blocks([BlockInfo(**b) for b in chunk["blocks"]])
                    self.chunks[(chunk["x"], chunk["y"], chunk["z"])] = c

                for block in j.get("updateBlocks", []):
                    x = block["x"]
                    y = block["y"]
                    z = block["z"]
                    cx = x >> 4
                    cy = y >> 4
                    cz = z >> 4
                    if (cx, cy, cz) in self.chunks:
                        self.chunks[(cx, cy, cz)].set_block(x, y, z, BlockInfo(**block["block"]))
                self.backpack = [ItemInfo(**item) for item in j.get('backpack', [])]

                if hasattr(self, 'msg_callback'):
                    for msg in j.get("messages", []):
                        self.msg_callback(msg)
            except Exception as e:
                print(f"[{self.name}] DROPPED: {type(e).__name__}: {e} after {frame_count} frames")
                traceback.print_exc()
                break

    def get_block(self, x: int, y: int, z: int) -> Optional[BlockInfo]:
        cx = x >> 4
        cy = y >> 4
        cz = z >> 4
        if (cx, cy, cz) in self.chunks:
            return self.chunks[(cx, cy, cz)].get_block(x, y, z)
        else:
            return None

    def get_entity(self, id: str) -> Optional[EntityInfo]:
        return self.entities.get(id, None)

    def get_nearby_entities(self) -> list[EntityInfo]:
        return list(self.entities.values())

    def chat(self, msg: str) -> None:
        if self.websocket:
            self.websocket.send(json.dumps({"type": "chat", "message": msg}))

    def connected(self) -> bool:
        return bool(self.websocket and self.websocket.connected and self.recv_thread.is_alive())

    def disconnect(self) -> None:
        if self.websocket is not None:
            self.websocket.close()
            self.websocket = None
