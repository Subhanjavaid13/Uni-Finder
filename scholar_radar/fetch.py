"""Polite HTTP fetching: robots.txt aware, per-host delay, HTML -> clean text."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; ScholarRadar/0.1; personal scholarship tracker)"
REMOVE_TAGS = ["script", "style", "noscript", "svg", "iframe", "form", "nav", "footer"]


@dataclass
class Page:
    url: str
    title: str
    text: str
    links: list[tuple[str, str]] = field(default_factory=list)  # (link text, absolute url)


def html_to_page(html: str, url: str, max_chars: int = 30000) -> Page:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""

    links: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        if href.startswith("http"):
            links.append((a.get_text(" ", strip=True), href.split("#")[0]))

    for tag in soup(REMOVE_TAGS):
        tag.decompose()
    lines = (line.strip() for line in soup.get_text("\n").splitlines())
    text = "\n".join(line for line in lines if line)
    return Page(url=url, title=title, text=text[:max_chars], links=links)


class Fetcher:
    def __init__(self, timeout: int = 25, per_host_delay: float = 1.5,
                 respect_robots: bool = True, max_chars: int = 30000) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en"})
        self.timeout = timeout
        self.per_host_delay = per_host_delay
        self.respect_robots = respect_robots
        self.max_chars = max_chars
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self._last_hit: dict[str, float] = {}

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parts = urlparse(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            parser = robotparser.RobotFileParser()
            try:
                resp = self.session.get(f"{base}/robots.txt", timeout=10)
                if resp.status_code == 200:
                    parser.parse(resp.text.splitlines())
                    self._robots[base] = parser
                else:
                    self._robots[base] = None  # no robots.txt -> allowed
            except requests.RequestException:
                self._robots[base] = None
        parser = self._robots[base]
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    def _wait_for_host(self, url: str) -> None:
        host = urlparse(url).netloc
        elapsed = time.monotonic() - self._last_hit.get(host, 0.0)
        if elapsed < self.per_host_delay:
            time.sleep(self.per_host_delay - elapsed)
        self._last_hit[host] = time.monotonic()

    def get(self, url: str, retries: int = 2) -> requests.Response | None:
        if not self.allowed(url):
            log.info("robots.txt disallows %s - skipping", url)
            return None
        for attempt in range(retries + 1):
            self._wait_for_host(url)
            try:
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                    time.sleep(3 * (attempt + 1))
                    continue
                log.warning("HTTP %s for %s", resp.status_code, url)
                return None
            except requests.RequestException as exc:
                if attempt == retries:
                    log.warning("Failed to fetch %s: %s", url, exc)
                    return None
                time.sleep(2 * (attempt + 1))
        return None

    def fetch_page(self, url: str) -> Page | None:
        resp = self.get(url)
        if resp is None:
            return None
        content_type = resp.headers.get("Content-Type", "")
        if "html" not in content_type and "text" not in content_type:
            log.info("Skipping non-HTML content (%s) at %s", content_type, url)
            return None
        return html_to_page(resp.text, resp.url, self.max_chars)
