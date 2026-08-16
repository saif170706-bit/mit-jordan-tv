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
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# ============================================================
# THE THREE EXACT LIVE PAGES
# ============================================================

ROYA_TV_PAGE = "https://roya.tv/live-stream/1"

ROYA_NEWS_PAGE = "https://roya.tv/live-stream/21"

MAMLAKA_PAGE = "https://www.almamlakatv.com/live-video"


# ============================================================
# CURRENTLY CONFIRMED WORKING AL MAMLAKA MASTER STREAM
#
# This is ONLY a final fallback.
#
# Priority is:
# 1. Fresh Al Mamlaka URL found now
# 2. Previous Al Mamlaka URL already stored in playlist.m3u
# 3. This known working URL
# ============================================================

KNOWN_MAMLAKA_FALLBACK = (
    "https://fastly.live.brightcove.com/"
    "6376826200112/eu-central-1/6415809151001/"
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJob3N0IjoieWlod3RhLmVncmVzcy5haGc3NmwiLCJhY2NvdW50X2lkIjoiNjQxNTgwOTE1MTAwMSIsImVobiI6ImZhc3RseS5saXZlLmJyaWdodGNvdmUuY29tIiwiaXNzIjoiYmxpdmUtcGxheWJhY2stc291cmNlLWFwaSIsInN1YiI6InBhdGhtYXB0b2tlbiIsImF1ZCI6WyI2NDE1ODA5MTUxMDAxIl0sImp0aSI6IjYzNzY4MjYyMDAxMTIifQ."
    "EBaDAQiDkyoRKYIjLROyrZzKFPcftOUxk4ftmhtVsEk/"
    "playlist-hls-dvr.m3u8"
)


# ============================================================
# CREATE CHROME
# ============================================================

def create_driver():

    options = Options()

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    options.add_argument(
        "--window-size=1920,1080"
    )

    # Important for live-video players
    options.add_argument(
        "--autoplay-policy=no-user-gesture-required"
    )

    options.add_argument("--mute-audio")

    # Enable Chrome performance/network logs
    options.set_capability(
        "goog:loggingPrefs",
        {
            "performance": "ALL"
        }
    )

    # Chrome installed by GitHub Action
    chrome_binary = os.environ.get(
        "CHROME_BINARY"
    )

    if (
        chrome_binary
        and os.path.exists(chrome_binary)
    ):
        options.binary_location = chrome_binary


    # Matching ChromeDriver installed by GitHub Action
    chromedriver_path = os.environ.get(
        "CHROMEDRIVER_PATH"
    )

    if (
        chromedriver_path
        and os.path.exists(chromedriver_path)
    ):
        service = Service(
            chromedriver_path
        )

    else:
        service = Service()


    driver = webdriver.Chrome(
        service=service,
        options=options
    )

    driver.set_page_load_timeout(60)


    # Explicitly enable Network events
    try:

        driver.execute_cdp_cmd(
            "Network.enable",
            {}
        )

    except Exception:
        pass


    return driver


# ============================================================
# READ OLD PLAYLIST
#
# This is VERY important.
#
# If a channel cannot be refreshed during one GitHub run,
# we keep the previous working URL instead of deleting it.
# ============================================================

def load_existing_playlist(
    path="playlist.m3u"
):

    streams = {}

    if not os.path.exists(path):
        return streams


    current_channel = None


    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        for raw_line in file:

            line = raw_line.strip()


            if line.startswith("#EXTINF:"):

                if "," in line:

                    current_channel = (
                        line
                        .split(",", 1)[1]
                        .strip()
                    )


            elif (
                current_channel
                and line.startswith(
                    (
                        "https://",
                        "http://"
                    )
                )
            ):

                if ".m3u8" in line.lower():

                    streams[
                        current_channel
                    ] = line


                current_channel = None


    return streams


# ============================================================
# EXTRACT URLS FROM CHROME NETWORK LOG
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


        method = message.get(
            "method"
        )


        # ------------------------
        # REQUEST
        # ------------------------

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

            if url:
                urls.append(url)


        # ------------------------
        # RESPONSE
        # ------------------------

        elif (
            method
            == "Network.responseReceived"
        ):

            response = (
                message
                .get("params", {})
                .get("response", {})
            )

            url = response.get(
                "url",
                ""
            )

            status = response.get(
                "status",
                0
            )


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
#
# Sometimes Brightcove also puts the master URL inside:
#
# metrics.brightcove.com/...&media_url=...
# ============================================================

def brightcove_media_urls(url):

    if (
        "metrics.brightcove.com"
        not in url.lower()
    ):

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

def start_video_in_current_frame(
    driver
):

    # ------------------------
    # Click Video.js buttons
    # ------------------------

    selectors = [

        ".vjs-big-play-button",

        ".vjs-play-control"

    ]


    for selector in selectors:

        try:

            buttons = (
                driver.find_elements(
                    By.CSS_SELECTOR,
                    selector
                )
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


    # ------------------------
    # HTML5 <video>.play()
    # ------------------------

    try:

        driver.execute_script(
            """
            document
                .querySelectorAll('video')
                .forEach((v) => {

                    try {

                        v.muted = true;

                        v.autoplay = true;

                        const promise = v.play();

                        if (
                            promise
                            && promise.catch
                        ) {

                            promise.catch(
                                () => {}
                            );

                        }

                    }

                    catch (e) {}

                });
            """
        )

    except Exception:
        pass


    # ------------------------
    # Video.js API
    # ------------------------

    try:

        driver.execute_script(
            """
            try {

                if (
                    window.videojs
                    && videojs.getPlayers
                ) {

                    const players =
                        videojs.getPlayers();

                    Object
                        .keys(players)
                        .forEach((key) => {

                            try {

                                const player =
                                    players[key];

                                player.muted(true);

                                player.play();

                            }

                            catch (e) {}

                        });

                }

            }

            catch (e) {}
            """
        )

    except Exception:
        pass


# ============================================================
# ACTIVELY START AL MAMLAKA / BRIGHTCOVE
# ============================================================

def actively_start_brightcove(
    driver
):

    # First try the main page
    driver.switch_to.default_content()

    start_video_in_current_frame(
        driver
    )


    # Now search all iframes
    try:

        iframes = (
            driver.find_elements(
                By.TAG_NAME,
                "iframe"
            )
        )

    except Exception:

        iframes = []


    logging.info(
        "Al Mamlaka: found %d iframe(s).",
        len(iframes)
    )


    # Try playback inside each iframe
    for index in range(
        len(iframes)
    ):

        try:

            driver.switch_to.default_content()


            # Re-read the iframe list
            # because DOM references can change
            current_iframes = (
                driver.find_elements(
                    By.TAG_NAME,
                    "iframe"
                )
            )


            if (
                index
                >= len(current_iframes)
            ):

                continue


            frame = (
                current_iframes[index]
            )


            src = (
                frame.get_attribute(
                    "src"
                )
                or ""
            )


            logging.info(
                "Al Mamlaka: trying iframe %d: %s",
                index + 1,
                src[:180]
            )


            driver.switch_to.frame(
                frame
            )


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
#
# We specifically want:
#
# playlist-hls-dvr.m3u8
# ============================================================

def find_mamlaka_master(
    logs
):

    urls = network_urls_from_logs(
        logs
    )


    for url in urls:

        low = url.lower()


        # ====================================================
        # METHOD 1
        #
        # DIRECT network request
        #
        # This is exactly what YOU found manually.
        # ====================================================

        if (
            "fastly.live.brightcove.com"
            in low
            and
            "playlist-hls-dvr.m3u8"
            in low
        ):

            logging.info(
                "AL MAMLAKA MASTER "
                "DIRECTLY FOUND:"
            )

            logging.info(url)

            return url


        # ====================================================
        # METHOD 2
        #
        # Brightcove metrics media_url=
        # ====================================================

        for media_url in (
            brightcove_media_urls(
                url
            )
        ):

            media_low = (
                media_url.lower()
            )


            if (
                "fastly.live.brightcove.com"
                in media_low
                and
                "playlist-hls-dvr.m3u8"
                in media_low
            ):

                logging.info(
                    "AL MAMLAKA MASTER "
                    "FOUND IN media_url=:"
                )

                logging.info(
                    media_url
                )

                return media_url


    return None


# ============================================================
# AL MAMLAKA SCANNER
# ============================================================

def sniff_almamlaka(
    timeout_seconds=45
):

    driver = None


    try:

        driver = create_driver()


        logging.info(
            "================================"
        )

        logging.info(
            "OPENING AL MAMLAKA:"
        )

        logging.info(
            MAMLAKA_PAGE
        )


        driver.get(
            MAMLAKA_PAGE
        )


        # Give Brightcove time to initialize
        time.sleep(5)


        # ====================================================
        # FIRST CHECK
        #
        # Maybe autoplay already requested
        # playlist-hls-dvr.m3u8
        # ====================================================

        found = find_mamlaka_master(

            driver.get_log(
                "performance"
            )

        )


        if found:
            return found


        # ====================================================
        # ACTIVELY START BRIGHTCOVE
        # ====================================================

        logging.info(
            "Al Mamlaka master not yet seen."
        )

        logging.info(
            "Actively starting Brightcove..."
        )


        actively_start_brightcove(
            driver
        )


        deadline = (
            time.time()
            + timeout_seconds
        )


        next_play_attempt = (
            time.time()
            + 8
        )


        # ====================================================
        # WATCH NETWORK LIVE
        # ====================================================

        while (
            time.time()
            < deadline
        ):

            time.sleep(1)


            logs = driver.get_log(
                "performance"
            )


            # Print EVERY M3U8 request
            # so GitHub logs are easy to debug
            urls = network_urls_from_logs(
                logs
            )


            for url in urls:

                if (
                    ".m3u8"
                    in url.lower()
                ):

                    logging.info(
                        "AL MAMLAKA M3U8 SEEN:"
                    )

                    logging.info(
                        url
                    )


            # Look specifically for
            # playlist-hls-dvr.m3u8
            found = find_mamlaka_master(
                logs
            )


            if found:

                logging.info(
                    "SUCCESS:"
                    " Al Mamlaka fresh"
                    " master found."
                )

                return found


            # Try pressing play again
            # every 8 seconds
            if (
                time.time()
                >= next_play_attempt
            ):

                logging.info(
                    "Trying Brightcove "
                    "playback again..."
                )

                actively_start_brightcove(
                    driver
                )

                next_play_attempt = (
                    time.time()
                    + 8
                )


        logging.warning(
            "Al Mamlaka:"
            " no fresh "
            "playlist-hls-dvr.m3u8 "
            "found during this run."
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
# ROYA MASTER PLAYLIST SCORING
# ============================================================

def roya_score(url):

    low = url.lower()


    if ".m3u8" not in low:

        return -10000


    score = 0


    # Prefer top/master playlists
    if "playlist.m3u8" in low:

        score += 500


    if "master.m3u8" in low:

        score += 450


    if "index.m3u8" in low:

        score += 300


    # Known delivery systems
    if "kwikmotion" in low:

        score += 150


    if "akamaized" in low:

        score += 100


    if "daioncdn" in low:

        score += 100


    # Avoid audio/video child playlists
    if "chunklist" in low:

        score -= 500


    if "audio" in low:

        score -= 300


    return score


# ============================================================
# ROYA TV + ROYA NEWS SCANNER
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

        logging.info(
            page_url
        )


        driver.get(
            page_url
        )


        time.sleep(3)


        # This already worked in the previous run,
        # but attempting play makes it more robust.
        start_video_in_current_frame(
            driver
        )


        deadline = (
            time.time()
            + timeout_seconds
        )


        while (
            time.time()
            < deadline
        ):

            time.sleep(1)


            logs = driver.get_log(
                "performance"
            )


            urls = network_urls_from_logs(
                logs
            )


            for url in urls:

                # --------------------
                # Direct M3U8
                # --------------------

                if (
                    ".m3u8"
                    in url.lower()
                ):

                    candidates.add(
                        url
                    )

                    logging.info(
                        "%s M3U8 SEEN:",
                        channel_name
                    )

                    logging.info(
                        url
                    )


                # --------------------
                # media_url fallback
                # --------------------

                for media_url in (
                    brightcove_media_urls(
                        url
                    )
                ):

                    if (
                        ".m3u8"
                        in media_url.lower()
                    ):

                        candidates.add(
                            media_url
                        )


            # =================================================
            # SELECT BEST ROYA URL
            # =================================================

            if candidates:

                best = max(
                    candidates,
                    key=roya_score
                )


                if (
                    roya_score(best)
                    >= 300
                ):

                    logging.info(
                        "%s MASTER SELECTED:",
                        channel_name
                    )

                    logging.info(
                        best
                    )

                    return best


        # =====================================================
        # TIMEOUT BUT WE FOUND SOMETHING
        # =====================================================

        if candidates:

            best = max(
                candidates,
                key=roya_score
            )


            logging.info(
                "%s BEST CANDIDATE "
                "AFTER TIMEOUT:",
                channel_name
            )

            logging.info(
                best
            )


            return best


        logging.warning(
            "%s:"
            " no fresh M3U8 found.",
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
# CHOOSE WHICH URL TO KEEP
#
# Priority:
#
# 1. fresh URL
# 2. previous playlist URL
# 3. hard fallback, only for Al Mamlaka
# ============================================================

def choose_url(
    channel_name,
    fresh_url,
    old_streams,
    hard_fallback=None
):

    # Fresh result wins
    if fresh_url:

        logging.info(
            "%s:"
            " USING FRESH URL.",
            channel_name
        )

        return fresh_url


    # Otherwise KEEP previous
    previous = old_streams.get(
        channel_name
    )


    if previous:

        logging.warning(
            "%s:"
            " fresh scan failed."
            " KEEPING PREVIOUS URL.",
            channel_name
        )

        return previous


    # Al Mamlaka emergency seed
    if hard_fallback:

        logging.warning(
            "%s:"
            " no previous URL exists."
            " USING KNOWN WORKING FALLBACK.",
            channel_name
        )

        return hard_fallback


    logging.error(
        "%s:"
        " no URL available.",
        channel_name
    )


    return None


# ============================================================
# WRITE FINAL PLAYLIST
# ============================================================

def write_playlist(
    streams,
    path="playlist.m3u"
):

    ordered_channels = [

        "Roya TV",

        "Roya News",

        "Al Mamlaka TV"

    ]


    lines = [

        "#EXTM3U",

        ""

    ]


    for channel in ordered_channels:

        url = streams.get(
            channel
        )


        if not url:

            continue


        lines.extend(
            [

                f"#EXTINF:-1,{channel}",

                url,

                ""

            ]
        )


    with open(
        path,
        "w",
        encoding="utf-8",
        newline="\n"
    ) as file:

        file.write(
            "\n".join(lines).rstrip()
            + "\n"
        )


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
        "=============================================="
    )


    # Load last known good URLs FIRST
    old_streams = (
        load_existing_playlist()
    )


    logging.info(
        "Previous URLs loaded:"
        " %d",
        len(old_streams)
    )


    # ========================================================
    # 1. ROYA TV
    #
    # Discover fresh URL every run
    # ========================================================

    fresh_roya_tv = sniff_roya(

        ROYA_TV_PAGE,

        "Roya TV"

    )


    # ========================================================
    # 2. ROYA NEWS
    #
    # Discover fresh URL every run
    # ========================================================

    fresh_roya_news = sniff_roya(

        ROYA_NEWS_PAGE,

        "Roya News"

    )


    # ========================================================
    # 3. AL MAMLAKA
    #
    # Actively start Brightcove
    #
    # Look specifically for:
    #
    # playlist-hls-dvr.m3u8
    # ========================================================

    fresh_mamlaka = (
        sniff_almamlaka()
    )


    # ========================================================
    # CHOOSE FINAL URLS
    # ========================================================

    final_streams = {


        "Roya TV": choose_url(

            "Roya TV",

            fresh_roya_tv,

            old_streams

        ),


        "Roya News": choose_url(

            "Roya News",

            fresh_roya_news,

            old_streams

        ),


        "Al Mamlaka TV": choose_url(

            "Al Mamlaka TV",

            fresh_mamlaka,

            old_streams,

            hard_fallback=
                KNOWN_MAMLAKA_FALLBACK

        )

    }


    # Remove None values
    final_streams = {

        channel: url

        for channel, url
        in final_streams.items()

        if url

    }


    # ========================================================
    # SAVE
    # ========================================================

    write_playlist(
        final_streams
    )


    logging.info(
        "=============================================="
    )


    logging.info(
        "playlist.m3u written "
        "with %d channel(s).",
        len(final_streams)
    )


    for channel, url in (
        final_streams.items()
    ):

        logging.info(
            "%s -> %s",
            channel,
            url
        )


    logging.info(
        "=============================================="
    )


if __name__ == "__main__":

    main()
