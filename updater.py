import time
import json
import logging
import os
import re

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# KUN de tre præcise live-sider
CHANNELS = {
    "Al Mamlaka TV": {
        "page": "https://www.almamlakatv.com/live-video",
        "prefer": ("brightcove", "playlist-hls-dvr.m3u8"),
    },

    "Roya TV": {
        "page": "https://roya.tv/live-stream/1",
        "prefer": ("roya", "kwikmotion", "playlist.m3u8"),
    },

    "Roya News": {
        "page": "https://roya.tv/live-stream/21",
        "prefer": ("roya", "kwikmotion", "playlist.m3u8"),
    },
}


def load_existing_playlist(path="playlist.m3u"):
    """
    Henter eksisterende m3u8-links fra playlist.m3u.
    Hvis en scanning fejler, beholder vi det gamle link
    i stedet for at indsætte brightcove.com/kwikmotion.com.
    """

    streams = {}

    if not os.path.exists(path):
        return streams

    current_channel = None

    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:

            line = raw_line.strip()

            if line.startswith("#EXTINF:"):
                if "," in line:
                    current_channel = line.split(",", 1)[1].strip()

            elif current_channel and line.startswith(("http://", "https://")):

                if ".m3u8" in line:
                    streams[current_channel] = line

                current_channel = None

    return streams


def score_m3u8(url, preferred_terms):
    """
    Giver master-playlists høj score og
    audio/chunklist-playlists lav score.
    """

    low = url.lower()

    if ".m3u8" not in low:
        return -10000

    score = 0

    # Al Mamlakas kendte master-format
    if "playlist-hls-dvr.m3u8" in low:
        score += 500

    # Generel master playlist
    if re.search(
        r"/playlist(?:[-_][^/?]+)?\.m3u8(?:[?#]|$)",
        low
    ):
        score += 350

    if "master.m3u8" in low:
        score += 300

    if "index.m3u8" in low:
        score += 150

    # Kanal-specifikke ting
    for term in preferred_terms:
        if term.lower() in low:
            score += 80

    # Undgå under-playlists
    if "chunklist" in low:
        score -= 500

    if "audio" in low:
        score -= 300

    if "media_" in low:
        score -= 150

    return score


def sniff_stream(page_url, preferred_terms, timeout_seconds=30):

    options = Options()

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    # Tillad at live-videoen starter uden klik
    options.add_argument(
        "--autoplay-policy=no-user-gesture-required"
    )

    # Aktiver Chrome performance/network logs
    options.set_capability(
        "goog:loggingPrefs",
        {"performance": "ALL"}
    )

    driver = None
    candidates = set()

    try:

        logging.info(
            "Åbner præcis live-side: %s",
            page_url
        )

        driver = webdriver.Chrome(options=options)

        # Aktiver netværks-events
        driver.execute_cdp_cmd(
            "Network.enable",
            {}
        )

        driver.get(page_url)

        deadline = time.time() + timeout_seconds

        while time.time() < deadline:

            time.sleep(2)

            logs = driver.get_log("performance")

            for entry in logs:

                try:
                    message = json.loads(
                        entry["message"]
                    )["message"]

                except (
                    KeyError,
                    TypeError,
                    json.JSONDecodeError
                ):
                    continue

                if message.get("method") != \
                        "Network.requestWillBeSent":
                    continue

                request = (
                    message
                    .get("params", {})
                    .get("request", {})
                )

                req_url = request.get("url", "")

                # Fang ALLE m3u8-links
                if ".m3u8" in req_url.lower():

                    candidates.add(req_url)

                    logging.info(
                        "M3U8 fundet: %s",
                        req_url
                    )

            # Find bedste kandidat
            if candidates:

                best = max(
                    candidates,
                    key=lambda url:
                    score_m3u8(
                        url,
                        preferred_terms
                    )
                )

                best_score = score_m3u8(
                    best,
                    preferred_terms
                )

                # God master-playlist fundet
                if best_score >= 300:

                    logging.info(
                        "MASTER PLAYLIST VALGT: %s",
                        best
                    )

                    return best

        # Hvis vi kun fandt mindre gode kandidater
        if candidates:

            best = max(
                candidates,
                key=lambda url:
                score_m3u8(
                    url,
                    preferred_terms
                )
            )

            logging.info(
                "Bedste kandidat efter timeout: %s",
                best
            )

            return best

        logging.warning(
            "Ingen m3u8 fundet på %s",
            page_url
        )

        return None

    except Exception:

        logging.exception(
            "Browser/sniffer fejlede for %s",
            page_url
        )

        return None

    finally:

        if driver is not None:
            driver.quit()


def main():

    logging.info(
        "Starter IPTV stream-opdatering..."
    )

    # Eksisterende gode links
    old_streams = load_existing_playlist()

    final_streams = {}

    for channel, config in CHANNELS.items():

        logging.info(
            "=============================="
        )

        logging.info(
            "Scanner: %s",
            channel
        )

        fresh_stream = sniff_stream(
            config["page"],
            config["prefer"]
        )

        if fresh_stream:

            final_streams[channel] = fresh_stream

            logging.info(
                "%s: frisk stream fundet.",
                channel
            )

        elif old_streams.get(channel):

            # VIGTIGT:
            # behold gammelt stream-link fremfor fake fallback
            final_streams[channel] = \
                old_streams[channel]

            logging.warning(
                "%s: scanning fejlede. "
                "Beholder tidligere m3u8.",
                channel
            )

        else:

            logging.error(
                "%s: intet stream-link tilgængeligt.",
                channel
            )

    # Lav ren M3U-fil
    lines = [
        "#EXTM3U",
        ""
    ]

    for channel in CHANNELS:

        if channel in final_streams:

            lines.extend([
                f"#EXTINF:-1,{channel}",
                final_streams[channel],
                ""
            ])

    with open(
        "playlist.m3u",
        "w",
        encoding="utf-8",
        newline="\n"
    ) as f:

        f.write(
            "\n".join(lines).rstrip()
            + "\n"
        )

    logging.info(
        "playlist.m3u opdateret med %d kanaler.",
        len(final_streams)
    )


if __name__ == "__main__":
    main()
