import asyncio
import aiohttp
import platform
import os
import re
import time
import logging
from datetime import datetime
from typing import List, Set
import socket
import uvloop

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Aktifkan uvloop untuk Linux
if platform.system() == "Linux":
    uvloop.install()
    logging.info("UVLoop activated for enhanced performance")

# Buat direktori proxy jika tidak ada
PROXY_DIR = "proxy"
if not os.path.exists(PROXY_DIR):
    os.makedirs(PROXY_DIR)

# File blacklist
BLACKLIST_FILE = "blacklist.txt"

class Proxy:
    __slots__ = ("ip", "port", "protocol", "latency")

    def __init__(self, ip: str, port: int, protocol: str, latency: float = 0):
        self.ip = ip
        self.port = port
        self.protocol = protocol
        self.latency = latency

    def __str__(self):
        return f"{self.protocol}://{self.ip}:{self.port}"

    def __eq__(self, other):
        if not isinstance(other, Proxy):
            return False
        return self.ip == other.ip and self.port == other.port

    def __hash__(self):
        return hash((self.ip, self.port))

class ProxyScraper:
    def __init__(self):
        self.sources = self.load_sources()
        self.session = None
        self.max_connections = 500
        self.semaphore = asyncio.Semaphore(self.max_connections)
        self.ip_pattern = re.compile(r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$")
        self.seen_proxies = set()
        self.latency_limit = 1500
        self.batch_size = 500  # Maksimalkan untuk 90% CPU/RAM
        self.blacklist = self.load_blacklist()

    def load_blacklist(self) -> Set[tuple]:
        blacklist = set()
        if os.path.exists(BLACKLIST_FILE):
            with open(BLACKLIST_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if ":" in line:
                        ip, port = line.split(":")
                        blacklist.add((ip, int(port)))
        logging.info(f"Loaded {len(blacklist)} proxies from blacklist")
        return blacklist

    def load_sources(self) -> dict:
        sources = {"http": [], "socks4": [], "socks5": []}
        try:
            with open("sites.txt", "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or not line.startswith("http"):
                        continue
                    if "socks4" in line.lower():
                        sources["socks4"].append(line)
                    elif "socks5" in line.lower():
                        sources["socks5"].append(line)
                    else:
                        sources["http"].append(line)
        except FileNotFoundError:
            logging.error("sites.txt not found, exiting")
            raise
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
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124",
                    "Accept": "*/*",
                    "Connection": "close",
                    "Accept-Encoding": "gzip, deflate",
                    "Cache-Control": "no-cache"
                }
            )

    async def fetch_proxies(self, url: str, protocol: str) -> Set[Proxy]:
        proxies = set()
        try:
            async with self.session.get(url, timeout=3) as response:
                if response.status == 200:
                    content = await response.text()
                    for line in content.splitlines():
                        if ":" in line:
                            try:
                                ip, port = line.strip().split(":")
                                port = int(port)
                                if self.is_valid_ip(ip) and self.is_valid_port(port) and (ip, port) not in self.blacklist:
                                    proxy = Proxy(ip, port, protocol)
                                    if proxy not in self.seen_proxies:
                                        self.seen_proxies.add(proxy)
                                        proxies.add(proxy)
                            except:
                                continue
            logging.info(f"Fetched {len(proxies)} proxies from {url}")
            return proxies
        except Exception as e:
            logging.error(f"Failed to fetch from {url}: {str(e)}")
            return set()

    def is_valid_ip(self, ip: str) -> bool:
        return bool(self.ip_pattern.match(ip))

    def is_valid_port(self, port: int) -> bool:
        return 0 < port < 65536

    async def check_proxy(self, proxy: Proxy) -> bool:
        if not self.session:
            await self.init_session()
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
                    proxy=f"{proxy.protocol}://{proxy.ip}:{self.port}",
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

    async def verify_proxies(self, proxies: List[Proxy]) -> tuple[List[Proxy], List[Proxy]]:
        verified = []
        invalid = []
        total = len(proxies)
        processed = 0
        for i in range(0, total, self.batch_size):
            batch = proxies[i:i + self.batch_size]
            tasks = [self.check_proxy(proxy) for proxy in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for proxy, result in zip(batch, results):
                if isinstance(result, bool) and result:
                    verified.append(proxy)
                else:
                    invalid.append(proxy)
                processed += 1
                if processed % 100 == 0:
                    logging.info(f"Processed {processed}/{total} proxies")
            await asyncio.sleep(0.2)
        logging.info(f"Verified {len(verified)} proxies, {len(invalid)} invalid")
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
        logging.info(f"Scraped {len(all_proxies)} unique proxies")
        return list(all_proxies)

    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def save_proxies(self, proxies: List[Proxy], invalid_proxies: List[Proxy]):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        all_file = os.path.join(PROXY_DIR, f"all-proxies_{timestamp}.txt")
        http_file = os.path.join(PROXY_DIR, f"http-proxies_{timestamp}.txt")
        socks4_file = os.path.join(PROXY_DIR, f"socks4-proxies_{timestamp}.txt")
        socks5_file = os.path.join(PROXY_DIR, f"socks5-proxies_{timestamp}.txt")
        blacklist_file = BLACKLIST_FILE

        with open(all_file, "w") as f:
            for proxy in sorted(proxies, key=lambda x: x.latency):
                f.write(f"{proxy}\n")
        logging.info(f"Saved {len(proxies)} proxies to {all_file}")

        with open(http_file, "w") as f:
            for proxy in sorted(proxies, key=lambda x: x.latency):
                if proxy.protocol == "http":
                    f.write(f"{proxy}\n")
        logging.info(f"Saved HTTP proxies to {http_file}")

        with open(socks4_file, "w") as f:
            for proxy in sorted(proxies, key=lambda x: x.latency):
                if proxy.protocol == "socks4":
                    f.write(f"{proxy}\n")
        logging.info(f"Saved SOCKS4 proxies to {socks4_file}")

        with open(socks5_file, "w") as f:
            for proxy in sorted(proxies, key=lambda x: x.latency):
                if proxy.protocol == "socks5":
                    f.write(f"{proxy}\n")
        logging.info(f"Saved SOCKS5 proxies to {socks5_file}")

        with open(blacklist_file, "a") as f:
            for proxy in invalid_proxies:
                f.write(f"{proxy.ip}:{proxy.port}\n")
        logging.info(f"Appended {len(invalid_proxies)} proxies to {blacklist_file}")

async def main():
    async with ProxyScraper() as scraper:
        protocols = ["http", "socks4", "socks5"]
        logging.info("Starting proxy scraping")
        proxies = await scraper.hyper_scrape(protocols)
        logging.info("Starting proxy verification")
        verified_proxies, invalid_proxies = await scraper.verify_proxies(proxies)
        scraper.save_proxies(verified_proxies, invalid_proxies)

if __name__ == "__main__":
    asyncio.run(main())
