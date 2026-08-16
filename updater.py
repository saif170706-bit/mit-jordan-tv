import json
import logging
import os
import time
from urllib.parse import parse_qs, urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By


# ============================================================
# SETTINGS
# ============================================================

PLAYLIST_PATH = "playlist.m3u"

ROYA_TV_PAGE = "https://roya.tv/live-stream/1"
ROYA_NEWS_PAGE = "https://roya.tv/live-stream/21"
MAMLAKA_PAGE = "https://www.almamlakatv.com/live-video"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# ============================================================
# CREATE CHROME DRIVER
# ============================================================

def create_driver():

    options = Options()

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--autoplay-policy=no-user-gesture-required")
    options.add_argument("--mute-audio")

    options.set_capability(
        "goog:loggingPrefs",
        {"performance": "ALL"}
    )

    chrome_binary = os.environ.get("CHROME_BINARY")

    if chrome_binary and os.path.exists(chrome_binary):
        options.binary_location = chrome_binary

    chromedriver_path = os.environ.get(
        "CHROMEDRIVER_PATH"
    )

    if (
        chromedriver_path
        and os.path.exists(chromedriver_path)
    ):
        service = Service(chromedriver_path)
    else:
        service = Service()

    driver = webdriver.Chrome(
        service=service,
        options=options
    )

    driver.set_page_load_timeout(60)

    try:
        driver.execute_cdp_cmd(
            "Network.enable",
            {}
        )
    except Exception:
        pass

    return driver


# ============================================================
# READ NETWORK URLS
# ============================================================

def network_urls_from_logs(logs):

    urls = []

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

        method = message.get("method")

        if method == "Network.requestWillBeSent":

            url = (
                message
                .get("params", {})
                .get("request", {})
                .get("url", "")
            )

            if url:
                urls.append(url)

        elif method == "Network.responseReceived":

            response = (
                message
                .get("params", {})
                .get("response", {})
            )

            url = response.get("url", "")
            status = response.get("status", 0)

            if (
                url
                and (
                    not status
                    or 200 <= status < 400
                )
            ):
                urls.append(url)

    return urls


# ============================================================
# BRIGHTCOVE media_url BACKUP
# ============================================================

def brightcove_media_urls(url):

    if "metrics.brightcove.com" not in url.lower():
        return []

    try:

        query = parse_qs(
            urlparse(url).query
        )

        return query.get(
            "media_url",
            []
        )

    except Exception:
        return []


# ============================================================
# TRY TO START VIDEO
# ============================================================

def start_video_in_current_frame(driver):

    selectors = [
        ".vjs-big-play-button",
        ".vjs-play-control"
    ]

    for selector in selectors:

        try:

            buttons = driver.find_elements(
                By.CSS_SELECTOR,
                selector
            )

            for button in buttons:

                try:
                    driver.execute_script(
                        "arguments[0].click();",
                        button
                    )
                except Exception:
                    pass

        except Exception:
            pass

    # Native HTML5 video
    try:

        driver.execute_script(
            """
            document.querySelectorAll('video').forEach((v) => {
                try {
                    v.muted = true;
                    v.autoplay = true;

                    const promise = v.play();

                    if (promise && promise.catch) {
                        promise.catch(() => {});
                    }

                } catch (e) {}
            });
            """
        )

    except Exception:
        pass

    # Video.js
    try:

        driver.execute_script(
            """
            try {
                if (window.videojs && videojs.getPlayers) {

                    const players = videojs.getPlayers();

                    Object.keys(players).forEach((key) => {

                        try {
                            const player = players[key];

                            player.muted(true);
                            player.play();

                        } catch (e) {}
                    });
                }
            } catch (e) {}
            """
        )

    except Exception:
        pass


# ============================================================
# ACTIVELY START AL MAMLAKA BRIGHTCOVE
# ============================================================

def actively_start_brightcove(driver):

    driver.switch_to.default_content()

    start_video_in_current_frame(driver)

    try:

        iframes = driver.find_elements(
            By.TAG_NAME,
            "iframe"
        )

    except Exception:
        iframes = []

    logging.info(
        "Al Mamlaka: found %d iframe(s).",
        len(iframes)
    )

    for index in range(len(iframes)):

        try:

            driver.switch_to.default_content()

            current_iframes = driver.find_elements(
                By.TAG_NAME,
                "iframe"
            )

            if index >= len(current_iframes):
                continue

            frame = current_iframes[index]

            src = (
                frame.get_attribute("src")
                or ""
            )

            logging.info(
                "Al Mamlaka: trying iframe %d: %s",
                index + 1,
                src[:180]
            )

            driver.switch_to.frame(frame)

            start_video_in_current_frame(
                driver
            )

        except Exception as exc:

            logging.info(
                "Could not start iframe %d: %s",
                index + 1,
                exc
            )

    driver.switch_to.default_content()


# ============================================================
# FIND AL MAMLAKA MASTER
# ============================================================

def find_mamlaka_master(logs):

    urls = network_urls_from_logs(logs)

    for url in urls:

        low = url.lower()

        # Direct Brightcove master request
        if (
            "fastly.live.brightcove.com" in low
            and
            "playlist-hls-dvr.m3u8" in low
        ):

            logging.info(
                "AL MAMLAKA MASTER DIRECTLY FOUND:"
            )

            logging.info(url)

            return url

        # Backup: media_url inside Brightcove metrics
        for media_url in brightcove_media_urls(url):

            media_low = media_url.lower()

            if (
                "fastly.live.brightcove.com"
                in media_low
                and
                "playlist-hls-dvr.m3u8"
                in media_low
            ):

                logging.info(
                    "AL MAMLAKA MASTER FOUND IN media_url=:"
                )

                logging.info(media_url)

                return media_url

    return None


# ============================================================
# SCAN AL MAMLAKA
# ============================================================

def sniff_almamlaka(timeout_seconds=45):

    driver = None

    try:

        driver = create_driver()

        logging.info(
            "================================"
        )

        logging.info(
            "OPENING AL MAMLAKA:"
        )

        logging.info(MAMLAKA_PAGE)

        driver.get(MAMLAKA_PAGE)

        time.sleep(5)

        # First check
        found = find_mamlaka_master(
            driver.get_log("performance")
        )

        if found:
            return found

        logging.info(
            "Al Mamlaka master not yet seen."
        )

        logging.info(
            "Actively starting Brightcove..."
        )

        actively_start_brightcove(driver)

        deadline = (
            time.time()
            + timeout_seconds
        )

        next_play_attempt = (
            time.time()
            + 8
        )

        while time.time() < deadline:

            time.sleep(1)

            logs = driver.get_log(
                "performance"
            )

            urls = network_urls_from_logs(
                logs
            )

            for url in urls:

                if ".m3u8" in url.lower():

                    logging.info(
                        "AL MAMLAKA M3U8 SEEN:"
                    )

                    logging.info(url)

            found = find_mamlaka_master(
                logs
            )

            if found:

                logging.info(
                    "SUCCESS: Al Mamlaka fresh master found."
                )

                return found

            if time.time() >= next_play_attempt:

                logging.info(
                    "Trying Brightcove playback again..."
                )

                actively_start_brightcove(
                    driver
                )

                next_play_attempt = (
                    time.time()
                    + 8
                )

        logging.warning(
            "Al Mamlaka: no fresh "
            "playlist-hls-dvr.m3u8 found."
        )

        return None

    except Exception:

        logging.exception(
            "Al Mamlaka scan failed."
        )

        return None

    finally:

        if driver is not None:
            driver.quit()


# ============================================================
# SCORE ROYA URLs
# ============================================================

def roya_score(url):

    low = url.lower()

    if ".m3u8" not in low:
        return -10000

    score = 0

    if "playlist.m3u8" in low:
        score += 500

    if "master.m3u8" in low:
        score += 450

    if "index.m3u8" in low:
        score += 300

    if "kwikmotion" in low:
        score += 150

    if "akamaized" in low:
        score += 100

    if "daioncdn" in low:
        score += 100

    if "chunklist" in low:
        score -= 500

    if "audio" in low:
        score -= 300

    return score


# ============================================================
# SCAN ROYA
# ============================================================

def sniff_roya(
    page_url,
    channel_name,
    timeout_seconds=35
):

    driver = None
    candidates = set()

    try:

        driver = create_driver()

        logging.info(
            "================================"
        )

        logging.info(
            "OPENING %s:",
            channel_name
        )

        logging.info(page_url)

        driver.get(page_url)

        time.sleep(3)

        start_video_in_current_frame(
            driver
        )

        deadline = (
            time.time()
            + timeout_seconds
        )

        while time.time() < deadline:

            time.sleep(1)

            logs = driver.get_log(
                "performance"
            )

            urls = network_urls_from_logs(
                logs
            )

            for url in urls:

                if ".m3u8" in url.lower():

                    candidates.add(url)

                    logging.info(
                        "%s M3U8 SEEN:",
                        channel_name
                    )

                    logging.info(url)

                for media_url in (
                    brightcove_media_urls(url)
                ):

                    if ".m3u8" in media_url.lower():

                        candidates.add(
                            media_url
                        )

            if candidates:

                best = max(
                    candidates,
                    key=roya_score
                )

                if roya_score(best) >= 300:

                    logging.info(
                        "%s MASTER SELECTED:",
                        channel_name
                    )

                    logging.info(best)

                    return best

        if candidates:

            best = max(
                candidates,
                key=roya_score
            )

            logging.info(
                "%s BEST CANDIDATE AFTER TIMEOUT:",
                channel_name
            )

            logging.info(best)

            return best

        logging.warning(
            "%s: no fresh M3U8 found.",
            channel_name
        )

        return None

    except Exception:

        logging.exception(
            "%s scan failed.",
            channel_name
        )

        return None

    finally:

        if driver is not None:
            driver.quit()


# ============================================================
# IDENTIFY ONLY OUR THREE DYNAMIC CHANNELS
#
# IMPORTANT:
#
# Your big playlist contains another channel also called
# "Roya TV".
#
# Therefore the real Roya TV is identified by:
#
#   tvg-name="Roya TV"
#   group-title="Jordan"
#
# This prevents the other Roya TV from being modified.
# ============================================================

def is_target_channel(
    extinf_line,
    channel_name
):

    if not extinf_line.startswith(
        "#EXTINF:"
    ):
        return False

    if channel_name == "Roya TV":

        return (
            'tvg-name="Roya TV"'
            in extinf_line
            and
            'group-title="Jordan"'
            in extinf_line
        )

    if channel_name == "Roya News":

        return (
            'tvg-name="Roya News"'
            in extinf_line
            and
            'group-title="Jordan"'
            in extinf_line
        )

    if channel_name == "Al Mamlaka TV":

        return (
            'tvg-name="Al Mamlaka TV"'
            in extinf_line
        )

    return False


# ============================================================
# REPLACE ONLY ONE CHANNEL URL
#
# EVERYTHING ELSE IN playlist.m3u REMAINS UNCHANGED
# ============================================================

def replace_channel_url(
    lines,
    channel_name,
    new_url
):

    for index, line in enumerate(lines):

        if not is_target_channel(
            line,
            channel_name
        ):
            continue

        # Find the URL belonging to this EXTINF entry
        for url_index in range(
            index + 1,
            min(index + 10, len(lines))
        ):

            candidate = (
                lines[url_index]
                .strip()
            )

            # Reached next channel without URL
            if candidate.startswith(
                "#EXTINF:"
            ):
                break

            if candidate.startswith(
                (
                    "https://",
                    "http://"
                )
            ):

                old_url = candidate

                if old_url == new_url:

                    logging.info(
                        "%s: URL is already current.",
                        channel_name
                    )

                    return True, False

                # Preserve existing line ending
                if lines[url_index].endswith(
                    "\r\n"
                ):
                    ending = "\r\n"

                elif lines[url_index].endswith(
                    "\n"
                ):
                    ending = "\n"

                else:
                    ending = ""

                lines[url_index] = (
                    new_url
                    + ending
                )

                logging.info(
                    "%s URL UPDATED.",
                    channel_name
                )

                logging.info(
                    "OLD: %s",
                    old_url
                )

                logging.info(
                    "NEW: %s",
                    new_url
                )

                return True, True

    logging.error(
        "%s entry was NOT found in playlist.",
        channel_name
    )

    return False, False


# ============================================================
# PATCH EXISTING BIG PLAYLIST
#
# This DOES NOT generate a new playlist.
#
# It edits only:
#
#   Roya TV
#   Roya News
#   Al Mamlaka TV
#
# If fresh scan fails:
#
#   old URL stays untouched
# ============================================================

def update_existing_playlist(
    fresh_streams,
    path=PLAYLIST_PATH
):

    if not os.path.exists(path):

        raise FileNotFoundError(
            f"{path} does not exist."
        )

    # newline="" preserves original line endings
    with open(
        path,
        "r",
        encoding="utf-8",
        newline=""
    ) as file:

        lines = file.readlines()

    changed_count = 0

    for channel_name in [
        "Roya TV",
        "Roya News",
        "Al Mamlaka TV"
    ]:

        fresh_url = fresh_streams.get(
            channel_name
        )

        if not fresh_url:

            logging.warning(
                "%s: fresh scan failed. "
                "LEAVING EXISTING PLAYLIST URL UNTOUCHED.",
                channel_name
            )

            continue

        found, changed = replace_channel_url(
            lines,
            channel_name,
            fresh_url
        )

        if not found:

            logging.error(
                "%s could not be patched.",
                channel_name
            )

        if changed:
            changed_count += 1

    # Write the full playlist back only if
    # at least one of the 3 URLs changed
    if changed_count > 0:

        with open(
            path,
            "w",
            encoding="utf-8",
            newline=""
        ) as file:

            file.writelines(lines)

        logging.info(
            "playlist.m3u saved."
        )

        logging.info(
            "%d dynamic channel URL(s) changed.",
            changed_count
        )

    else:

        logging.info(
            "No playlist changes needed."
        )

    return changed_count


# ============================================================
# MAIN
# ============================================================

def main():

    logging.info(
        "=============================================="
    )

    logging.info(
        "STARTING IPTV AUTO UPDATE"
    )

    logging.info(
        "STATIC CHANNELS WILL NOT BE MODIFIED"
    )

    logging.info(
        "=============================================="
    )

    # --------------------------------------------------------
    # 1. Get fresh Roya TV token
    # --------------------------------------------------------

    fresh_roya_tv = sniff_roya(
        ROYA_TV_PAGE,
        "Roya TV"
    )

    # --------------------------------------------------------
    # 2. Get fresh Roya News token
    # --------------------------------------------------------

    fresh_roya_news = sniff_roya(
        ROYA_NEWS_PAGE,
        "Roya News"
    )

    # --------------------------------------------------------
    # 3. Get fresh Al Mamlaka URL
    # --------------------------------------------------------

    fresh_mamlaka = sniff_almamlaka()

    fresh_streams = {

        "Roya TV":
            fresh_roya_tv,

        "Roya News":
            fresh_roya_news,

        "Al Mamlaka TV":
            fresh_mamlaka
    }

    # --------------------------------------------------------
    # Patch ONLY those three entries
    # --------------------------------------------------------

    update_existing_playlist(
        fresh_streams
    )

    logging.info(
        "=============================================="
    )

    logging.info(
        "UPDATE COMPLETE"
    )

    logging.info(
        "All other playlist channels were preserved."
    )

    logging.info(
        "=============================================="
    )


if __name__ == "__main__":
    main()
