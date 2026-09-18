"""
Namesniper - Steam Vanity / ID API Client
Checks availability of custom Steam profile vanity URLs (https://steamcommunity.com/id/<vanity>/).
Supports public XML inspection and optional Steam Web API resolution,
rate limiting, proxy routing, and exponential backoff.
"""
import time
import re
import random
import requests
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, List, Tuple

STEAM_COMMUNITY_URL = "https://steamcommunity.com/id"
STEAM_API_BASE = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001"
VANITY_REGEX = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")

class SteamAPIError(Exception):
    """Custom exception for Steam API errors."""
    pass

class SteamAPIClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        proxies: Optional[List[str]] = None,
        timeout: float = 10.0
    ):
        self.api_key = api_key.strip() if api_key else None
        self.proxies = [p.strip() for p in (proxies or []) if p.strip()]
        self.proxy_index = 0
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/xml, application/xml, text/html, */*"
        })

    def get_current_proxy(self) -> Optional[Dict[str, str]]:
        if not self.proxies:
            return None
        proxy_url = self.proxies[self.proxy_index % len(self.proxies)]
        return {"http": proxy_url, "https": proxy_url}

    def rotate_proxy(self) -> None:
        if len(self.proxies) > 1:
            self.proxy_index = (self.proxy_index + 1) % len(self.proxies)

    @staticmethod
    def validate_vanity(vanity: str) -> bool:
        """Steam vanity URLs must be 3-32 characters, alphanumeric, hyphen, or underscore."""
        if not vanity:
            return False
        return bool(VANITY_REGEX.match(vanity))

    def check_vanity(self, vanity: str, retries: int = 3) -> Dict[str, Any]:
        """
        Check availability of a Steam custom URL.
        Returns result dictionary with status: AVAILABLE, TAKEN, INVALID, or ERROR.
        """
        clean_vanity = vanity.strip()
        profile_url = f"{STEAM_COMMUNITY_URL}/{clean_vanity}/"

        if not self.validate_vanity(clean_vanity):
            return {
                "status": "INVALID",
                "vanity": clean_vanity,
                "length": len(clean_vanity),
                "steamid64": None,
                "profile_url": profile_url,
                "details": "Invalid length (must be 3-32 characters: letters, numbers, _)"
            }

        # If Steam Web API key is configured, use official API endpoint
        if self.api_key:
            return self._check_via_api(clean_vanity, profile_url, retries=retries)

        # Default: check via public community XML endpoint (zero configuration required)
        return self._check_via_community(clean_vanity, profile_url, retries=retries)

    def _check_via_community(self, vanity: str, profile_url: str, retries: int = 3) -> Dict[str, Any]:
        url = f"{STEAM_COMMUNITY_URL}/{vanity}/?xml=1"
        attempt = 0

        while attempt < retries:
            attempt += 1
            proxies = self.get_current_proxy()

            try:
                resp = self.session.get(url, timeout=self.timeout, proxies=proxies)

                if resp.status_code == 429 or (resp.status_code == 403 and "rate limit" in resp.text.lower()):
                    if len(self.proxies) > 1 and attempt < retries:
                        sleep_time = (2 ** attempt) + random.uniform(0.5, 1.5)
                        self.rotate_proxy()
                        time.sleep(sleep_time)
                        continue
                    return {
                        "status": "RATE_LIMITED",
                        "vanity": vanity,
                        "length": len(vanity),
                        "steamid64": None,
                        "profile_url": profile_url,
                        "details": "Steam rate limit reached (HTTP 429)"
                    }

                if resp.status_code == 404:
                    return {
                        "status": "AVAILABLE",
                        "vanity": vanity,
                        "length": len(vanity),
                        "steamid64": None,
                        "profile_url": profile_url,
                        "details": "Free to claim"
                    }

                if resp.status_code == 200:
                    text = resp.text
                    if "The specified profile could not be found" in text or "<response><error>" in text:
                        return {
                            "status": "AVAILABLE",
                            "vanity": vanity,
                            "length": len(vanity),
                            "steamid64": None,
                            "profile_url": profile_url,
                            "details": "Free to claim"
                        }

                    # Profile exists - parse steamID64
                    steamid64 = None
                    try:
                        match = re.search(r"<steamID64>(\d+)</steamID64>", text)
                        if match:
                            steamid64 = match.group(1)
                    except Exception:
                        pass

                    return {
                        "status": "TAKEN",
                        "vanity": vanity,
                        "length": len(vanity),
                        "steamid64": steamid64,
                        "profile_url": profile_url,
                        "details": "Registered account"
                    }

                # Other HTTP status
                if resp.status_code >= 500:
                    time.sleep(1.0)
                    continue

                return {
                    "status": "ERROR",
                    "vanity": vanity,
                    "length": len(vanity),
                    "steamid64": None,
                    "profile_url": profile_url,
                    "details": f"HTTP {resp.status_code}"
                }

            except (requests.exceptions.RequestException, Exception) as e:
                self.rotate_proxy()
                if attempt >= retries:
                    return {
                        "status": "ERROR",
                        "vanity": vanity,
                        "length": len(vanity),
                        "steamid64": None,
                        "profile_url": profile_url,
                        "details": f"Connection error: {type(e).__name__}"
                    }
                time.sleep(0.5)

        return {
            "status": "ERROR",
            "vanity": vanity,
            "length": len(vanity),
            "steamid64": None,
            "profile_url": profile_url,
            "details": "Max retries exceeded"
        }

    def _check_via_api(self, vanity: str, profile_url: str, retries: int = 3) -> Dict[str, Any]:
        params = {
            "key": self.api_key,
            "vanityurl": vanity
        }
        attempt = 0

        while attempt < retries:
            attempt += 1
            proxies = self.get_current_proxy()

            try:
                resp = self.session.get(STEAM_API_BASE, params=params, timeout=self.timeout, proxies=proxies)

                if resp.status_code == 429 or (resp.status_code == 403 and "rate limit" in resp.text.lower()):
                    if len(self.proxies) > 1 and attempt < retries:
                        sleep_time = (2 ** attempt) + random.uniform(0.5, 1.5)
                        self.rotate_proxy()
                        time.sleep(sleep_time)
                        continue
                    return {
                        "status": "RATE_LIMITED",
                        "vanity": vanity,
                        "length": len(vanity),
                        "steamid64": None,
                        "profile_url": profile_url,
                        "details": "Steam rate limit reached (HTTP 429)"
                    }

                if resp.status_code == 200:
                    data = resp.json().get("response", {})
                    success = data.get("success")

                    if success == 42:
                        # 42 = No match (Available)
                        return {
                            "status": "AVAILABLE",
                            "vanity": vanity,
                            "length": len(vanity),
                            "steamid64": None,
                            "profile_url": profile_url,
                            "details": "Free to claim"
                        }
                    elif success == 1:
                        # 1 = Match found (Taken)
                        return {
                            "status": "TAKEN",
                            "vanity": vanity,
                            "length": len(vanity),
                            "steamid64": data.get("steamid"),
                            "profile_url": profile_url,
                            "details": "Registered account"
                        }

                if resp.status_code >= 500:
                    time.sleep(1.0)
                    continue

                return {
                    "status": "ERROR",
                    "vanity": vanity,
                    "length": len(vanity),
                    "steamid64": None,
                    "profile_url": profile_url,
                    "details": f"HTTP {resp.status_code}"
                }

            except (requests.exceptions.RequestException, Exception) as e:
                self.rotate_proxy()
                if attempt >= retries:
                    return {
                        "status": "ERROR",
                        "vanity": vanity,
                        "length": len(vanity),
                        "steamid64": None,
                        "profile_url": profile_url,
                        "details": f"Connection error: {type(e).__name__}"
                    }
                time.sleep(0.5)

        return {
            "status": "ERROR",
            "vanity": vanity,
            "length": len(vanity),
            "steamid64": None,
            "profile_url": profile_url,
            "details": "Max retries exceeded"
        }

    def test_api_key(self, api_key: str) -> Tuple[bool, str]:
        """Test if a given Steam API key is valid."""
        api_key = api_key.strip()
        if not api_key:
            return False, "API key is empty."

        try:
            params = {"key": api_key, "vanityurl": "gaben"}
            resp = requests.get(STEAM_API_BASE, params=params, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json().get("response", {})
                if data.get("success") == 1:
                    return True, "Valid Steam Web API key."
                return False, f"Unexpected response: {data}"
            elif resp.status_code in (401, 403):
                return False, "Invalid Steam Web API key (Unauthorized)."
            else:
                return False, f"HTTP {resp.status_code} error testing key."
        except Exception as e:
            return False, f"Connection error: {e}"
