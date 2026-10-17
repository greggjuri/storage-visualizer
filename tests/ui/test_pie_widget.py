import pytest

from storage_visualizer.core.models import Volume
from storage_visualizer.ui.pie_widget import PieWidget, used_percent


@pytest.mark.parametrize(
    "used,free,expected",
    [
        (2_867_200, 1_024_000, 74),
        (1, 999, 1),
        (0, 100, 0),
        (100, 0, 100),
        (0, 0, 0),
        (999, 1, 100),
    ],
)
def test_used_percent_ceil_against_used_plus_free(used, free, expected):
    assert used_percent(used, free) == expected


OK = Volume("/mnt/backup", "/mnt/backup", "ext4", False, "ok", 4_096_000, 2_867_200, 1_024_000)


@pytest.mark.parametrize(
    "volume",
    [
        None,
        OK,
        Volume("/z", "/z", "ext4", False, "ok", 0, 0, 0),
        Volume("/x", "/x", "ext4", False, "unavailable", None, None, None),
    ],
)
def test_pie_renders_each_state(qtbot, volume):
    w = PieWidget("/run/media/juri/My Passport Ultra 2TB With A Very Long Name")
    qtbot.addWidget(w)
    if volume is not None:
        w.set_volume(volume)
    assert w.volume == volume
    assert not w.grab().isNull()
