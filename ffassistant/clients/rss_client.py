import requests

USER_AGENT = "ffassistant/0.1"
TIMEOUT_SECONDS = 20


def fetch_feed(url: str) -> bytes:
    response = requests.get(
        url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS
    )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}")
    return response.content
