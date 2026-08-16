import re
import urllib.request
import logging

# Sæt basal logging op
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_html(url):
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        logging.error(f"Fejl ved hentning af {url}: {e}")
        return ""

def main():
    logging.info("Starter automatisk token-fornyelse for Jordan-kanaler...")
    
    # --- 1. AL MAMLAKA TV (Skal scrapes pga. dynamisk Brightcove JWT-token) ---
    mamlaka_url = "https://brightcove.com" # Fallback
    mamlaka_html = get_html("https://almamlakatv.com")
    mamlaka_match = re.search(r'(https://fastly\.live\.brightcove\.com/[^"\']+playlist-hls-dvr\.m3u8)', mamlaka_html)
    if mamlaka_match:
        mamlaka_url = mamlaka_match.group(1)
        logging.info("-> SUCCESS: Fandt frisk token-link til Al Mamlaka TV")
    else:
        logging.warning("-> Kunne ikke finde Mamlaka i HTML, bruger fallback.")

    # --- 2. ROYA TV (Skal scrapes pga. Akamai 'hdnts' token) ---
    roya_tv_url = "https://kwikmotion.com" # Fallback
    roya_tv_html = get_html("https://roya.tv")
    roya_tv_match = re.search(r'(https://live\.kwikmotion\.com/[^"\']+playlist\.m3u8\?hdnts=[^"\']+)', roya_tv_html)
    if roya_tv_match:
        roya_tv_url = roya_tv_match.group(1)
        logging.info("-> SUCCESS: Fandt frisk token-link til Roya TV")
    else:
        logging.warning("-> Kunne ikke finde Roya TV i HTML, bruger fallback.")
        
    # --- 3. ROYA NEWS (Skal scrapes pga. Akamai 'hdnts' token) ---
    roya_news_url = "https://kwikmotion.com" # Fallback
    roya_news_html = get_html("https://roya.tv")
    roya_news_match = re.search(r'(https://live\.kwikmotion\.com/[^"\']+playlist\.m3u8\?hdnts=[^"\']+)', roya_news_html)
    if roya_news_match:
        roya_news_url = roya_news_match.group(1)
        logging.info("-> SUCCESS: Fandt frisk token-link til Roya News")
    else:
        logging.warning("-> Kunne ikke finde Roya News i HTML, bruger fallback.")

    # --- BYG DEN RENE M3U-AFSPILNINGSLISTE ---
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
    
    # Gem listen direkte som en m3u-fil i arkivet
    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write(m3u_content)
    logging.info("playlist.m3u er blevet opbygget og gemt korrekt!")

if __name__ == "__main__":
    main()
