import logging
import time
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse
import urllib.robotparser
import httpx
from app.core.config import (
    CRAWL_TIMEOUT_SECONDS,
    MAX_CRAWL_PAGES,
)
from app.core.security import validate_url_security

logger = logging.getLogger(__name__)

USER_AGENT = "CampusGuideAI-Bot/1.0 (+http://astu.edu.et)"


def clean_url(url: str) -> str:
    """Normalize URL by stripping fragments and tracking query parameters."""
    parsed = urlparse(url.strip())
    # Remove tracking query parameters like utm_*
    clean_query = "&".join(
        q for q in parsed.query.split("&")
        if q and not q.lower().startswith(("utm_", "fbclid", "ref"))
    )
    # Rebuild URL
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path,
        parsed.params,
        clean_query,
        "",  # drop fragment
    ))


class CrawlerService:
    def __init__(self, timeout: int = CRAWL_TIMEOUT_SECONDS):
        self.timeout = timeout
        self._robot_parsers: Dict[str, urllib.robotparser.RobotFileParser] = {}

    def _get_robot_parser(self, base_url: str) -> Optional[urllib.robotparser.RobotFileParser]:
        """Fetch and parse robots.txt for a given domain safely."""
        parsed = urlparse(base_url)
        domain_key = f"{parsed.scheme}://{parsed.netloc}"

        if domain_key in self._robot_parsers:
            return self._robot_parsers[domain_key]

        robots_url = f"{domain_key}/robots.txt"
        is_safe, _ = validate_url_security(robots_url, check_approved_domain=True)
        if not is_safe:
            return None

        rp = urllib.robotparser.RobotFileParser()
        try:
            with httpx.Client(timeout=5.0, headers={"User-Agent": USER_AGENT}) as client:
                resp = client.get(robots_url)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    # If robots.txt returns 404 or other, all is allowed by standard
                    rp.allow_all = True
        except Exception as e:
            logger.info("Could not fetch robots.txt for %s: %s", domain_key, str(e))
            rp.allow_all = True

        self._robot_parsers[domain_key] = rp
        return rp

    def is_allowed_by_robots(self, url: str) -> bool:
        """Check if URL is permitted by robots.txt."""
        rp = self._get_robot_parser(url)
        if rp is None:
            return False
        return rp.can_fetch(USER_AGENT, url)

    def fetch_url_safely(
        self,
        url: str,
        expected_content_types: Optional[Tuple[str, ...]] = None,
    ) -> Tuple[bool, Optional[httpx.Response], str]:
        """
        Fetch a URL with SSRF protection, robots.txt adherence, and status verification.
        Returns (success, response_object, error_message).
        """
        cleaned = clean_url(url)

        # 1. SSRF and Domain security check
        is_safe, error_reason = validate_url_security(cleaned, check_approved_domain=True)
        if not is_safe:
            return False, None, f"Security check failed: {error_reason}"

        # 2. Robots.txt check
        if not self.is_allowed_by_robots(cleaned):
            return False, None, f"Access disallowed by website robots.txt: {cleaned}"

        # 3. HTTP Request with redirect protection
        try:
            # We follow redirects manually or validate each redirect hop to avoid SSRF redirect attacks
            current_url = cleaned
            redirect_count = 0
            max_redirects = 3

            with httpx.Client(
                timeout=self.timeout,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=False,
            ) as client:
                while redirect_count <= max_redirects:
                    resp = client.get(current_url)

                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            return False, None, "Redirect without Location header."
                        next_url = clean_url(urljoin(current_url, location))
                        # Validate next URL against SSRF and domain
                        is_next_safe, next_reason = validate_url_security(next_url, check_approved_domain=True)
                        if not is_next_safe:
                            return False, None, f"Redirect to unsafe destination blocked: {next_reason}"
                        current_url = next_url
                        redirect_count += 1
                        continue

                    # Final response reached
                    if resp.status_code != 200:
                        return False, None, f"HTTP status error: {resp.status_code} {resp.reason_phrase}"

                    # Verify Content-Type
                    ct = resp.headers.get("content-type", "").lower()
                    if expected_content_types:
                        if not any(expected in ct for expected in expected_content_types):
                            return False, None, f"Unexpected content-type '{ct}'. Expected one of {expected_content_types}"

                    return True, resp, ""

                return False, None, "Too many redirects encountered."

        except httpx.TimeoutException:
            return False, None, f"Request timed out after {self.timeout}s."
        except httpx.ConnectError:
            return False, None, "Connection failed. Host may be offline or unreachable."
        except Exception as e:
            return False, None, f"Request failed: {str(e)}"

    def discover_and_validate_pdf_links(self, base_url: str, pdf_hrefs: List[str]) -> List[str]:
        """Convert relative PDF links to absolute URLs and validate security/domain."""
        valid_pdf_urls: List[str] = []
        for href in pdf_hrefs:
            try:
                full_url = clean_url(urljoin(base_url, href))
                is_safe, _ = validate_url_security(full_url, check_approved_domain=True)
                if is_safe and full_url not in valid_pdf_urls:
                    valid_pdf_urls.append(full_url)
            except Exception:
                continue
        return valid_pdf_urls


# Global singleton instance
crawler = CrawlerService()
