"""Tests voor geocoding: cache, geen-resultaat en netwerkfouten — zonder netwerk."""

from pathlib import Path
from unittest import mock

import pytest
import requests

import geocoding
import main as app_main
from rss_feed import parse_feed

FIXTURE = Path(__file__).parent / "fixtures" / "feed_sample.xml"


@pytest.fixture(autouse=True)
def reset_geocoding_state():
    geocoding._cache.clear()
    geocoding._last_lookup = 0
    yield
    geocoding._cache.clear()
    geocoding._last_lookup = 0


def _response(payload):
    response = mock.Mock()
    response.json.return_value = payload
    return response


def test_geocode_returns_none_without_results():
    with mock.patch("geocoding.requests.get", return_value=_response([])):
        assert geocoding.geocode("Onbekende Straat, Katwijk", "test/1.0") is None


def test_geocode_caches_successful_lookups():
    payload = [{"lat": "52.2011", "lon": "4.3997", "display_name": "Prins Hendrikkade"}]
    with mock.patch("geocoding.requests.get", return_value=_response(payload)) as get:
        first = geocoding.geocode("Prins Hendrikkade, Katwijk, Nederland", "test/1.0")
        # Zelfde locatie, andere witruimte/hoofdletters: cache-hit, geen request.
        second = geocoding.geocode("prins hendrikkade,  katwijk, nederland", "test/1.0")

    assert first == second == {
        "lat": 52.2011,
        "lon": 4.3997,
        "display_name": "Prins Hendrikkade",
    }
    assert get.call_count == 1


def test_geocode_cache_is_bounded():
    payload = [{"lat": "52.0", "lon": "4.0", "display_name": "x"}]
    # time.sleep gemockt: anders wacht de Nominatim-ratelimiter ~1,1 s per
    # (gemockte) request en duurt deze test minuten.
    with mock.patch("geocoding.requests.get", return_value=_response(payload)), mock.patch(
        "geocoding.time.sleep"
    ):
        for n in range(geocoding._CACHE_MAX + 10):
            geocoding.geocode(f"straat {n}", "test/1.0")
    assert len(geocoding._cache) == geocoding._CACHE_MAX


def _enrich_config():
    from tests.test_process import make_config

    return make_config(geocoding_enabled=True, home_lat=52.2, home_lon=4.4)


def test_enrich_alert_sets_distance():
    alert = parse_feed(FIXTURE.read_bytes(), limit=1, location_name="Katwijk")[0]
    payload = [{"lat": "52.2011", "lon": "4.3997", "display_name": "Prins Hendrikkade"}]
    with mock.patch("geocoding.requests.get", return_value=_response(payload)):
        enriched = app_main.enrich_alert(alert, _enrich_config())

    assert enriched.lat == 52.2011
    assert enriched.lon == 4.3997
    assert enriched.afstand_km is not None


def test_enrich_alert_survives_network_error():
    alert = parse_feed(FIXTURE.read_bytes(), limit=1, location_name="Katwijk")[0]
    with mock.patch(
        "geocoding.requests.get", side_effect=requests.ConnectionError("offline")
    ):
        enriched = app_main.enrich_alert(alert, _enrich_config())

    # Melding blijft bruikbaar, alleen zonder coördinaten.
    assert enriched.lat is None
    assert enriched.afstand_km is None
    assert enriched.titel
