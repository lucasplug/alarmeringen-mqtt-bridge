from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
import hashlib
import re


LOCAL_TIMEZONE = ZoneInfo("Europe/Amsterdam")
UTC_TIMEZONE = ZoneInfo("UTC")


def parse_local_time(value: str) -> str:
    """
    Zet een RSS-datum om naar lokale tijd in Europe/Amsterdam.

    Voorbeeld:
    Fri, 10 Jul 2026 10:39:00 +0000
    wordt:
    2026-07-10T12:39:00+02:00
    """
    if not value:
        return ""

    try:
        dt = parsedate_to_datetime(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC_TIMEZONE)

        return dt.astimezone(LOCAL_TIMEZONE).isoformat(timespec="seconds")

    except (TypeError, ValueError, OverflowError):
        # Laat de originele waarde staan als het formaat onbekend is.
        return value


@dataclass
class Alert:
    id: str
    titel: str
    omschrijving: str
    link: str
    tijd: str

    dienst: str = ""
    prioriteit: str = ""
    locatie: str = ""
    plaats: str = ""

    lat: float | None = None
    lon: float | None = None
    afstand_km: float | None = None

    @classmethod
    def from_entry(cls, entry, location_name: str):
        titel = entry.get("title", "").strip()
        omschrijving = entry.get("summary", "").strip()
        link = entry.get("link", "").strip()

        # feedparser normaliseert RSS 'pubDate' al naar 'published', dus
        # een aparte pubDate-fallback is niet nodig.
        raw_time = entry.get("published", "") or entry.get("updated", "")
        tijd = parse_local_time(raw_time)

        raw_id = (
            f"{entry.get('id', '')}-"
            f"{titel}-"
            f"{raw_time}-"
            f"{link}"
        )
        alert_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()

        return cls(
            id=alert_id,
            titel=titel,
            omschrijving=omschrijving,
            link=link,
            tijd=tijd,
            dienst=detect_dienst(titel, omschrijving),
            prioriteit=detect_prioriteit(titel),
            locatie=extract_locatie(titel, omschrijving, location_name),
            plaats=location_name,
        )

    def to_dict(self):
        return asdict(self)


def detect_prioriteit(text: str) -> str:
    """
    Herkent onder andere A1, A2, B1, B2, P1, P2 en 'prio 1/2'.
    """
    match = re.search(
        r"\b(a1|a2|b1|b2|prio\s*1|prio\s*2|p1|p2)\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return ""

    value = match.group(1).upper()
    value = re.sub(r"\s+", " ", value)

    if value == "PRIO 1":
        return "P1"

    if value == "PRIO 2":
        return "P2"

    return value


def detect_dienst(titel: str, omschrijving: str) -> str:
    """
    Probeert de hulpdienst te bepalen op basis van titel en omschrijving.
    Ambulance wordt eerst gecontroleerd, omdat A1/A2/B1/B2 daar sterk op wijzen.

    Let op: 2-letterige voertuigafkortingen (TS, HV) zijn een zwak signaal
    en kunnen theoretisch samenvallen met losse woorden in de tekst. 'AL'
    (Autoladder) is bewust NIET als kale afkorting opgenomen, omdat "al"
    een van de meest voorkomende Nederlandse woorden is en dat structureel
    valse positieven voor brandweer zou opleveren.
    """
    text = f"{titel} {omschrijving}".lower()

    if (
        "ambulance" in text
        or re.search(r"\ba1\b", text)
        or re.search(r"\ba2\b", text)
        or re.search(r"\bb1\b", text)
        or re.search(r"\bb2\b", text)
    ):
        return "ambulance"

    if (
        "brandweer" in text
        or "tankautospuit" in text
        or "autoladder" in text
        or re.search(r"\bts\b", text)
        or re.search(r"\bhv\b", text)
        or "hoogwerker" in text
        or "ovd-b" in text
        or "prio 1" in text
        or "prio 2" in text
    ):
        return "brandweer"

    if (
        "politie" in text
        or "ovd-p" in text
    ):
        return "politie"

    return ""


def extract_locatie(titel: str, omschrijving: str, location_name: str) -> str:
    """
    Probeert de locatie te herkennen, met de meest betrouwbare signalen eerst:
    1. Een provinciaal wegnummer (N-weg), ongeacht of dat in titel of
       omschrijving staat.
    2. Een expliciete "naar/op/aan ... in <plaats>"-zin in de omschrijving.
    3. Een straatnaam-achtig patroon in de titel, als laatste redmiddel.
    """
    combined = f"{titel} {omschrijving}"

    road_match = re.search(r"\b([Nn]\d{3})\b", combined)
    if road_match:
        return clean_location(road_match.group(1))

    place = re.escape(location_name)
    description_patterns = [
        rf"naar\s+(.+?)\s+in\s+{place}\b",
        rf"op\s+(.+?)\s+in\s+{place}\b",
        rf"aan\s+(.+?)\s+in\s+{place}\b",
    ]

    for pattern in description_patterns:
        match = re.search(pattern, omschrijving, re.IGNORECASE)

        if match:
            return clean_location(match.group(1))

    # Vereist een hoofdletter aan het begin van (max.) elk van de twee
    # woorden, om te voorkomen dat de match over de hele titel heen
    # doorloopt tot de laatst voorkomende straat-suffix (was eerder een
    # greedy-match bug). De suffix zelf is case-insensitive via (?i:...).
    street_pattern = (
        r"\b([A-ZÀ-Ý][A-Za-zÀ-ÿ'’-]*"
        r"(?:\s[A-ZÀ-Ý][A-Za-zÀ-ÿ'’-]*)?"
        r"(?i:weg|straat|laan|singel|plein|dijk|pad|kade|boulevard))\b"
    )
    match = re.search(street_pattern, titel)

    if match:
        return clean_location(match.group(1))

    return ""


def clean_location(value: str) -> str:
    """Ruimt extra witruimte en generieke P2000-resttekst op."""
    location = re.sub(r"\s+", " ", value).strip(" ,:-")

    location = re.sub(
        r"\s+(?:directe inzet|:?\s*\d{4,6})$",
        "",
        location,
        flags=re.IGNORECASE,
    )

    return location.strip(" ,:-")
