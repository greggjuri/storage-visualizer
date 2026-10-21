import pytest

from storage_visualizer.core import labels
from storage_visualizer.core.labels import (
    decode_udev,
    local_label,
    network_label,
    read_device_labels,
)


@pytest.fixture
def fake_dev(tmp_path):
    dev = tmp_path / "dev"
    (dev / "disk/by-label").mkdir(parents=True)
    (dev / "mapper").mkdir()
    (dev / "sdc4").touch()
    (dev / "dm-0").touch()
    (dev / "disk/by-label" / "Bork\\x20Bork").symlink_to("../../sdc4")
    (dev / "disk/by-label" / "vg-data").symlink_to("../../dm-0")
    (dev / "disk/by-label" / "ghost").symlink_to("../../nope")
    (dev / "mapper/x").symlink_to("../dm-0")
    return dev


@pytest.mark.parametrize(
    "device,mp,expected",
    [
        ("//192.168.1.11/mansion", "/mnt/nas", "mansion"),
        ("//nas/share/sub/", "/mnt/x", "sub"),
        ("//nas", "/mnt/x", "x"),
        ("192.168.1.184:/volume1/media", "/mnt/nas-media", "media"),
        ("host:/export/", "/mnt/e", "export"),
        ("user@host:", "/mnt/remote", "remote"),
        ("user@host:/", "/mnt/remote", "remote"),
        ("user@host:docs", "/mnt/remote", "docs"),
        ("user@host:", "/mnt/remote/", "remote"),  # trailing slash on the mount point
    ],
)
def test_network_label(device, mp, expected):
    assert network_label(device, mp) == expected


@pytest.mark.parametrize(
    "mp,name,expected",
    [
        ("/", "debian", "System"),
        ("/", None, "System"),
        ("/mnt/hoepsis", "Hoepsis", "Hoepsis"),
        ("/mnt/hoepsis", None, "hoepsis"),
        ("/mnt/hoepsis", "", "hoepsis"),
        ("/run/media/juri/My Disk", None, "My Disk"),
    ],
)
def test_local_label(mp, name, expected):
    assert local_label(mp, name) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Bork\\x20Bork", "Bork Bork"),
        ("caf\\xc3\\xa9", "café"),
        ("bad\\xff", "bad�"),
        ("plain-Name_1", "plain-Name_1"),
        ("ünï", "ünï"),
    ],
)
def test_decode_udev(raw, expected):
    assert decode_udev(raw) == expected


def test_read_device_labels_decodes_and_matches(fake_dev):
    assert read_device_labels([str(fake_dev / "sdc4")], str(fake_dev / "disk/by-label")) == {
        str(fake_dev / "sdc4"): "Bork Bork"
    }


def test_read_device_labels_matches_through_symlinked_device(fake_dev):
    mapper = str(fake_dev / "mapper/x")
    assert read_device_labels([mapper], str(fake_dev / "disk/by-label")) == {mapper: "vg-data"}


def test_read_device_labels_omits_unlabelled_devices(fake_dev):
    assert read_device_labels([str(fake_dev / "sdz9")], str(fake_dev / "disk/by-label")) == {}


def test_read_device_labels_missing_dir_is_empty(tmp_path):
    assert read_device_labels(["/dev/sda1"], str(tmp_path / "nope")) == {}


def test_read_device_labels_unreadable_dir_is_empty(monkeypatch, fake_dev):
    def boom(path):
        raise PermissionError("denied")

    monkeypatch.setattr(labels.os, "listdir", boom)
    assert read_device_labels([str(fake_dev / "sdc4")], str(fake_dev / "disk/by-label")) == {}
