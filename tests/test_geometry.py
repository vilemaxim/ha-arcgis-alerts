"""Tests for point-in-polygon."""

from custom_components.arcgis_alerts.geometry import feature_contains, point_in_rings

from .conftest import TEST_LATITUDE, TEST_LONGITUDE, load_fixture

OUTER = [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]
HOLE = [[3, 3], [7, 3], [7, 7], [3, 7], [3, 3]]
SECOND_PART = [[20, 20], [20, 25], [25, 25], [25, 20], [20, 20]]


def test_polygon_with_hole() -> None:
    """A point in the hole is outside; a point between the rings is inside."""
    rings = [OUTER, HOLE]
    assert point_in_rings(1, 1, rings)
    assert point_in_rings(9, 5, rings)
    assert not point_in_rings(5, 5, rings)
    assert not point_in_rings(11, 5, rings)
    assert not point_in_rings(-1, -1, rings)


def test_multipart_polygon() -> None:
    """Each outer ring of a multipart polygon counts."""
    rings = [OUTER, HOLE, SECOND_PART]
    assert point_in_rings(22, 22, rings)
    assert point_in_rings(1, 1, rings)
    assert not point_in_rings(15, 15, rings)


def test_missing_geometry() -> None:
    """A feature without rings covers nothing."""
    assert not feature_contains(None, 0, 0)
    assert not feature_contains({}, 0, 0)
    assert not feature_contains({"rings": []}, 0, 0)


def test_recorded_features_cover_test_point() -> None:
    """The three recorded SWBNO polygons cover the test point and not far away."""
    features = load_fixture("query_at_point_all.json")["features"]
    assert len(features) == 3
    for feature in features:
        assert feature_contains(feature["geometry"], TEST_LONGITUDE, TEST_LATITUDE)
        assert not feature_contains(feature["geometry"], -91.5, 31.0)
