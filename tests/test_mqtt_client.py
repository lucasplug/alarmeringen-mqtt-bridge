"""Tests voor MqttPublisher zonder echte broker (paho-client gemockt)."""

from unittest import mock

import mqtt_client


def make_publisher(connected=True):
    with mock.patch("mqtt_client.mqtt.Client") as client_cls:
        client = client_cls.return_value
        client.is_connected.return_value = connected
        publisher = mqtt_client.MqttPublisher("broker", 1883, "", "", "p2000/")
    return publisher, client


def test_publish_skipped_when_not_connected():
    publisher, client = make_publisher(connected=False)

    assert publisher.publish_json("melding", {"a": 1}) is False
    # Niet in paho's eigen wachtrij gezet.
    client.publish.assert_not_called()


def test_publish_error_returns_false_instead_of_raising():
    publisher, client = make_publisher()
    client.publish.return_value.wait_for_publish.side_effect = RuntimeError("no conn")

    assert publisher.publish_json("melding", {"a": 1}) is False


def test_publish_confirmed():
    publisher, client = make_publisher()
    client.publish.return_value.is_published.return_value = True

    assert publisher.publish_json("laatste", {"a": 1}, retain=True) is True
    client.publish.assert_called_once_with(
        "p2000/laatste", '{"a": 1}', qos=1, retain=True
    )
