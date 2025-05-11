import aiohttp
import asyncio
import logging
import os
from datetime import datetime
from aiohttp_socks import ProxyConnector

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

class ProxyScraper:
    def __init__(self):
        self.proxy_sources = self._load_sources()
        self.rate_limit = asyncio.Semaphore(40)  # 40 req/minute
        self.session = None
        self.results = {
            'http': [], 'socks4': [], 'socks5': [],
            'id_http': [], 'id_socks4': [], 'id_socks5': []
        }

    def _load_sources(self):
        with open('src/proxies.txt', 'r') as f:
            return [line.strip() for line in f if line.strip()]

    async def _get_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session

    async def scrape_proxies(self):
        logging.info("Mulai scraping dari %d sumber...", len(self.proxy_sources))
        tasks = [self._fetch_proxies(url) for url in self.proxy_sources]
        proxy_lists = await asyncio.gather(*tasks)
        return list(set().union(*proxy_lists))  # Dedup

    async def _fetch_proxies(self, url):
        try:
            async with (await self._get_session()).get(url, timeout=10) as res:
                text = await res.text()
                return [line.strip() for line in text.split('\n') if line.strip()]
        except Exception as e:
            logging.warning(f"Gagal scrape {url}: {str(e)}")
            return []

    async def check_proxy(self, proxy):
        proxy_type = self._guess_proxy_type(proxy)
        try:
            connector = ProxyConnector.from_url(f"{proxy_type}://{proxy}")
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    "http://example.com", 
                    timeout=5
                ) as res:
                    if res.status == 200:
                        return proxy, proxy_type
        except:
            return None, None

    async def check_country(self, proxy):
        ip = proxy.split(':')[0]
        async with self.rate_limit:
            try:
                async with (await self._get_session()).get(
                    f"http://ip-api.com/json/{ip}?fields=countryCode",
                    timeout=3
                ) as res:
                    data = await res.json()
                    return data.get('countryCode') == 'ID'
            except:
                return False

    def _guess_proxy_type(self, proxy):
        port = proxy.split(':')[1]
        if port in ['1080', '9050']:
            return 'socks5'
        elif port in ['1081', '4145']:
            return 'socks4'
        return 'http'

    async def run(self):
        proxies = await self.scrape_proxies()
        logging.info("Total %d proxy unik ditemukan", len(proxies))

        # Step 1: Cek live proxy
        live_proxies = []
        tasks = [self.check_proxy(p) for p in proxies]
        for future in asyncio.as_completed(tasks):
            proxy, ptype = await future
            if proxy:
                live_proxies.append((proxy, ptype))

        # Step 2: Cek country untuk proxy live
        id_proxies = []
        tasks = [self.check_country(p[0]) for p in live_proxies]
        for i, future in enumerate(asyncio.as_completed(tasks)):
            is_id = await future
            if is_id:
                id_proxies.append(live_proxies[i])

        # Klasifikasi hasil
        for proxy, ptype in live_proxies:
            self.results[ptype].append(proxy)
        for proxy, ptype in id_proxies:
            self.results[f'id_{ptype}'].append(proxy)

        # Simpan hasil
        self._save_results()

    def _save_results(self):
        os.makedirs('live-proxy/ID', exist_ok=True)
        for ptype in ['http', 'socks4', 'socks5']:
            with open(f'live-proxy/{ptype}.txt', 'w') as f:
                f.write('\n'.join(self.results[ptype]))
            with open(f'live-proxy/ID/{ptype}.txt', 'w') as f:
                f.write('\n'.join(self.results[f'id_{ptype}']))

        logging.info(
            "Selesai! Valid: HTTP=%d, SOCKS4=%d, SOCKS5=%d | ID: HTTP=%d, SOCKS4=%d, SOCKS5=%d",
            len(self.results['http']), len(self.results['socks4']), 
            len(self.results['socks5']), len(self.results['id_http']), 
            len(self.results['id_socks4']), len(self.results['id_socks5'])
        )

if __name__ == "__main__":
    scraper = ProxyScraper()
    asyncio.run(scraper.run())
