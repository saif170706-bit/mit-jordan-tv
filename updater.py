import time
import json
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# Sæt basal logging op
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def plet_network_sniffer(target_url):
    """
    Starter en usynlig Chrome-browser, indlæser den præcise live-side og 
    leder efter 'playlist.m3u8' i netværkstrafikken for at fange linket med tokenet.
    """
    options = Options()
    options.add_argument("--headless")  # Gør browseren usynlig i skyen
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")
    
    # Aktiver logning af netværksydelse/trafik i Chrome
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    found_url = None
    
    try:
        logging.info(f"Åbner usynlig browser på live-siden: {target_url}")
        driver.get(target_url)
        
        # Vent 8 sekunder på, at afspilleren indlæser og genererer tokenet i netværket
        time.sleep(8)  
        
        # Hent alle netværksanmodninger, som browseren har foretaget
        logs = driver.get_log("performance")
        logging.info("Gennemlæser netværksloggen...")
        
        for entry in logs:
            log_data = json.loads(entry["message"])["message"]
            if "params" in log_data and "request" in log_data["params"]:
                req_url = log_data["params"]["request"]["url"]
                
                # Søger udelukkende efter den ene række, der indeholder 'playlist.m3u8'
                if "playlist.m3u8" in req_url:
                    found_url = req_url
                    logging.info(f"-> MATCH FUNDET: {found_url}")
                    break  # Stop med det samme, når den rigtige række er fundet!
                    
    except Exception as e:
        logging.error(f"Fejl under søgning i netværksloggen: {e}")
    finally:
        driver.quit()
        
    return found_url

def main():
    logging.info("Starter det optimerede IPTV-scrapersystem...")
    
    # --- 1. ANMODNING: AL MAMLAKA TV (Direkte til den rigtige live-side) ---
    mamlaka_url = plet_network_sniffer("https://www.almamlakatv.com/live-video")
    if not mamlaka_url:
        logging.warning("Kunne ikke sniffe Al Mamlaka, bruger fallback link.")
        mamlaka_url = "https://brightcove.com"

    # --- 2. ANMODNING: ROYA TV (Direkte til den rigtige live-side) ---
    roya_tv_url = plet_network_sniffer("https://roya.tv/live-stream/1")
    if not roya_tv_url:
        logging.warning("Kunne ikke sniffe Roya TV, bruger fallback link.")
        roya_tv_url = "https://kwikmotion.com"

    # --- 3. ANMODNING: ROYA NEWS (Direkte til den rigtige live-side) ---
    roya_news_url = plet_network_sniffer("https://roya.tv/live-stream/21")
    if not roya_news_url:
        logging.warning("Kunne ikke sniffe Roya News, bruger fallback link.")
        roya_news_url = "https://kwikmotion.com"

    # --- BYG DEN ENDELIGE, RENE PLAYLISTE ---
    m3u_content = f"""#EXTM3U

#EXTINF:-1, Al Mamlaka TV
{mamlaka_url}

#EXTINF:-1, Roya TV
{roya_tv_url}

#EXTINF:-1, Roya News
{roya_news_url}

#EXTINF:-1, Roya Comedy
https://kwikmotion.com

#EXTINF:-1, Roya Kitchen
https://kwikmotion.com

#EXTINF:-1, Roya Set El Nakhat
https://kwikmotion.com
"""
    
    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write(m3u_content)
    logging.info("Succes! playlist.m3u er gemt med de mest opdaterede token-links.")

if __name__ == "__main__":
    main()
