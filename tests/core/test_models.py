import dataclasses

import pytest

from storage_visualizer.core.models import MountInfo, Volume


def test_volume_is_frozen():
    v = Volume("/", "/", "ext4", False, "ok", 10, 4, 6)
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.used = 5


def test_mountinfo_fields():
    m = MountInfo("/dev/sda1", "/mnt/x", "ext4", False)
    assert (m.device, m.mount_point, m.fstype, m.is_network) == (
        "/dev/sda1",
        "/mnt/x",
        "ext4",
        False,
    )
