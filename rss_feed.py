import feedparser
import requests

from models import Alert

# (connect, read) timeouts: een traag of half-open antwoord van de feed mag
# de poll-loop nooit langdurig blokkeren.
REQUEST_TIMEOUT = (5, 15)


class FeedError(RuntimeError):
    """De feed is opgehaald maar niet als RSS te parsen."""


def parse_feed(content, limit, location_name):
    """Parst RSS-bytes naar Alerts. Netwerkloos, dus goed testbaar."""
    feed = feedparser.parse(content)

    if feed.bozo:
        raise FeedError(f"RSS-feed fout: {feed.bozo_exception}")

    return [Alert.from_entry(entry, location_name) for entry in feed.entries[:limit]]


def fetch_alerts(feed_url, limit, user_agent, location_name):
    """Haalt de feed zelf op (met expliciete timeout, User-Agent en
    statuscontrole) en geeft de inhoud aan feedparser. Netwerkfouten komen
    als requests.RequestException naar boven, parsefouten als FeedError,
    zodat de aanroeper ze gescheiden kan loggen."""
    response = requests.get(
        feed_url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": user_agent},
    )
    response.raise_for_status()

    return parse_feed(response.content, limit, location_name)
