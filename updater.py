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
    options.add_argument("--headless=new")  # Ny headless-metode til cloud-miljøer
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")
    
    # Aktiver logning af netværksydelse/trafik i Chrome
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    
    driver = None
    found_url = None
    
    try:
        logging.info(f"Åbner usynlig browser på live-siden: {target_url}")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get(target_url)
        
        # Vent 10 sekunder på, at afspilleren indlæser og genererer tokenet i netværket
        time.sleep(10)  
        
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
        if driver:
            driver.quit()
        
    return found_url

def main():
    logging.info("Starter det optimerede IPTV-scrapersystem...")
    
    # --- 1. ANMODNING: AL MAMLAKA TV (Præcis den underside du har givet mig) ---
    mamlaka_url = "https://brightcove.com"
    mamlaka_sniffed = plet_network_sniffer("https://www.almamlakatv.com/live-video")
    if mamlaka_sniffed:
        mamlaka_url = mamlaka_sniffed

    # --- 2. ANMODNING: ROYA TV (Præcis den underside du har givet mig) ---
    roya_tv_url = "https://kwikmotion.com"
    roya_tv_sniffed = plet_network_sniffer("https://roya.tv/live-stream/1")
    if roya_tv_sniffed:
        roya_tv_url = roya_tv_sniffed

    # --- 3. ANMODNING: ROYA NEWS (Præcis den underside du har givet mig) ---
    roya_news_url = "https://kwikmotion.com"
    roya_news_sniffed = plet_network_sniffer("https://roya.tv/live-stream/21")
    if roya_news_sniffed:
        roya_news_url = roya_news_sniffed

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
    logging.info("Succes! playlist.m3u er gemt korrekt.")

if __name__ == "__main__":
    main()
