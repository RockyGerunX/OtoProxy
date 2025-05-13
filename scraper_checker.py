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
SCRAPE_TIMEOUT = 3  # Timeout untuk scraping
CHECK_TIMEOUT = 7  # Timeout untuk checking proxy
TEST_URL = "http://httpbin.org/ip"  # Situs untuk tes proxy
OUTPUT_DIR = "result"
PROXY_REGEX = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})')

async def fetch_url(session, url, semaphore):
    async with semaphore:
        try:
            async with session.get(url, timeout=SCRAPE_TIMEOUT) as response:
                if response.status == 200:
                    return await response.text(), True
                else:
                    logger.error(f"Failed to fetch {url}: Status {response.status}")
                    return None, False
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None, False

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
                async with session.get(TEST_URL, proxy=proxy_url, timeout=CHECK_TIMEOUT) as response:
                    if response.status == 200:
                        latency = response.connection.transport.get_extra_info('latency', 0)
                        return protocol, latency
            else:
                connector = ProxyConnector.from_url(f"{protocol}://{proxy}")
                async with aiohttp.ClientSession(connector=connector) as socks_session:
                    async with socks_session.get(TEST_URL, timeout=CHECK_TIMEOUT) as response:
                        if response.status == 200:
                            latency = response.connection.transport.get_extra_info('latency', 0)
                            return protocol, latency
            return None, None
        except Exception:
            return None, None

async def save_proxies(proxies, filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as f:
        if not proxies:
            f.write("No valid proxies found.\n")
        else:
            for proxy in proxies:
                f.write(f"{proxy}\n")
    logger.info(f"Saved {len(proxies)} proxies to {filename}")

async def update_sources(urls, valid_urls):
    """Hapus URL yang error dari sources.txt."""
    with open('sources.txt', 'w') as f:
        for url in urls:
            if url in valid_urls:
                f.write(f"{url}\n")
    logger.info(f"Updated sources.txt with {len(valid_urls)} valid URLs")

async def initialize_dirs():
    """Buat folder result/ dan file kosong default."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for filename in [
        os.path.join(OUTPUT_DIR, "all_validproxies.txt"),
        os.path.join(OUTPUT_DIR, "http_validproxies.txt"),
        os.path.join(OUTPUT_DIR, "socks4_validproxies.txt"),
        os.path.join(OUTPUT_DIR, "socks5_validproxies.txt")
    ]:
        if not os.path.exists(filename):
            with open(filename, 'w') as f:
                f.write("No valid proxies found.\n")
            logger.info(f"Created empty file: {filename}")

async def main():
    # Inisialisasi folder
    await initialize_dirs()
    
    # Inisialisasi semaphore untuk kecepatan maksimal (batasi CPU/memori ~90%)
    semaphore = asyncio.Semaphore(100)  # 100 koneksi paralel
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
    valid_urls = set()
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=100)) as session:
        tasks = [fetch_url(session, url, semaphore) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for url, (html, success) in zip(urls, results):
            if success and html:
                valid_urls.add(url)
                proxies = await parse_proxies(html)
                all_proxies.update(proxies)
    
    # Update sources.txt (hapus URL error)
    if valid_urls:
        await update_sources(urls, valid_urls)
    
    logger.info(f"Found {len(all_proxies)} unique proxies after deduplication")
    
    # Cek proxy
    valid_proxies = {'http': [], 'socks4': [], 'socks5': []}
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=100)) as session:
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

if __name__ == "__main__":
    asyncio.run(main())
