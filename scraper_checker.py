import aiohttp
import asyncio
import aiodns
from bs4 import BeautifulSoup
import logging
import re
import os
from aiohttp_socks import ProxyConnector
from datetime import datetime

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Konfigurasi
TIMEOUT = 10  # Timeout untuk checking proxy
GEO_API_URL = "http://ip-api.com/json/{}"
GEO_RATE_LIMIT = 30  # 30 proxy per menit
TEST_URL = "http://httpbin.org/ip"  # Situs untuk tes proxy
OUTPUT_DIR = "result"
ID_DIR = os.path.join(OUTPUT_DIR, "ID")

# Regex untuk deteksi IP:Port
PROXY_REGEX = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})')

async def fetch_url(session, url, semaphore):
    async with semaphore:
        try:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.error(f"Failed to fetch {url}: Status {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

async def parse_proxies(html):
    proxies = set()
    soup = BeautifulSoup(html, 'html.parser')
    
    # Cari IP:Port di teks atau tabel
    for text in soup.stripped_strings:
        matches = PROXY_REGEX.findall(text)
        for match in matches:
            proxies.add(f"{match[0]}:{match[1]}")
    
    # Cari di tabel HTML
    for row in soup.find_all('tr'):
        cols = row.find_all('td')
        if len(cols) >= 2:
            ip = cols[0].get_text().strip()
            port = cols[1].get_text().strip()
            if PROXY_REGEX.match(f"{ip}:{port}"):
                proxies.add(f"{ip}:{port}")
    
    return proxies

async def check_proxy(session, proxy, protocol, semaphore):
    async with semaphore:
        try:
            if protocol == "http":
                proxy_url = f"http://{proxy}"
                async with session.get(TEST_URL, proxy=proxy_url, timeout=TIMEOUT) as response:
                    if response.status == 200:
                        latency = response.connection.transport.get_extra_info('latency', 0)
                        return protocol, latency
            else:
                connector = ProxyConnector.from_url(f"{protocol}://{proxy}")
                async with aiohttp.ClientSession(connector=connector) as socks_session:
                    async with socks_session.get(TEST_URL, timeout=TIMEOUT) as response:
                        if response.status == 200:
                            latency = response.connection.transport.get_extra_info('latency', 0)
                            return protocol, latency
            return None, None
        except Exception:
            return None, None

async def check_geo(ip, session, semaphore):
    async with semaphore:
        try:
            async with session.get(GEO_API_URL.format(ip), timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('countryCode') == 'ID'
                return False
        except Exception:
            return False

async def save_proxies(proxies, filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as f:
        for proxy in proxies:
            f.write(f"{proxy}\n")
    logger.info(f"Saved {len(proxies)} proxies to {filename}")

async def main():
    # Inisialisasi
    semaphore = asyncio.Semaphore(50)  # Batasi 50 koneksi paralel
    geo_semaphore = asyncio.Semaphore(1)  # Kontrol rate limit geo
    all_proxies = set()
    
    # Baca sources.txt
    try:
        with open('sources.txt', 'r') as f:
            urls = [line.strip() for line in f if line.strip()]
        logger.info(f"Found {len(urls)} URLs in sources.txt")
    except Exception as e:
        logger.error(f"Error reading sources.txt: {e}")
        return
    
    # Scrape proxies
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_url(session, url, semaphore) for url in urls]
        htmls = await asyncio.gather(*tasks, return_exceptions=True)
        
        for html in htmls:
            if html:
                proxies = await parse_proxies(html)
                all_proxies.update(proxies)
    
    logger.info(f"Found {len(all_proxies)} unique proxies after deduplication")
    
    # Cek proxy
    valid_proxies = {'http': [], 'socks4': [], 'socks5': []}
    async with aiohttp.ClientSession() as session:
        for proxy in all_proxies:
            tasks = [
                check_proxy(session, proxy, 'http', semaphore),
                check_proxy(session, proxy, 'socks4', semaphore),
                check_proxy(session, proxy, 'socks5', semaphore)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for protocol, latency in results:
                if protocol and latency:
                    valid_proxies[protocol].append(f"{proxy} | Latency: {latency:.2f}s")
                    break  # Hentikan jika satu protokol valid
    
    # Simpan semua proxy valid
    all_valid = []
    for protocol, proxies in valid_proxies.items():
        all_valid.extend(proxies)
        await save_proxies(proxies, os.path.join(OUTPUT_DIR, f"{protocol}_validproxies.txt"))
    
    await save_proxies(all_valid, os.path.join(OUTPUT_DIR, "all_validproxies.txt"))
    logger.info(f"Total valid proxies: {len(all_valid)}")
    
    # Cek geo untuk proxy valid
    id_proxies = {'http': [], 'socks4': [], 'socks5': []}
    async with aiohttp.ClientSession() as session:
        for proxy in all_valid:
            ip = proxy.split('|')[0].strip()
            await asyncio.sleep(60 / GEO_RATE_LIMIT)  # Rate limit ip-api.com
            if await check_geo(ip, session, geo_semaphore):
                for protocol in valid_proxies:
                    if proxy in valid_proxies[protocol]:
                        id_proxies[protocol].append(proxy)
                        break
    
    # Simpan proxy Indonesia
    id_all_valid = []
    for protocol, proxies in id_proxies.items():
        id_all_valid.extend(proxies)
        await save_proxies(proxies, os.path.join(ID_DIR, f"ID-{protocol}_validproxies.txt"))
    
    await save_proxies(id_all_valid, os.path.join(ID_DIR, "ID-all_validproxies.txt"))
    logger.info(f"Total Indonesia proxies: {len(id_all_valid)}")

if __name__ == "__main__":
    asyncio.run(main())
