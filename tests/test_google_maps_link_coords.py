"""Pin vs viewport: Google Maps place links must resolve to POI, not map camera center."""

import pytest

from utils.geo_utils import (
    _extract_coordinates_from_maps_url,
    _extract_place_pin_coordinates,
    _extract_viewport_coordinates,
)

pytestmark = pytest.mark.no_db

MADAM_LEE_EXPANDED_ZOOMED_OUT = (
    "https://www.google.com/maps/place/Madam+Lee+Korean+BBQ+Denpasar/"
    "@-8.6788385,115.1783469,14759m/data=!3m1!1e3!4m6!3m5!1s0x2dd2413ff6fc91d1:0x359b6e66f2b25d4c"
    "!8m2!3d-8.6809181!4d115.2009929!16s%2Fg%2F11x_v3mxv7"
)

MADAM_LEE_EXPANDED_ZOOMED_IN = (
    "https://www.google.com/maps/place/Madam+Lee+Korean+BBQ+Denpasar/"
    "@-8.6809128,115.198418,820m/data=!3m2!1e3!4b1!4m6!3m5!1s0x2dd2413ff6fc91d1:0x359b6e66f2b25d4c"
    "!8m2!3d-8.6809181!4d115.2009929!16s%2Fg%2F11x_v3mxv7"
)

PIN = (-8.6809181, 115.2009929)
VIEWPORT_FAR = (-8.6788385, 115.1783469)
VIEWPORT_NEAR = (-8.6809128, 115.198418)


def test_pin_extracted_from_both_madam_lee_urls():
    assert _extract_place_pin_coordinates(MADAM_LEE_EXPANDED_ZOOMED_OUT) == PIN
    assert _extract_place_pin_coordinates(MADAM_LEE_EXPANDED_ZOOMED_IN) == PIN


def test_viewport_differs_from_pin_when_zoomed_out():
    assert _extract_viewport_coordinates(MADAM_LEE_EXPANDED_ZOOMED_OUT) == VIEWPORT_FAR
    assert _extract_viewport_coordinates(MADAM_LEE_EXPANDED_ZOOMED_IN) == VIEWPORT_NEAR


def test_combined_extractor_prefers_pin_over_viewport():
    assert _extract_coordinates_from_maps_url(MADAM_LEE_EXPANDED_ZOOMED_OUT) == PIN
    assert _extract_coordinates_from_maps_url(MADAM_LEE_EXPANDED_ZOOMED_IN) == PIN


def test_map_only_link_uses_viewport():
    url = "https://www.google.com/maps/@-8.6788385,115.1783469,14759m"
    assert _extract_place_pin_coordinates(url) is None
    assert _extract_coordinates_from_maps_url(url) == VIEWPORT_FAR


def test_query_lat_lng_still_works():
    url = "https://maps.google.com/maps?q=-8.65,115.14"
    assert _extract_coordinates_from_maps_url(url) is None  # handled earlier in parse_google_maps_link
