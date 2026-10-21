import pytest

from storage_visualizer.core.dfsize import df_size

# df -B1 vs df -h on debian-dev, coreutils 9.7
DF_FIXTURES = [
    (420536655872, "392G"),
    (122371670016, "114G"),
    (276727062528, "258G"),
    (1071628288, "1022M"),
    (4743168, "4.6M"),
    (1066885120, "1018M"),
    (3829392867328, "3.5T"),
    (2660562370560, "2.5T"),
    (1168830496768, "1.1T"),
    (9589459386368, "8.8T"),
    (2865106944, "2.7G"),
    (8251813888, "7.7G"),
    (131072, "128K"),
    (26255, "26K"),
    (99697, "98K"),
    (0, "0"),
]
EDGES = [
    (1023, "1023"),
    (1024, "1.0K"),
    (10239, "10K"),
    (1024**2 - 1, "1.0M"),
    (1024**7, "1024E"),
]


@pytest.mark.parametrize("n,expected", DF_FIXTURES + EDGES)
def test_df_size_matches_df_h(n, expected):
    assert df_size(n) == expected
