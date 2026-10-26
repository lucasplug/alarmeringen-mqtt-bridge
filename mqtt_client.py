import json
import logging
import paho.mqtt.client as mqtt


class MqttPublisher:
    def __init__(self, host, port, user, password, topic_base):
        self.topic_base = topic_base.rstrip("/")
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

        if user:
            self.client.username_pw_set(user, password)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        # Automatisch herverbinden met backoff (1s -> 120s) als de
        # verbinding wegvalt.
        self.client.reconnect_delay_set(min_delay=1, max_delay=120)

        # connect_async (i.p.v. connect) zorgt dat de container niet
        # meteen crasht als de MQTT-broker bij het opstarten nog niet
        # bereikbaar is. Paho blijft dan op de achtergrond retryen
        # zodra loop_start() draait.
        self.client.connect_async(host, port, keepalive=60)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logging.info("Verbonden met MQTT broker")
        else:
            logging.warning("MQTT verbinding mislukt: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        logging.warning("MQTT verbinding verbroken: %s", reason_code)

    def publish_json(self, subtopic, payload, retain=False, qos=1) -> bool:
        """Publiceert en geeft True terug zodra de broker de publicatie heeft
        bevestigd. QoS 1 zorgt dat berichten die tijdens een korte
        verbindingsstoring gepubliceerd worden, door paho worden gequeued en
        bij reconnect alsnog worden afgeleverd."""
        topic = f"{self.topic_base}/{subtopic}"

        # Zonder verbinding niet publiceren: paho zou het bericht in zijn
        # eigen wachtrij zetten en bij reconnect alsnog versturen, terwijl de
        # volgende poll het opnieuw probeert. Dat gaf een groeiende wachtrij
        # en dubbele berichten na een langere storing.
        if not self.client.is_connected():
            logging.warning("Niet verbonden met MQTT; %s niet gepubliceerd", topic)
            return False

        message = json.dumps(payload, ensure_ascii=False)
        result = self.client.publish(topic, message, qos=qos, retain=retain)

        # Timeout voorkomt dat de poll-loop oneindig blijft hangen als de
        # broker langdurig onbereikbaar is. wait_for_publish gooit een
        # exception als de verbinding net tussendoor wegviel.
        try:
            result.wait_for_publish(timeout=10)
        except (RuntimeError, ValueError) as exc:
            logging.warning("Publiceren naar %s mislukt: %s", topic, exc)
            return False

        if result.is_published():
            logging.info("Gepubliceerd naar %s", topic)
            return True

        logging.warning("Publiceren naar %s (nog) niet bevestigd", topic)
        return False

    def close(self) -> None:
        """Netjes afsluiten: netwerkloop stoppen en verbinding verbreken."""
        self.client.loop_stop()
        self.client.disconnect()
