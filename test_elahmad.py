import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By


PAGE = "https://www.elahmad.ru/tv/live/roya_tv.php?id=RoyaTV"


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

    if chrome_binary:
        options.binary_location = chrome_binary

    chromedriver_path = os.environ.get(
        "CHROMEDRIVER_PATH"
    )

    if chromedriver_path:
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


def try_start_video(driver):

    try:
        driver.execute_script("""
            document.querySelectorAll('video').forEach(v => {
                try {
                    v.muted = true;
                    v.autoplay = true;
                    v.play().catch(() => {});
                } catch(e) {}
            });
        """)
    except Exception:
        pass

    for selector in [
        ".vjs-big-play-button",
        ".vjs-play-control",
        "button"
    ]:

        try:
            elements = driver.find_elements(
                By.CSS_SELECTOR,
                selector
            )

            for element in elements[:10]:

                try:
                    driver.execute_script(
                        "arguments[0].click();",
                        element
                    )
                except Exception:
                    pass

        except Exception:
            pass


def print_media_requests(logs):

    for entry in logs:

        try:

            message = json.loads(
                entry["message"]
            )["message"]

        except Exception:
            continue

        method = message.get("method", "")

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

        if not url:
            continue

        low = url.lower()

        interesting = [
            ".m3u8",
            ".mpd",
            "manifest",
            "playlist",
            "chunklist"
        ]

        if any(x in low for x in interesting):

            print("")
            print("================================")
            print("MEDIA REQUEST FOUND")
            print("================================")
            print(url)


def main():

    driver = create_driver()

    try:

        print("Opening:")
        print(PAGE)

        driver.get(PAGE)

        # Give page time to build player
        time.sleep(8)

        try_start_video(driver)

        # Also try iframes
        try:

            iframes = driver.find_elements(
                By.TAG_NAME,
                "iframe"
            )

            print(
                f"Found {len(iframes)} iframe(s)"
            )

            for i in range(len(iframes)):

                try:

                    driver.switch_to.default_content()

                    frames = driver.find_elements(
                        By.TAG_NAME,
                        "iframe"
                    )

                    if i >= len(frames):
                        continue

                    driver.switch_to.frame(
                        frames[i]
                    )

                    try_start_video(driver)

                except Exception:
                    pass

            driver.switch_to.default_content()

        except Exception:
            pass

        # Watch traffic for 45 seconds
        for second in range(45):

            time.sleep(1)

            logs = driver.get_log(
                "performance"
            )

            print_media_requests(
                logs
            )

            if second in [10, 20, 30]:

                try_start_video(driver)

    finally:

        driver.quit()


if __name__ == "__main__":
    main()
