import asyncio
import aiohttp
import platform
import os
import socket
import re
import time
import logging
from datetime import datetime
from diskcache import Cache
from typing import List, Set

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Konfigurasi UVLoop untuk Linux
if platform.system() == 'Linux':
    try:
        import uvloop
        uvloop.install()
        logger.info("UVLoop activated for enhanced performance")
    except ImportError:
        logger.warning("UVLoop not available, using standard event loop")

# Konfigurasi direktori cache
CACHE_DIR = './cache'
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# Konfigurasi cache
cache = Cache(CACHE_DIR, size_limit=int(1e9), ttl=1800)

class Proxy:
    __slots__ = ('ip', 'port', 'protocol', 'latency')

    def __init__(self, ip: str, port: int, protocol: str, latency: float = 0):
        self.ip = ip
        self.port = port
        self.protocol = protocol
        self.latency = latency

    def format(self) -> str:
        return f"{self.ip}:{self.port}"

    def __eq__(self, other):
        if not isinstance(other, Proxy):
            return False
        return (self.ip == other.ip and self.port == other.port)

    def __hash__(self):
        return hash((self.ip, self.port))

class ProxyScraper:
    def __init__(self):
        self.sources = self.load_sources()
        self.session = None
        self.max_connections = 500
        self.semaphore = asyncio.Semaphore(self.max_connections)
        self.ip_pattern = re.compile(r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$')
        self.seen_proxies = set()
        self.cache = Cache(CACHE_DIR, size_limit=int(1e9), ttl=1800)
        self.latency_limit = 1500
        self.batch_size = 1000  # Disesuaikan untuk 90% penggunaan CPU/RAM
        self.blacklist = self.load_blacklist()

    async def __aenter__(self):
        await self.init_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_session()
        self.cache.close()

    def is_valid_ip(self, ip: str) -> bool:
        return bool(self.ip_pattern.match(ip))

    def is_valid_port(self, port: int) -> bool:
        return 0 < port < 65536

    def load_blacklist(self) -> Set[str]:
        blacklist = set()
        try:
            if os.path.exists('blacklist.txt'):
                with open('blacklist.txt', 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            blacklist.add(line)
            logger.info(f"Loaded {len(blacklist)} blacklisted proxies")
        except Exception as e:
            logger.error(f"Error loading blacklist: {e}")
        return blacklist

    def load_sources(self) -> dict:
        sources = {'http': [], 'socks4': [], 'socks5': []}
        try:
            with open('sites.txt', 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or not line.startswith('http'):
                        continue
                    if 'socks4' in line.lower():
                        sources['socks4'].append(line)
                    elif 'socks5' in line.lower():
                        sources['socks5'].append(line)
                    else:
                        sources['http'].append(line)
            logger.info(f"Loaded sources: HTTP={len(sources['http'])}, SOCKS4={len(sources['socks4'])}, SOCKS5={len(sources['socks5'])}")
        except FileNotFoundError:
            logger.error("sites.txt not found, using default sources")
            sources = {
                'http': ["https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"],
                'socks4': ["https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt"],
                'socks5': ["https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt"]
            }
        return sources

    async def init_session(self):
        if not self.session:
            connector = aiohttp.TCPConnector(
                limit=self.max_connections,
                ttl_dns_cache=300,
                force_close=True,
                enable_cleanup_closed=True,
                use_dns_cache=True,
                ssl=False,
                limit_per_host=0,
                family=socket.AF_INET
            )
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=10, connect=2),
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124',
                    'Accept': '*/*',
                    'Connection': 'close'
                }
            )

    async def fetch_proxies(self, url: str, protocol: str) -> Set[Proxy]:
        cache_key = f"proxies_{url}_{protocol}"
        try:
            cached_proxies = self.cache.get(cache_key)
            if cached_proxies:
                logger.info(f"Using cached proxies for {url}")
                return cached_proxies
        except:
            pass

        proxies = set()
        try:
            async with self.session.get(url, timeout=3) as response:
                if response.status == 200:
                    content = await response.text()
                    for line in f:
                        if ':' in line:
                            try:
                                ip, port = line.strip().split(':')
                                port = int(port)
                                if self.is_valid_ip(ip) and self.is_valid_port(port):
                                    proxy_str = f"{ip}:{port}"
                                    if proxy_str not in self.blacklist:
                                        proxy = Proxy(ip, port, protocol)
                                        if proxy not in self.seen_proxies:
                                            self.seen_proxies.add(proxy)
                                            proxies.add(proxy)
                            except:
                                continue
            if proxies:
                self.cache.set(cache_key, proxies)
            logger.info(f"Fetched {len(proxies)} proxies from {url}")
            return proxies
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return set()

    async def check_proxy(self, proxy: Proxy) -> bool:
        test_urls = [
            "http://ip-api.com/json/",
            "http://httpbin.org/ip",
            "http://ipinfo.io/json"
        ]
        timeout = aiohttp.ClientTimeout(total=5.0)
        for url in test_urls:
            try:
                start_time = time.time()
                async with self.session.get(
                    url,
                    proxy=f"{proxy.protocol}://{proxy.ip}:{proxy.port}",
                    timeout=timeout,
                    allow_redirects=False,
                    ssl=False
                ) as response:
                    if response.status in [200, 201, 202]:
                        latency = (time.time() - start_time) * 1000
                        if latency < self.latency_limit:
                            proxy.latency = latency
                            return True
            except:
                continue
        return False

    async def verify_proxies(self, proxies: List[Proxy]) -> tuple[List[Proxy], List[str]]:
        verified = []
        invalid = []
        total = len(proxies)
        processed = 0
        alive = 0
        dead = 0

        for i in range(0, total, self.batch_size):
            batch = proxies[i:i + self.batch_size]
            tasks = [self.check_proxy(proxy) for proxy in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for proxy, result in zip(batch, results):
                proxy_str = proxy.format()
                if isinstance(result, bool) and result:
                    verified.append(proxy)
                    alive += 1
                else:
                    invalid.append(proxy_str)
                    dead += 1
                processed += 1
                if processed % 100 == 0:
                    logger.info(f"Stats: Total={total}, Alive={alive}, Dead={dead}, Progress={int(processed/total*100)}%")
            await asyncio.sleep(0.2)

        logger.info(f"Verification complete: Total={total}, Alive={alive}, Dead={dead}")
        return verified, invalid

    async def hyper_scrape(self, protocols: List[str]) -> List[Proxy]:
        tasks = []
        for protocol in protocols:
            for url in self.sources.get(protocol, []):
                tasks.append(self.fetch_proxies(url, protocol))
        results = await asyncio.gather(*tasks)
        all_proxies = set()
        for proxy_set in results:
            all_proxies.update(proxy_set)
        logger.info(f"Scraped {len(all_proxies)} unique proxies")
        return list(all_proxies)

    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def save_proxies(self, proxies: List[Proxy], invalid_proxies: List[str]):
        # Buat file output
        all_proxies = []
        http_proxies = []
        socks4_proxies = []
        socks5_proxies = []

        for proxy in sorted(proxies, key=lambda x: x.latency):
            proxy_str = proxy.format()
            all_proxies.append(proxy_str)
            if proxy.protocol == 'http':
                http_proxies.append(proxy_str)
            elif proxy.protocol == 'socks4':
                socks4_proxies.append(proxy_str)
            elif proxy.protocol == 'socks5':
                socks5_proxies.append(proxy_str)

        # Simpan ke file
        for filename, data in [
            ('all-proxies.txt', all_proxies),
            ('http-proxies.txt', http_proxies),
            ('socks4-proxies.txt', socks4_proxies),
            ('socks5-proxies.txt', socks5_proxies),
            ('blacklist.txt', invalid_proxies)
        ]:
            with open(filename, 'w') as f:
                f.write('\n'.join(data) + '\n')
            logger.info(f"Saved {len(data)} entries to {filename}")

async def main():
    async with ProxyScraper() as scraper:
        try:
            logger.info("Starting OtoProxy")
            proxies = await scraper.hyper_scrape(['http', 'socks4', 'socks5'])
            logger.info("Verifying proxies")
            verified_proxies, invalid_proxies = await scraper.verify_proxies(proxies)
            logger.info("Saving results")
            scraper.save_proxies(verified_proxies, invalid_proxies)
            logger.info("OtoProxy completed")
        except Exception as e:
            logger.error(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
