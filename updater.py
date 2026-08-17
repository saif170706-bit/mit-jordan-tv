import json
import logging
import os
import time
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.common.exceptions import (
    JavascriptException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By


# ============================================================
# CONFIGURATION
# ============================================================

ROYA_TV_PAGE = "https://roya.tv/live-stream/1"
ROYA_NEWS_PAGE = "https://roya.tv/live-stream/21"
ALMAMLAKA_PAGE = "https://www.almamlakatv.com/live-video"


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    ),
)


# ============================================================
# URL HELPERS
# ============================================================

def deep_unquote(value):
    """
    Decode URL encoding a few times.

    Some players put stream URLs inside encoded
    parameters, so one urllib.parse.unquote()
    is not always enough.
    """

    if not value:
        return ""

    result = value

    for _ in range(4):
        decoded = urllib.parse.unquote(
            result
        )

        if decoded == result:
            break

        result = decoded

    return result


def safe_url_for_log(url):
    """
    Show enough information to identify a stream
    without printing long temporary tokens.
    """

    if not url:
        return "<none>"

    try:
        parsed = urllib.parse.urlsplit(
            url
        )

        path_parts = [
            part
            for part in parsed.path.split("/")
            if part
        ]

        if len(path_parts) > 2:
            visible_path = (
                "/.../"
                + path_parts[-1]
            )

        elif path_parts:
            visible_path = (
                "/"
                + "/".join(path_parts)
            )

        else:
            visible_path = "/"

        result = (
            f"{parsed.scheme}://"
            f"{parsed.netloc}"
            f"{visible_path}"
        )

        if parsed.query:
            result += "?<token-hidden>"

        return result

    except Exception:
        return "<stream-url-hidden>"


# ============================================================
# CHROME
# ============================================================

def create_driver():
    chrome_binary = os.environ.get(
        "CHROME_BINARY",
        "",
    ).strip()

    chromedriver_path = os.environ.get(
        "CHROMEDRIVER_PATH",
        "",
    ).strip()

    options = Options()

    if chrome_binary:
        options.binary_location = (
            chrome_binary
        )

    # --------------------------------------------------------
    # GitHub Actions / headless Chrome
    # --------------------------------------------------------

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
        "--disable-notifications"
    )

    options.add_argument(
        "--disable-popup-blocking"
    )

    # Important for video players.
    options.add_argument(
        "--autoplay-policy=no-user-gesture-required"
    )

    # Enable Chrome DevTools performance/network logging.
    options.set_capability(
        "goog:loggingPrefs",
        {
            "performance": "ALL",
        },
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
        45
    )

    # Explicitly enable Network domain.
    try:
        driver.execute_cdp_cmd(
            "Network.enable",
            {},
        )
    except Exception:
        pass

    return driver


# ============================================================
# NETWORK CAPTURE
# ============================================================

def read_network_entries(driver):
    """
    Read Chrome's REAL network traffic.

    This is the important part.

    It captures requests from:
    - the main page
    - iframes
    - Brightcove
    - video players
    - JavaScript/fetch/XHR

    Each call drains the current performance log.
    """

    entries = []

    try:
        logs = driver.get_log(
            "performance"
        )

    except Exception:
        return entries

    for log_entry in logs:

        try:
            outer = json.loads(
                log_entry["message"]
            )

            message = outer[
                "message"
            ]

        except Exception:
            continue

        method = message.get(
            "method",
            "",
        )

        params = message.get(
            "params",
            {},
        )


        # ====================================================
        # REQUEST
        # ====================================================

        if (
            method
            == "Network.requestWillBeSent"
        ):

            request = params.get(
                "request",
                {},
            )

            url = request.get(
                "url",
                "",
            )

            if url:
                entries.append(
                    {
                        "url": url,
                        "kind": "request",
                        "status": None,
                        "mime_type": "",
                    }
                )


        # ====================================================
        # RESPONSE
        # ====================================================

        elif (
            method
            == "Network.responseReceived"
        ):

            response = params.get(
                "response",
                {},
            )

            url = response.get(
                "url",
                "",
            )

            if url:
                entries.append(
                    {
                        "url": url,
                        "kind": "response",

                        "status":
                            response.get(
                                "status"
                            ),

                        "mime_type":
                            response.get(
                                "mimeType",
                                "",
                            ),
                    }
                )

    return entries


def read_network_urls(driver):
    """
    Compatibility helper used by the Roya scanner.
    """

    return [
        item["url"]
        for item
        in read_network_entries(driver)
        if item.get("url")
    ]


# ============================================================
# RESOURCE URLS
# ============================================================

def get_resource_urls(driver):
    """
    Secondary source of URLs from browser Performance API.
    """

    try:
        urls = driver.execute_script(
            """
            return performance
                .getEntriesByType('resource')
                .map(function(x) {
                    return x.name;
                });
            """
        )

        if isinstance(
            urls,
            list,
        ):
            return [
                str(x)
                for x in urls
                if x
            ]

    except Exception:
        pass

    return []


# ============================================================
# PLAY BUTTON / PLAYER CONTROL
# ============================================================

PLAY_SELECTORS = [
    "button.vjs-big-play-button",
    ".vjs-big-play-button",
    "button.vjs-play-control",
    ".vjs-play-control",
    "button[aria-label='Play']",
    "button[title='Play']",
    ".play-button",
    ".playButton",
]


def click_player_in_current_frame(
    driver,
):
    """
    Try several ways of actually starting the
    video in the currently selected document/frame.

    Returns number of playback actions attempted.
    """

    actions = 0


    # --------------------------------------------------------
    # 1. Click known play buttons
    # --------------------------------------------------------

    for selector in PLAY_SELECTORS:

        try:
            elements = (
                driver.find_elements(
                    By.CSS_SELECTOR,
                    selector,
                )
            )

        except Exception:
            continue

        for element in elements:

            try:
                if not element.is_displayed():
                    continue

                driver.execute_script(
                    """
                    arguments[0].click();
                    """,
                    element,
                )

                actions += 1

                logging.info(
                    "Player: clicked %s",
                    selector,
                )

            except Exception:
                continue


    # --------------------------------------------------------
    # 2. Directly tell HTML5 video elements to play
    # --------------------------------------------------------

    try:
        result = driver.execute_script(
            """
            const videos =
                Array.from(
                    document.querySelectorAll(
                        'video'
                    )
                );

            let attempted = 0;

            for (const video of videos) {

                try {
                    video.muted = true;

                    const result =
                        video.play();

                    if (
                        result &&
                        typeof result.catch
                        === 'function'
                    ) {
                        result.catch(
                            function() {}
                        );
                    }

                    attempted++;
                }
                catch (e) {
                }
            }

            return attempted;
            """
        )

        if result:
            actions += int(
                result
            )

            logging.info(
                "Player: play() called "
                "on %s video element(s).",
                result,
            )

    except Exception:
        pass


    # --------------------------------------------------------
    # 3. Click the visible video/player area
    #
    # Useful if a player has an overlay rather than
    # a normal <button>.
    # --------------------------------------------------------

    try:
        players = driver.find_elements(
            By.CSS_SELECTOR,
            (
                "video, "
                ".video-js, "
                ".vjs-tech"
            ),
        )

        for player in players:

            try:
                if not player.is_displayed():
                    continue

                driver.execute_script(
                    """
                    arguments[0].click();
                    """,
                    player,
                )

                actions += 1

            except Exception:
                pass

    except Exception:
        pass

    return actions


def play_in_frames_recursive(
    driver,
    depth=0,
    max_depth=3,
):
    """
    Search for the player both on the main page and
    inside iframes.

    This is especially important for Al Mamlaka because
    its video player is embedded in Brightcove.
    """

    actions = 0

    actions += (
        click_player_in_current_frame(
            driver
        )
    )

    if depth >= max_depth:
        return actions

    try:
        frame_count = len(
            driver.find_elements(
                By.TAG_NAME,
                "iframe",
            )
        )
    except Exception:
        return actions

    for index in range(
        frame_count
    ):

        try:
            # Find the frames again because the page/player
            # can alter the DOM while playback starts.
            frames = (
                driver.find_elements(
                    By.TAG_NAME,
                    "iframe",
                )
            )

            if index >= len(frames):
                continue

            driver.switch_to.frame(
                frames[index]
            )

            actions += (
                play_in_frames_recursive(
                    driver,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
            )

            driver.switch_to.parent_frame()

        except Exception:

            try:
                driver.switch_to.default_content()
            except Exception:
                pass

            # We intentionally continue.
            continue

    return actions


def try_start_playback(driver):
    """
    Start playback wherever the player is located.

    For Roya this is harmless.
    For Al Mamlaka this is crucial because the
    correct HLS request appears when the actual
    Brightcove player starts.
    """

    try:
        driver.switch_to.default_content()
    except Exception:
        pass

    try:
        iframe_count = len(
            driver.find_elements(
                By.TAG_NAME,
                "iframe",
            )
        )

        logging.info(
            "Player: page currently "
            "contains %d iframe(s).",
            iframe_count,
        )

    except Exception:
        pass

    actions = 0

    try:
        actions = (
            play_in_frames_recursive(
                driver,
                depth=0,
                max_depth=3,
            )
        )
    except Exception:
        pass

    try:
        driver.switch_to.default_content()
    except Exception:
        pass

    logging.info(
        "Player: playback actions attempted: %d",
        actions,
    )

    return actions


# ============================================================
# ROYA
# ============================================================

def score_roya(
    url,
    want_news=False,
):
    """
    Existing Roya logic.

    We keep this strict because the current Roya system
    already works correctly.
    """

    decoded = deep_unquote(
        url
    )

    lower = decoded.lower()

    if ".m3u8" not in lower:
        return -1

    if "kwikmotion.com" not in lower:
        return -1

    # Do not select an individual child/media playlist.
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

    if (
        "hdnts="
        in lower
    ):
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


def scan_roya(
    name,
    page,
    want_news=False,
):
    logging.info(
        "===================================="
    )

    logging.info(
        "Scanning %s",
        name,
    )

    logging.info(
        "Page: %s",
        page,
    )

    driver = create_driver()

    best_url = None
    best_score = -1

    seen = set()

    try:

        try:
            driver.get(
                page
            )

        except TimeoutException:
            logging.warning(
                "%s: page load timed out; "
                "continuing.",
                name,
            )

        # Let Roya's player initialize.
        time.sleep(7)

        started = time.time()

        while (
            time.time()
            - started
            < 30
        ):

            candidates = []

            # REAL Chrome network.
            candidates.extend(
                read_network_urls(
                    driver
                )
            )

            # Secondary browser resource list.
            candidates.extend(
                get_resource_urls(
                    driver
                )
            )

            for candidate in candidates:

                if not candidate:
                    continue

                decoded = (
                    deep_unquote(
                        candidate
                    )
                )

                if decoded in seen:
                    continue

                seen.add(
                    decoded
                )

                score = score_roya(
                    decoded,
                    want_news=want_news,
                )

                if score < 0:
                    continue

                if (
                    score
                    > best_score
                ):

                    best_score = score
                    best_url = decoded

                    logging.info(
                        "%s candidate found: "
                        "%s (score=%d)",
                        name,
                        safe_url_for_log(
                            decoded
                        ),
                        score,
                    )

            # Usually not needed for Roya, but can help
            # if the site waits for playback.
            if (
                time.time()
                - started
                > 8
                and
                best_url is None
            ):
                try_start_playback(
                    driver
                )

            if (
                best_url
                and
                best_score >= 400
            ):
                break

            time.sleep(1)

        if best_url:

            logging.info(
                "%s: selected %s",
                name,
                safe_url_for_log(
                    best_url
                ),
            )

            return best_url

        logging.error(
            "%s: no usable stream found.",
            name,
        )

        return None

    finally:

        try:
            driver.quit()
        except Exception:
            pass


# ============================================================
# AL MAMLAKA
# ============================================================

def looks_like_hls(
    url,
    mime_type="",
):
    """
    Broad HLS recognition.

    Important:
    NO Brightcove domain is required.
    NO playlist-hls-dvr filename is required.
    """

    if not url:
        return False

    lower_url = (
        deep_unquote(
            url
        )
        .lower()
    )

    lower_mime = (
        mime_type
        or ""
    ).lower()

    if ".m3u8" in lower_url:
        return True

    if "mpegurl" in lower_mime:
        return True

    if "application/x-mpegurl" in lower_mime:
        return True

    if (
        "application/"
        "vnd.apple.mpegurl"
        in lower_mime
    ):
        return True

    return False


def score_mamlaka(
    url,
    mime_type="",
    status=None,
    kind="request",
):
    """
    Score an ACTUAL HLS URL seen while the
    official Al Mamlaka player is running.

    Current known Al Mamlaka characteristics get
    strong bonuses, but are NOT requirements.
    """

    decoded = deep_unquote(
        url
    )

    lower = decoded.lower()

    if not looks_like_hls(
        decoded,
        mime_type,
    ):
        return -1

    score = 100


    # --------------------------------------------------------
    # We prefer URLs actually returned successfully
    # by the server.
    # --------------------------------------------------------

    if kind == "response":
        score += 150

    try:
        numeric_status = int(
            status
        )

        if (
            200
            <= numeric_status
            < 300
        ):
            score += 200

    except Exception:
        pass


    # --------------------------------------------------------
    # Generic HLS/master clues
    # --------------------------------------------------------

    if ".m3u8" in lower:
        score += 100

    if "playlist" in lower:
        score += 100

    if "master" in lower:
        score += 150

    if "hls" in lower:
        score += 70

    if "dvr" in lower:
        score += 100


    # --------------------------------------------------------
    # Avoid choosing an individual video rendition if
    # a real master playlist is present.
    # --------------------------------------------------------

    child_clues = [
        "chunks.m3u8",
        "chunklist",
        "media_",
        "segment",
    ]

    if any(
        clue in lower
        for clue in child_clues
    ):
        score -= 250


    # --------------------------------------------------------
    # Current CORRECT Al Mamlaka stream characteristics.
    #
    # These are BONUSES ONLY.
    #
    # Tomorrow the domain/path may change and the scanner
    # can still accept another HLS master.
    # --------------------------------------------------------

    if (
        "fastly.live.brightcove.com"
        in lower
    ):
        score += 500

    if (
        "playlist-hls-dvr.m3u8"
        in lower
    ):
        score += 1000

    elif (
        "playlist-hls"
        in lower
    ):
        score += 500


    # MIME type is useful even if the URL naming
    # convention changes entirely.

    lower_mime = (
        mime_type
        or ""
    ).lower()

    if "mpegurl" in lower_mime:
        score += 200

    return score


def scan_almamlaka():
    """
    Al Mamlaka procedure:

    1. Open official page once.
    2. Let the player initialize.
    3. Clear old network logs.
    4. Make sure browser cache is disabled.
    5. REFRESH the page while Chrome network
       monitoring is already active.
    6. Player autoplays by itself.
    7. Capture every HLS request generated
       during/after the refresh.
    8. Validate candidates independently.
    9. Store the best real stream.

    NO Play-button clicking.
    NO hard-coded fallback URL.
    """

    logging.info(
        "===================================="
    )

    logging.info(
        "Scanning Al Mamlaka TV"
    )

    logging.info(
        "Page: %s",
        ALMAMLAKA_PAGE,
    )

    driver = create_driver()

    seen = set()

    best_url = None
    best_score = -1

    best_found_at = None

    try:

        # ====================================================
        # 1. OPEN PAGE NORMALLY
        # ====================================================

        try:
            driver.get(
                ALMAMLAKA_PAGE
            )

        except TimeoutException:
            logging.warning(
                "Al Mamlaka: initial page "
                "load timed out; continuing."
            )

        logging.info(
            "Al Mamlaka: initial page opened."
        )

        # Let Brightcove/player initialize.
        time.sleep(6)


        # ====================================================
        # 2. DISABLE CACHE
        #
        # We WANT a new network request on refresh.
        # ====================================================

        try:
            driver.execute_cdp_cmd(
                "Network.setCacheDisabled",
                {
                    "cacheDisabled": True
                },
            )

            logging.info(
                "Al Mamlaka: Chrome cache disabled."
            )

        except Exception as exc:

            logging.warning(
                "Al Mamlaka: could not disable "
                "cache: %s",
                type(exc).__name__,
            )


        # Optional extra protection against a service worker
        # serving old requests locally.

        try:
            driver.execute_cdp_cmd(
                "Network.setBypassServiceWorker",
                {
                    "bypass": True
                },
            )

        except Exception:
            pass


        # ====================================================
        # 3. CLEAR NETWORK HISTORY
        #
        # This reproduces:
        #
        # open Network tab
        # ↓
        # then refresh
        #
        # Anything we see after this point belongs to
        # the controlled refresh.
        # ====================================================

        try:
            old_urls = (
                read_performance_urls(
                    driver
                )
            )

            logging.info(
                "Al Mamlaka: cleared %d "
                "pre-refresh network URL(s).",
                len(old_urls),
            )

        except Exception:
            pass


        # ====================================================
        # 4. REFRESH
        #
        # THIS is the equivalent of what you manually do.
        #
        # Network monitoring is ALREADY enabled before
        # the refresh begins.
        # ====================================================

        logging.info(
            "Al Mamlaka: REFRESHING page "
            "with network monitoring active..."
        )

        try:
            driver.refresh()

        except TimeoutException:
            logging.warning(
                "Al Mamlaka: refresh timed out; "
                "network capture continues."
            )


        # ====================================================
        # 5. DO NOT PRESS PLAY
        #
        # Player should autoplay.
        # Immediately monitor the requests generated
        # during and after refresh.
        # ====================================================

        logging.info(
            "Al Mamlaka: refresh completed. "
            "Watching autoplay network traffic..."
        )


        start_time = time.time()

        timeout_seconds = 45


        while (
            time.time()
            - start_time
            < timeout_seconds
        ):

            candidates = []


            # =================================================
            # A. Chrome DevTools Network traffic
            #
            # This contains requests generated DURING refresh,
            # even though driver.refresh() itself was blocking.
            # =================================================

            try:
                candidates.extend(
                    read_performance_urls(
                        driver
                    )
                )

            except Exception:
                pass


            # =================================================
            # B. Resource timing + Video.js inside iframes
            #
            # Extra safety in case Chrome performance logging
            # doesn't expose one of the player requests in the
            # normal list.
            # =================================================

            try:
                candidates.extend(
                    collect_frame_urls(
                        driver
                    )
                )

            except Exception:
                pass


            # Remove duplicates from this batch.
            candidates = list(
                dict.fromkeys(
                    candidates
                )
            )


            # =================================================
            # 6. LOOK THROUGH EVERYTHING SEEN
            # =================================================

            for raw in candidates:

                if not raw:
                    continue


                # A network entry can sometimes contain an
                # encoded URL inside another URL/string.
                expanded = (
                    expand_url_strings(
                        raw
                    )
                )

                if not expanded:
                    expanded = [
                        raw
                    ]


                for candidate in expanded:

                    candidate = (
                        deep_unquote(
                            candidate
                        )
                    )

                    if not candidate:
                        continue


                    # -----------------------------------------
                    # Only investigate HLS URLs.
                    #
                    # NOT restricted to Brightcove.
                    # -----------------------------------------

                    if not is_hls_url(
                        candidate
                    ):
                        continue


                    if candidate in seen:
                        continue


                    seen.add(
                        candidate
                    )


                    logging.info(
                        "Al Mamlaka: HLS request "
                        "seen after refresh: %s",
                        safe_url_for_log(
                            candidate
                        ),
                    )


                    # =========================================
                    # 7. TEST THE URL OUTSIDE SELENIUM
                    #
                    # This prevents us storing something that
                    # only works inside the webpage.
                    # =========================================

                    validation = (
                        validate_hls_standalone(
                            candidate
                        )
                    )


                    if not validation:

                        logging.info(
                            "Al Mamlaka: rejected "
                            "non-standalone candidate: %s",
                            safe_url_for_log(
                                candidate
                            ),
                        )

                        continue


                    # =========================================
                    # 8. SCORE THE REAL WORKING MANIFEST
                    #
                    # Known current:
                    #
                    # fastly.live.brightcove.com
                    # playlist-hls-dvr.m3u8
                    #
                    # gets a large bonus, but isn't required.
                    # =========================================

                    score = (
                        score_mamlaka(
                            validation[
                                "url"
                            ],
                            validation,
                        )
                    )


                    logging.info(
                        "Al Mamlaka VALID HLS: "
                        "%s | master=%s | "
                        "live=%s | score=%d",
                        safe_url_for_log(
                            validation[
                                "url"
                            ]
                        ),
                        validation[
                            "is_master"
                        ],
                        validation[
                            "is_live"
                        ],
                        score,
                    )


                    if (
                        score
                        > best_score
                    ):

                        best_score = score

                        best_url = (
                            validation[
                                "url"
                            ]
                        )

                        best_found_at = (
                            time.time()
                        )


                        logging.info(
                            "Al Mamlaka NEW BEST: %s "
                            "(score=%d)",
                            safe_url_for_log(
                                best_url
                            ),
                            best_score,
                        )


            # =================================================
            # 9. AFTER FINDING A GOOD ONE, KEEP LISTENING
            #    FOR 6 MORE SECONDS
            #
            # This gives the browser time to expose a master
            # after a child/rendition playlist.
            # =================================================

            if (
                best_url
                and
                best_found_at
                and
                time.time()
                - best_found_at
                >= 6
            ):

                break


            # Poll quickly because the manifest request may
            # happen very shortly after refresh.

            time.sleep(
                0.25
            )


        # ====================================================
        # 10. RESULT
        # ====================================================

        if best_url:

            logging.info(
                "Al Mamlaka TV: selected %s "
                "(score=%d)",
                safe_url_for_log(
                    best_url
                ),
                best_score,
            )

            return best_url


        logging.error(
            "Al Mamlaka TV: no independently "
            "playable HLS manifest was observed "
            "during the monitored page refresh."
        )

        return None


    finally:

        try:
            driver.quit()

        except Exception:
            pass


# ============================================================
# CLOUDFLARE WORKER UPDATE
# ============================================================

def push_to_worker(
    streams,
):
    update_url = (
        os.environ.get(
            "WORKER_UPDATE_URL",
            "",
        )
        .strip()
    )

    update_secret = (
        os.environ.get(
            "WORKER_UPDATE_SECRET",
            "",
        )
        .strip()
    )

    if not update_url:
        raise RuntimeError(
            "WORKER_UPDATE_URL "
            "is missing."
        )

    if not update_secret:
        raise RuntimeError(
            "WORKER_UPDATE_SECRET "
            "is missing."
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
                    "github-updater/2.0"
                ),
        },
    )

    logging.info(
        "Sending %d fresh "
        "stream(s) to Worker...",
        len(streams),
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:

            body = (
                response.read()
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
            "Worker rejected update "
            f"with HTTP {exc.code}: "
            f"{body}"
        ) from exc

    except Exception as exc:

        raise RuntimeError(
            "Could not contact Worker: "
            f"{exc}"
        ) from exc


    if not (
        200
        <= status
        < 300
    ):
        raise RuntimeError(
            "Unexpected Worker "
            f"HTTP status {status}: "
            f"{body}"
        )


    logging.info(
        "Worker accepted update."
    )

    logging.info(
        "Worker response: %s",
        body,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    streams = {}


    # ========================================================
    # ROYA TV
    # ========================================================

    roya_tv = scan_roya(
        name="Roya TV",
        page=ROYA_TV_PAGE,
        want_news=False,
    )

    if roya_tv:
        streams[
            "roya_tv"
        ] = roya_tv


    # ========================================================
    # ROYA NEWS
    # ========================================================

    roya_news = scan_roya(
        name="Roya News",
        page=ROYA_NEWS_PAGE,
        want_news=True,
    )

    if roya_news:
        streams[
            "roya_news"
        ] = roya_news


    # ========================================================
    # AL MAMLAKA
    # ========================================================

    almamlaka = (
        scan_almamlaka()
    )

    if almamlaka:
        streams[
            "almamlaka"
        ] = almamlaka


    # ========================================================
    # SEND ONLY SUCCESSFUL STREAMS
    # ========================================================

    if not streams:
        raise RuntimeError(
            "No fresh streams "
            "were discovered."
        )


    push_to_worker(
        streams
    )


    # ========================================================
    # SUMMARY
    # ========================================================

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
            "Only %d of 3 streams "
            "were freshly updated. "
            "Existing Worker targets "
            "for failed channels "
            "were preserved.",
            len(streams),
        )


if __name__ == "__main__":
    main()
