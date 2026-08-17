import html
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By


# ==========================================================
# CONFIGURATION
# ==========================================================

ROYA_TV_PAGE = (
    "https://roya.tv/live-stream/1"
)

ROYA_NEWS_PAGE = (
    "https://roya.tv/live-stream/21"
)

ALMAMLAKA_PAGE = (
    "https://www.almamlakatv.com/live-video"
)


# ==========================================================
# LOGGING
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    ),
)


# ==========================================================
# CREATE CHROME
# ==========================================================

def create_driver():
    options = Options()

    options.add_argument(
        "--headless=new"
    )

    options.add_argument(
        "--no-sandbox"
    )

    options.add_argument(
        "--disable-dev-shm-usage"
    )

    options.add_argument(
        "--disable-gpu"
    )

    options.add_argument(
        "--window-size=1920,1080"
    )

    options.add_argument(
        "--autoplay-policy="
        "no-user-gesture-required"
    )

    options.add_argument(
        "--mute-audio"
    )

    options.set_capability(
        "goog:loggingPrefs",
        {
            "performance": "ALL"
        },
    )

    chrome_binary = os.environ.get(
        "CHROME_BINARY"
    )

    if chrome_binary:
        options.binary_location = (
            chrome_binary
        )

    chromedriver_path = os.environ.get(
        "CHROMEDRIVER_PATH"
    )

    if chromedriver_path:
        service = Service(
            chromedriver_path
        )
    else:
        service = Service()

    driver = webdriver.Chrome(
        service=service,
        options=options,
    )

    driver.set_page_load_timeout(
        60
    )

    try:
        driver.execute_cdp_cmd(
            "Network.enable",
            {},
        )
    except Exception:
        pass

    return driver


# ==========================================================
# URL HELPERS
# ==========================================================

def deep_unquote(value):
    value = html.unescape(
        value
    )

    for _ in range(4):
        decoded = urllib.parse.unquote(
            value
        )

        if decoded == value:
            break

        value = decoded

    return value


def safe_url_for_log(url):
    """
    Hide tokens from public GitHub logs.
    """

    try:
        parsed = urllib.parse.urlsplit(
            url
        )

        filename = (
            parsed.path
            .rstrip("/")
            .split("/")[-1]
        )

        if not filename:
            filename = "stream"

        return (
            f"{parsed.scheme}://"
            f"{parsed.hostname}"
            f"/.../{filename}"
            + (
                "?<token-hidden>"
                if parsed.query
                else ""
            )
        )

    except Exception:
        return "<hidden URL>"


# ==========================================================
# PERFORMANCE NETWORK LOG
# ==========================================================

def read_network_urls(driver):
    urls = []

    try:
        logs = driver.get_log(
            "performance"
        )
    except Exception:
        return urls

    for entry in logs:
        try:
            message = json.loads(
                entry["message"]
            )["message"]
        except Exception:
            continue

        method = message.get(
            "method",
            ""
        )

        url = ""

        if (
            method
            == "Network.requestWillBeSent"
        ):
            url = (
                message
                .get("params", {})
                .get("request", {})
                .get("url", "")
            )

        elif (
            method
            == "Network.responseReceived"
        ):
            url = (
                message
                .get("params", {})
                .get("response", {})
                .get("url", "")
            )

        if url:
            urls.append(url)

    return urls


# ==========================================================
# JAVASCRIPT RESOURCE LIST
# ==========================================================

def get_resource_urls(driver):
    try:
        resources = driver.execute_script(
            """
            return performance
                .getEntriesByType('resource')
                .map(x => x.name);
            """
        )

        if isinstance(
            resources,
            list,
        ):
            return resources

    except Exception:
        pass

    return []


# ==========================================================
# FIND URLS INSIDE PAGE SOURCE
# ==========================================================

def urls_from_page_source(driver):
    try:
        source = (
            driver.page_source
            .replace("\\/", "/")
        )
    except Exception:
        return []

    matches = re.findall(
        r'https?://[^\s"\'<>\\]+',
        source,
        flags=re.IGNORECASE,
    )

    return [
        html.unescape(
            match.rstrip(
                ")]},;"
            )
        )
        for match in matches
    ]


# ==========================================================
# TRY TO START VIDEO
# ==========================================================

def play_current_context(driver):
    try:
        driver.execute_script(
            """
            document
                .querySelectorAll('video')
                .forEach(v => {
                    try {
                        v.muted = true;
                        v.autoplay = true;

                        const result =
                            v.play();

                        if (
                            result &&
                            result.catch
                        ) {
                            result.catch(
                                () => {}
                            );
                        }

                    } catch (e) {}
                });


            try {
                if (
                    window.videojs &&
                    typeof window.videojs
                        .getPlayers
                        === 'function'
                ) {
                    const players =
                        window.videojs
                            .getPlayers();

                    Object
                        .values(players)
                        .forEach(p => {
                            try {
                                p.muted(true);
                                p.play();
                            } catch (e) {}
                        });
                }
            } catch (e) {}
            """
        )

    except Exception:
        pass

    selectors = [
        ".vjs-big-play-button",
        ".vjs-play-control",
        ".jw-icon-playback",
        ".plyr__control--overlaid",
        '[aria-label="Play"]',
        '[aria-label="play"]',
    ]

    for selector in selectors:
        try:
            elements = (
                driver.find_elements(
                    By.CSS_SELECTOR,
                    selector,
                )
            )

            for element in elements[:5]:
                try:
                    driver.execute_script(
                        "arguments[0].click();",
                        element,
                    )
                except Exception:
                    pass

        except Exception:
            pass


def try_start_playback(
    driver,
):
    """
    Start video in main page and
    top-level iframes.
    """

    try:
        driver.switch_to.default_content()
    except Exception:
        pass

    play_current_context(
        driver
    )

    try:
        driver.switch_to.default_content()

        frames = driver.find_elements(
            By.TAG_NAME,
            "iframe",
        )

        frame_count = len(
            frames
        )

    except Exception:
        frame_count = 0

    for index in range(
        frame_count
    ):
        try:
            driver.switch_to.default_content()

            frames = driver.find_elements(
                By.TAG_NAME,
                "iframe",
            )

            if index >= len(frames):
                continue

            driver.switch_to.frame(
                frames[index]
            )

            play_current_context(
                driver
            )

        except Exception:
            pass

    try:
        driver.switch_to.default_content()
    except Exception:
        pass


# ==========================================================
# ROYA SCORING
# ==========================================================

def score_roya(
    url,
    want_news=False,
):
    decoded = deep_unquote(
        url
    )

    lower = decoded.lower()

    if ".m3u8" not in lower:
        return -1

    if (
        "kwikmotion.com"
        not in lower
    ):
        return -1

    # IMPORTANT:
    # Do NOT save the child chunks
    # playlist we tested.
    if "chunks.m3u8" in lower:
        return -1

    score = 100

    if (
        "live.kwikmotion.com"
        in lower
    ):
        score += 80

    if (
        "playlist.m3u8"
        in lower
    ):
        score += 120

    if "hdnts=" in lower:
        score += 80

    if "roya" in lower:
        score += 20

    if want_news:
        if "news" in lower:
            score += 60

    else:
        if "news" in lower:
            score -= 100
        else:
            score += 20

    return score


# ==========================================================
# AL MAMLAKA HELPERS
# ==========================================================

def expand_mamlaka_url(
    url,
):
    """
    Brightcove sometimes reports the
    real HLS URL inside metrics URLs as
    media_url=...
    """

    results = []

    try:
        parsed = urllib.parse.urlsplit(
            url
        )

        query = urllib.parse.parse_qs(
            parsed.query
        )

        for key in [
            "media_url",
            "mediaUrl",
        ]:
            for value in query.get(
                key,
                [],
            ):
                value = deep_unquote(
                    value
                )

                if value.startswith(
                    (
                        "https://",
                        "http://",
                    )
                ):
                    results.append(
                        value
                    )

    except Exception:
        pass

    return results


def score_mamlaka(
    url,
):
    decoded = deep_unquote(
        url
    )

    lower = decoded.lower()

    if ".m3u8" not in lower:
        return -1

    if (
        "brightcove.com"
        not in lower
    ):
        return -1

    score = 100

    if (
        "fastly.live.brightcove.com"
        in lower
    ):
        score += 120

    if (
        "playlist-hls-dvr.m3u8"
        in lower
    ):
        score += 200

    elif (
        "playlist-hls"
        in lower
    ):
        score += 150

    elif (
        "master"
        in lower
    ):
        score += 80

    return score


# ==========================================================
# GENERIC PAGE SCANNER
# ==========================================================

def scan_stream(
    page_url,
    channel_name,
    scorer,
    timeout_seconds=70,
    early_score=300,
    expander=None,
):
    logging.info(
        "===================================="
    )

    logging.info(
        "Scanning %s",
        channel_name,
    )

    logging.info(
        "Page: %s",
        page_url,
    )

    driver = create_driver()

    best_url = None
    best_score = -1

    seen = set()

    try:
        try:
            driver.get(
                page_url
            )

        except TimeoutException:
            logging.warning(
                "%s page load timed out, "
                "continuing anyway.",
                channel_name,
            )

        time.sleep(5)

        for second in range(
            timeout_seconds
        ):
            if (
                second % 5 == 0
            ):
                try_start_playback(
                    driver
                )

            candidates = []

            candidates.extend(
                read_network_urls(
                    driver
                )
            )

            if (
                second % 5 == 0
            ):
                candidates.extend(
                    get_resource_urls(
                        driver
                    )
                )

            if (
                second % 10 == 0
            ):
                candidates.extend(
                    urls_from_page_source(
                        driver
                    )
                )

            expanded = []

            for candidate in candidates:
                if (
                    candidate
                    in seen
                ):
                    continue

                seen.add(
                    candidate
                )

                expanded.append(
                    candidate
                )

                if expander:
                    for extra in expander(
                        candidate
                    ):
                        expanded.append(
                            extra
                        )

            for candidate in expanded:
                try:
                    score = scorer(
                        candidate
                    )
                except Exception:
                    continue

                if (
                    score
                    > best_score
                ):
                    best_score = (
                        score
                    )

                    best_url = (
                        candidate
                    )

                    if score >= 0:
                        logging.info(
                            "%s candidate found: "
                            "%s "
                            "(score=%d)",
                            channel_name,
                            safe_url_for_log(
                                candidate
                            ),
                            score,
                        )

            if (
                second >= 10
                and
                best_url
                and
                best_score
                >= early_score
            ):
                break

            time.sleep(1)

    finally:
        driver.quit()

    if (
        best_url is None
        or
        best_score < 0
    ):
        logging.error(
            "%s: no usable stream found.",
            channel_name,
        )

        return None

    logging.info(
        "%s: selected %s",
        channel_name,
        safe_url_for_log(
            best_url
        ),
    )

    return best_url


# ==========================================================
# ROYA TV
# ==========================================================

def scan_roya_tv():
    return scan_stream(
        page_url=ROYA_TV_PAGE,

        channel_name="Roya TV",

        scorer=lambda url:
            score_roya(
                url,
                want_news=False,
            ),

        timeout_seconds=70,

        early_score=300,
    )


# ==========================================================
# ROYA NEWS
# ==========================================================

def scan_roya_news():
    return scan_stream(
        page_url=ROYA_NEWS_PAGE,

        channel_name="Roya News",

        scorer=lambda url:
            score_roya(
                url,
                want_news=True,
            ),

        timeout_seconds=70,

        early_score=300,
    )


# ==========================================================
# AL MAMLAKA
# ==========================================================

def scan_almamlaka():
    return scan_stream(
        page_url=ALMAMLAKA_PAGE,

        channel_name="Al Mamlaka TV",

        scorer=score_mamlaka,

        timeout_seconds=90,

        early_score=350,

        expander=expand_mamlaka_url,
    )


# ==========================================================
# SEND STREAMS TO CLOUDFLARE
# ==========================================================

def push_to_worker(
    streams,
):
    update_url = os.environ.get(
        "WORKER_UPDATE_URL",
        "",
    ).strip()

    update_secret = os.environ.get(
        "WORKER_UPDATE_SECRET",
        "",
    ).strip()

    if not update_url:
        raise RuntimeError(
            "WORKER_UPDATE_URL is missing."
        )

    if not update_secret:
        raise RuntimeError(
            "WORKER_UPDATE_SECRET is missing."
        )

    payload = json.dumps(
        streams
    ).encode(
        "utf-8"
    )

    request = urllib.request.Request(
        update_url,

        data=payload,

        method="POST",

        headers={
            "Content-Type":
                "application/json",

            "Authorization":
                (
                    "Bearer "
                    + update_secret
                ),

            "User-Agent":
                (
                    "jordan-tv-"
                    "github-updater/1.0"
                ),
        },
    )

    logging.info(
        "Sending %d fresh stream(s) "
        "to Worker...",
        len(streams),
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:
            body = (
                response
                .read()
                .decode(
                    "utf-8",
                    errors="replace",
                )
            )

            status = (
                response.status
            )

    except urllib.error.HTTPError as exc:
        body = (
            exc.read()
            .decode(
                "utf-8",
                errors="replace",
            )
        )

        raise RuntimeError(
            "Worker update failed "
            f"with HTTP {exc.code}: "
            f"{body}"
        ) from exc

    except Exception as exc:
        raise RuntimeError(
            "Unable to contact Worker: "
            f"{exc}"
        ) from exc

    if not (
        200
        <= status
        < 300
    ):
        raise RuntimeError(
            "Worker returned "
            f"HTTP {status}: "
            f"{body}"
        )

    logging.info(
        "Worker accepted update."
    )

    logging.info(
        "Worker response: %s",
        body,
    )


# ==========================================================
# MAIN
# ==========================================================

def main():
    streams = {}

    # --------------------------
    # ROYA TV
    # --------------------------

    try:
        roya_tv = (
            scan_roya_tv()
        )

        if roya_tv:
            streams[
                "roya_tv"
            ] = roya_tv

    except Exception:
        logging.exception(
            "Roya TV scan failed."
        )


    # --------------------------
    # ROYA NEWS
    # --------------------------

    try:
        roya_news = (
            scan_roya_news()
        )

        if roya_news:
            streams[
                "roya_news"
            ] = roya_news

    except Exception:
        logging.exception(
            "Roya News scan failed."
        )


    # --------------------------
    # AL MAMLAKA
    # --------------------------

    try:
        almamlaka = (
            scan_almamlaka()
        )

        if almamlaka:
            streams[
                "almamlaka"
            ] = almamlaka

    except Exception:
        logging.exception(
            "Al Mamlaka scan failed."
        )


    # --------------------------
    # NOTHING FOUND
    # --------------------------

    if not streams:
        raise RuntimeError(
            "No fresh streams were found. "
            "Worker was NOT changed."
        )


    # --------------------------
    # IMPORTANT:
    #
    # Only successful scans are
    # sent.
    #
    # If one channel fails,
    # its existing Worker value
    # remains untouched.
    # --------------------------

    push_to_worker(
        streams
    )

    logging.info(
        "===================================="
    )

    logging.info(
        "Finished."
    )

    logging.info(
        "Updated Worker keys: %s",
        ", ".join(
            streams.keys()
        ),
    )

    if len(streams) < 3:
        logging.warning(
            "Only %d of 3 streams were "
            "freshly updated. "
            "Existing Worker targets for "
            "failed channels were preserved.",
            len(streams),
        )


if __name__ == "__main__":
    main()
