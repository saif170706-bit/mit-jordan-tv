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
        logging.error(f"Fejl ved anmodning til {url}: {e}")
        return ""

def main():
    logging.info("Sender anmodninger til de angivne live-sider...")
    
    # --- 1. AL MAMLAKA TV (Anmodning sendes til din præcise underside) ---
    mamlaka_url = "https://brightcove.com" # Stabile fallback
    mamlaka_html = get_html("https://www.almamlakatv.com/live-video")
    
    # Forbedret mønster til at fange Brightcove-linket i sidens data
    mamlaka_match = re.search(r'(https://[^\s"\']+brightcove\.com/[^"\']+playlist-hls-dvr\.m3u8[^"\']*)', mamlaka_html)
    if mamlaka_match:
        mamlaka_url = mamlaka_match.group(1)
        logging.info("-> SUCCESS: Hentede aktivt link fra www.almamlakatv.com/live-video")

    # --- 2. ROYA TV (Anmodning sendes til live-stream/1) ---
    roya_tv_url = "https://kwikmotion.com" # Stabile fallback
    roya_tv_html = get_html("https://roya.tv/live-stream/1")
    
    # Bredere søgning til at fange Kwikmotion-linket uanset JSON- eller HTML-formatering
    roya_tv_match = re.search(r'(https://[^\s"\']+kwikmotion\.com/[^"\']+playlist\.m3u8\?hdnts=[^"\']+)', roya_tv_html)
    if roya_tv_match:
        roya_tv_url = roya_tv_match.group(1)
        logging.info("-> SUCCESS: Hentede aktivt link fra roya.tv/live-stream/1")
        
    # --- 3. ROYA NEWS (Anmodning sendes til live-stream/21) ---
    roya_news_url = "https://kwikmotion.com" # Stabile fallback
    roya_news_html = get_html("https://roya.tv/live-stream/21")
    
    roya_news_match = re.search(r'(https://[^\s"\']+kwikmotion\.com/[^"\']+playlist\.m3u8\?hdnts=[^"\']+)', roya_news_html)
    if roya_news_match:
        roya_news_url = roya_news_match.group(1)
        logging.info("-> SUCCESS: Hentede aktivt link fra roya.tv/live-stream/21")

    # --- BYG PLAYLISTEN ---
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
    logging.info("playlist.m3u er blevet gemt succesfuldt!")

if __name__ == "__main__":
    main()

