import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By


PAGE = "https://www.elahmad.ru/tv/live/roya_tv.php?id=RoyaTV"

OUTPUT_FILE = "elahmad_debug.txt"


def log(text=""):

    print(text)

    with open(
        OUTPUT_FILE,
        "a",
        encoding="utf-8"
    ) as f:
        f.write(str(text) + "\n")


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
        {
            "performance": "ALL",
            "browser": "ALL"
        }
    )

    chrome_binary = os.environ.get(
        "CHROME_BINARY"
    )

    if chrome_binary:
        options.binary_location = chrome_binary

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


def get_network_urls(logs):

    urls = []

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

        if method == "Network.requestWillBeSent":

            url = (
                message
                .get("params", {})
                .get("request", {})
                .get("url", "")
            )

        elif method == "Network.responseReceived":

            url = (
                message
                .get("params", {})
                .get("response", {})
                .get("url", "")
            )

        if url:
            urls.append(url)

    return urls


def try_start_video(driver):

    try:

        driver.execute_script(
            """
            document.querySelectorAll('video').forEach(v => {

                try {
                    v.muted = true;

                    const p = v.play();

                    if (p && p.catch) {
                        p.catch(() => {});
                    }

                } catch(e) {}

            });
            """
        )

    except Exception:
        pass


def main():

    # Clear previous output
    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        f.write("")

    driver = create_driver()

    all_urls = set()

    try:

        log("========================================")
        log("OPENING PAGE")
        log("========================================")
        log(PAGE)

        driver.get(PAGE)

        time.sleep(10)

        log("")
        log("========================================")
        log("PAGE INFORMATION")
        log("========================================")

        log(
            "CURRENT URL:"
        )

        log(
            driver.current_url
        )

        log(
            ""
        )

        log(
            "PAGE TITLE:"
        )

        log(
            driver.title
        )

        # ----------------------------------------------------
        # iframe information
        # ----------------------------------------------------

        try:

            iframes = driver.find_elements(
                By.TAG_NAME,
                "iframe"
            )

            log("")
            log(
                f"IFRAMES FOUND: {len(iframes)}"
            )

            for i, iframe in enumerate(
                iframes
            ):

                src = (
                    iframe.get_attribute("src")
                    or ""
                )

                log(
                    f"IFRAME {i + 1}: {src}"
                )

        except Exception as e:

            log(
                f"IFRAME ERROR: {e}"
            )

        # ----------------------------------------------------
        # Video elements
        # ----------------------------------------------------

        try:

            videos = driver.find_elements(
                By.TAG_NAME,
                "video"
            )

            log("")
            log(
                f"VIDEO ELEMENTS FOUND: {len(videos)}"
            )

            for i, video in enumerate(
                videos
            ):

                src = (
                    video.get_attribute("src")
                    or ""
                )

                log(
                    f"VIDEO {i + 1}: {src}"
                )

        except Exception as e:

            log(
                f"VIDEO ERROR: {e}"
            )

        try_start_video(driver)

        # ----------------------------------------------------
        # Monitor network for 45 sec
        # ----------------------------------------------------

        log("")
        log("========================================")
        log("WATCHING NETWORK FOR 45 SECONDS")
        log("========================================")

        for second in range(45):

            time.sleep(1)

            logs = driver.get_log(
                "performance"
            )

            urls = get_network_urls(
                logs
            )

            for url in urls:

                if url in all_urls:
                    continue

                all_urls.add(url)

                low = url.lower()

                interesting = [
                    ".m3u8",
                    ".mpd",
                    "roya",
                    "stream",
                    "player",
                    "video",
                    "manifest",
                    "playlist",
                    "hls"
                ]

                if any(
                    word in low
                    for word in interesting
                ):

                    log("")
                    log("INTERESTING REQUEST:")
                    log(url)

            if second in [
                10,
                20,
                30,
                40
            ]:

                try_start_video(
                    driver
                )

        # ----------------------------------------------------
        # Javascript performance resources
        # ----------------------------------------------------

        log("")
        log("========================================")
        log("JAVASCRIPT PERFORMANCE RESOURCES")
        log("========================================")

        try:

            resources = driver.execute_script(
                """
                return performance
                    .getEntriesByType('resource')
                    .map(x => x.name);
                """
            )

            for url in resources:

                low = url.lower()

                interesting = [
                    ".m3u8",
                    ".mpd",
                    "roya",
                    "stream",
                    "player",
                    "video",
                    "manifest",
                    "playlist",
                    "hls"
                ]

                if any(
                    word in low
                    for word in interesting
                ):

                    log(url)

        except Exception as e:

            log(
                f"RESOURCE ERROR: {e}"
            )

        # ----------------------------------------------------
        # Browser console
        # ----------------------------------------------------

        log("")
        log("========================================")
        log("BROWSER CONSOLE")
        log("========================================")

        try:

            browser_logs = driver.get_log(
                "browser"
            )

            for entry in browser_logs:

                log(
                    entry
                )

        except Exception as e:

            log(
                f"BROWSER LOG ERROR: {e}"
            )

        # ----------------------------------------------------
        # Save page HTML
        # ----------------------------------------------------

        with open(
            "elahmad_page.html",
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                driver.page_source
            )

        log("")
        log("========================================")
        log("DONE")
        log("========================================")

        log(
            f"TOTAL NETWORK URLS SEEN: {len(all_urls)}"
        )

        log(
            "Saved elahmad_debug.txt"
        )

        log(
            "Saved elahmad_page.html"
        )

    finally:

        driver.quit()


if __name__ == "__main__":
    main()
