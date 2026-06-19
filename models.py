from typing import *
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class BlockInfo:
    type: str
    passable: bool


@dataclass(slots=True)
class EntityInfo:
    id: str
    type: str
    name: Optional[str]
    x: float
    y: float
    z: float
    helmet: Optional[str]
    chestplate: Optional[str]
    leggings: Optional[str]
    boots: Optional[str]


@dataclass(slots=True)
class ItemInfo:
    type: str
    amount: int


@dataclass(slots=True)
class InputInfo:
    yaw: float
    pitch: float
    w: bool
    a: bool
    s: bool
    d: bool
    jump: bool
    sneak: bool
    sprint: bool
    fly: bool
    attack: str


class Chunk:
    def __init__(self, x: int, y: int, z: int):
        self.x: int = x
        self.y: int = y
        self.z: int = z
        self.blocks: list[BlockInfo] = []

    def set_blocks(self, blocks: list[BlockInfo]) -> None:
        self.blocks = blocks

    def get_block(self, x: int, y: int, z: int) -> BlockInfo:
        x = x & 15
        y = y & 15
        z = z & 15
        return self.blocks[z << 8 | y << 4 | x]

    def set_block(self, x: int, y: int, z: int, block_info: BlockInfo) -> None:
        x = x & 15
        y = y & 15
        z = z & 15
        self.blocks[z << 8 | y << 4 | x] = block_info
