from unittest.mock import MagicMock, patch
import httpx
import pytest
from app.core.security import is_domain_approved, is_ip_allowed, validate_url_security
from app.services.crawler import clean_url, crawler


def test_ip_filtering_ssrf():
    # Loopback
    assert is_ip_allowed("127.0.0.1") is False
    assert is_ip_allowed("127.0.1.1") is False
    assert is_ip_allowed("::1") is False

    # Private ranges
    assert is_ip_allowed("10.0.0.1") is False
    assert is_ip_allowed("172.16.0.1") is False
    assert is_ip_allowed("192.168.1.1") is False

    # Cloud metadata
    assert is_ip_allowed("169.254.169.254") is False
    assert is_ip_allowed("169.254.170.2") is False

    # Public IP
    assert is_ip_allowed("8.8.8.8") is True
    assert is_ip_allowed("1.1.1.1") is True


def test_domain_approval_check():
    assert is_domain_approved("astu.edu.et") is True
    assert is_domain_approved("www.astu.edu.et") is True
    assert is_domain_approved("portal.astu.edu.et") is True
    assert is_domain_approved("fakeastu.edu.et.attacker.com") is False
    assert is_domain_approved("google.com") is False
    assert is_domain_approved("localhost") is False


def test_validate_url_security():
    # Loopback URL
    safe, msg = validate_url_security("http://127.0.0.1/admin")
    assert safe is False
    assert "not in the approved ASTU domain list" in msg or "unsafe or private IP" in msg

    # Unapproved external URL
    safe, msg = validate_url_security("https://google.com/search")
    assert safe is False
    assert "not in the approved ASTU domain list" in msg

    # Embedded credentials
    safe, msg = validate_url_security("https://user:password@www.astu.edu.et/page")
    assert safe is False
    assert "Credentials" in msg

    # Non-HTTP protocol
    safe, msg = validate_url_security("file:///etc/passwd")
    assert safe is False
    assert "Only HTTP and HTTPS" in msg


def test_clean_url():
    raw = "https://www.astu.edu.et/admission/calendar?utm_source=facebook&utm_medium=cpc#dates"
    cleaned = clean_url(raw)
    assert "utm_source" not in cleaned
    assert "#dates" not in cleaned
    assert cleaned == "https://www.astu.edu.et/admission/calendar"


@patch("httpx.Client.get")
def test_crawler_fetch_url_success(mock_get):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.is_redirect = False
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
    mock_resp.text = "<html><head><title>ASTU</title></head><body><main><p>Valid content</p></main></body></html>"
    mock_get.return_value = mock_resp

    with patch("app.services.crawler.validate_url_security", return_value=(True, "")):
        with patch.object(crawler, "is_allowed_by_robots", return_value=True):
            success, resp, err = crawler.fetch_url_safely("https://www.astu.edu.et/page")
            assert success is True
            assert resp is not None
            assert err == ""
            assert "Valid content" in resp.text


@patch("httpx.Client.get")
def test_crawler_handles_inaccessible_page(mock_get):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.is_redirect = False
    mock_resp.status_code = 404
    mock_resp.reason_phrase = "Not Found"
    mock_get.return_value = mock_resp

    with patch("app.services.crawler.validate_url_security", return_value=(True, "")):
        with patch.object(crawler, "is_allowed_by_robots", return_value=True):
            success, resp, err = crawler.fetch_url_safely("https://www.astu.edu.et/missing")
            assert success is False
            assert resp is None
            assert "HTTP status error: 404 Not Found" in err


def test_crawler_robots_disallow():
    with patch("app.services.crawler.validate_url_security", return_value=(True, "")):
        with patch.object(crawler, "is_allowed_by_robots", return_value=False):
            success, resp, err = crawler.fetch_url_safely("https://www.astu.edu.et/private/admin")
            assert success is False
            assert resp is None
            assert "disallowed by website robots.txt" in err
