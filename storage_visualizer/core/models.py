from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class MountInfo:
    device: str
    mount_point: str
    fstype: str
    is_network: bool
    label: str = ""


@dataclass(frozen=True)
class Volume:
    mount_point: str
    label: str
    fstype: str
    is_network: bool
    status: Literal["ok", "unavailable"]
    total: int | None
    used: int | None
    free: int | None
