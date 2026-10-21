import pytest

from storage_visualizer.core.models import Volume
from storage_visualizer.ui.pie_widget import (
    MIN_WIDTH,
    WORST_CASE_NUMBERS,
    PieWidget,
    pie_text,
    used_percent,
)


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


OK_LABELLED = Volume("/", "System", "ext4", False, "ok", 420536655872, 122371670016, 276727062528)


@pytest.mark.parametrize(
    "volume",
    [
        None,
        OK,
        OK_LABELLED,
        Volume("/z", "/z", "ext4", False, "ok", 0, 0, 0),
        Volume("/x", "/x", "ext4", False, "unavailable", None, None, None),
    ],
)
def test_pie_renders_each_state(qtbot, volume):
    w = PieWidget(
        "/run/media/juri/My Passport Ultra 2TB With A Very Long Name", "Very Long Label …"
    )
    qtbot.addWidget(w)
    if volume is not None:
        w.set_volume(volume)
    assert w.volume == volume
    assert not w.grab().isNull()


def test_pie_text_ok_has_three_df_lines():
    assert pie_text(OK_LABELLED, "/", "System") == ["System", "114G used · 258G free", "392G total"]


@pytest.mark.parametrize(
    "volume", [None, Volume("/x", "x", "nfs", True, "unavailable", None, None, None)]
)
def test_pie_text_label_only_when_not_ok(volume):
    assert pie_text(volume, "/x", "x") == ["x"]


@pytest.mark.parametrize(
    "volume,label,expected",
    [
        (Volume("/x", "fresh", "ext4", False, "unavailable", None, None, None), "old", "fresh"),
        (Volume("/x", "", "ext4", False, "unavailable", None, None, None), "old", "old"),
        (None, "", "/x"),
    ],
)
def test_pie_text_name_fallback(volume, label, expected):
    assert pie_text(volume, "/x", label)[0] == expected


def test_pie_width_fits_worst_case_numbers(qtbot):
    w = PieWidget("/mnt/nas-media-4k", "media-4k")
    qtbot.addWidget(w)
    assert w.width() >= max(MIN_WIDTH, w.fontMetrics().horizontalAdvance(WORST_CASE_NUMBERS) + 8)
    assert w.height() > 170  # three text lines below the pie
