"""
Namesniper - Faceit API Client
Handles API requests to the Faceit Data API v4, rate-limiting, key rotation,
status classification (AVAILABLE, CLAIMABLE_IDLE, TAKEN, INVALID), and error handling.
"""
import time
import re
import random
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

FACEIT_API_BASE = "https://open.faceit.com/data/v4"
NICKNAME_REGEX = re.compile(r"^[a-zA-Z0-9_-]{3,12}$")

class FaceitAPIError(Exception):
    """Custom exception for Faceit API errors."""
    pass

class FaceitAPIClient:
    def __init__(
        self,
        api_keys: Optional[List[str]] = None,
        proxies: Optional[List[str]] = None,
        timeout: float = 10.0,
        detect_idle: bool = True
    ):
        self.api_keys = [k.strip() for k in (api_keys or []) if k.strip()]
        self.key_index = 0
        self.proxies = [p.strip() for p in (proxies or []) if p.strip()]
        self.proxy_index = 0
        self.timeout = timeout
        self.detect_idle = detect_idle
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "Namesniper-FaceitChecker/2.0"
        })

    def get_current_key(self) -> Optional[str]:
        if not self.api_keys:
            return None
        return self.api_keys[self.key_index % len(self.api_keys)]

    def rotate_key(self) -> Optional[str]:
        if len(self.api_keys) > 1:
            self.key_index = (self.key_index + 1) % len(self.api_keys)
            return self.get_current_key()
        return self.get_current_key()

    def get_current_proxy(self) -> Optional[Dict[str, str]]:
        if not self.proxies:
            return None
        proxy_url = self.proxies[self.proxy_index % len(self.proxies)]
        return {"http": proxy_url, "https": proxy_url}

    def rotate_proxy(self) -> None:
        if len(self.proxies) > 1:
            self.proxy_index = (self.proxy_index + 1) % len(self.proxies)

    @staticmethod
    def validate_nickname(nickname: str) -> bool:
        """Validate if a nickname satisfies Faceit's username constraints (3-12 chars, [a-zA-Z0-9_-])."""
        if not nickname:
            return False
        return bool(NICKNAME_REGEX.match(nickname))

    @staticmethod
    def parse_creation_date(date_str: Optional[str]) -> Tuple[Optional[str], float, bool]:
        """Parse Faceit activated_at timestamp, return (formatted_date, age_years, is_older_than_1_year)."""
        if not date_str:
            return None, 0.0, False
        try:
            clean_str = date_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
            now = datetime.now(timezone.utc)
            days = (now - dt).days
            years = round(days / 365.25, 1)
            is_older_than_1_year = (days >= 365)
            formatted_date = dt.strftime("%Y-%m-%d")
            return formatted_date, years, is_older_than_1_year
        except Exception:
            return None, 0.0, False

    def test_api_key(self, api_key: str) -> Tuple[bool, str]:
        """Test if a given API key is valid by querying a known Faceit player."""
        api_key = api_key.strip()
        if not api_key:
            return False, "API key is empty."
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "Namesniper-FaceitChecker/2.0"
        }
        
        try:
            url = f"{FACEIT_API_BASE}/games?limit=1"
            resp = requests.get(url, headers=headers, timeout=10.0)
            if resp.status_code == 200:
                return True, "Key verified! Successfully connected to Faceit Data API."
            elif resp.status_code in (401, 403) or (resp.status_code == 400 and "invalid_token" in resp.text):
                return False, f"Authorization failed (HTTP {resp.status_code}). Invalid or unrecognized Faceit API key."
            elif resp.status_code == 429:
                return False, "Rate limit reached (HTTP 429). Please wait a moment."
            else:
                return False, f"Unexpected response (HTTP {resp.status_code}): {resp.text[:100]}"
        except requests.exceptions.RequestException as e:
            return False, f"Connection failed: {str(e)}"

    def check_nickname(self, nickname: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Check nickname availability against Faceit Data API v4.
        Returns a dict:
        {
            "nickname": str,
            "status": "AVAILABLE" | "CLAIMABLE_IDLE" | "TAKEN" | "INVALID" | "ERROR",
            "length": int,
            "player_id": str | None,
            "country": str | None,
            "faceit_elo": int | None,
            "faceit_url": str | None,
            "games_count": int,
            "details": str
        }
        """
        nickname = nickname.strip()
        result_template = {
            "nickname": nickname,
            "status": "ERROR",
            "length": len(nickname),
            "player_id": None,
            "country": None,
            "faceit_elo": None,
            "faceit_url": None,
            "games_count": 0,
            "account_created_at": None,
            "account_age_years": 0.0,
            "older_than_1_year": False,
            "details": ""
        }

        # 1. Syntax validation
        if not self.validate_nickname(nickname):
            result_template["status"] = "INVALID"
            result_template["details"] = "Invalid format: Must be 3-12 alphanumeric characters, hyphens or underscores."
            return result_template

        # 2. Key check
        current_key = self.get_current_key()
        if not current_key:
            result_template["status"] = "ERROR"
            result_template["details"] = "No Faceit API key provided. Please add an API key in Settings."
            return result_template

        url = f"{FACEIT_API_BASE}/search/players?nickname={nickname}&limit=20"

        retries = 0
        backoff_delay = 1.0

        while retries <= max_retries:
            headers = {
                "Authorization": f"Bearer {current_key}",
                "Accept": "application/json",
                "User-Agent": "Namesniper-FaceitChecker/2.0"
            }
            proxies = self.get_current_proxy()

            try:
                resp = self.session.get(url, headers=headers, proxies=proxies, timeout=self.timeout)

                # HTTP 404: Not Found -> Available!
                if resp.status_code == 404:
                    result_template["status"] = "AVAILABLE"
                    result_template["details"] = "Username is not taken on Faceit and is available for registration."
                    return result_template

                # HTTP 200: Search succeeded -> Look for case-insensitive exact match
                elif resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", []) or []

                    target_lower = nickname.lower()
                    exact_match = None
                    for item in items:
                        if item.get("nickname", "").lower() == target_lower:
                            exact_match = item
                            break

                    if exact_match:
                        # Found existing account with exact case-insensitive match!
                        real_nickname = exact_match.get("nickname", nickname)
                        player_id = exact_match.get("player_id")
                        country = exact_match.get("country")
                        games = exact_match.get("games", []) or []
                        games_count = len(games)

                        account_created_at = None
                        account_age_years = 0.0
                        older_than_1_year = False

                        # Query full player profile by UUID to retrieve activated_at (creation date)
                        if player_id:
                            try:
                                p_url = f"{FACEIT_API_BASE}/players/{player_id}"
                                p_resp = self.session.get(p_url, headers=headers, proxies=proxies, timeout=self.timeout)
                                if p_resp.status_code == 200:
                                    p_data = p_resp.json()
                                    raw_activated = p_data.get("activated_at")
                                    account_created_at, account_age_years, older_than_1_year = self.parse_creation_date(raw_activated)

                                    # Check games in full profile
                                    prof_games = p_data.get("games", {}) or {}
                                    if prof_games:
                                        games_count = max(games_count, len(prof_games))
                                        if "cs2" in prof_games and prof_games["cs2"].get("faceit_elo"):
                                            result_template["faceit_elo"] = prof_games["cs2"].get("faceit_elo")
                                        elif "csgo" in prof_games and prof_games["csgo"].get("faceit_elo"):
                                            result_template["faceit_elo"] = prof_games["csgo"].get("faceit_elo")
                            except Exception:
                                pass

                        faceit_url = f"https://www.faceit.com/en/players/{real_nickname}"
                        result_template["nickname"] = real_nickname
                        result_template["length"] = len(real_nickname)
                        result_template["player_id"] = player_id
                        result_template["country"] = country
                        result_template["faceit_url"] = faceit_url
                        result_template["games_count"] = games_count
                        result_template["account_created_at"] = account_created_at
                        result_template["account_age_years"] = account_age_years
                        result_template["older_than_1_year"] = older_than_1_year

                        # Extract skill level from search data if available
                        cs_game = next((g for g in games if g.get("name") in ("cs2", "csgo")), None)
                        skill_level = cs_game.get("skill_level") if cs_game else None

                        # Idle Account Check:
                        # Must have 0 games AND be created MORE THAN 1 YEAR AGO
                        if self.detect_idle and games_count == 0:
                            if older_than_1_year:
                                result_template["status"] = "CLAIMABLE_IDLE"
                                age_desc = f"Created: {account_created_at} ({account_age_years}y ago)" if account_created_at else "Old account (>1y)"
                                result_template["details"] = f"Idle account ({age_desc}, 0 games). Eligible for Faceit idle claim!"
                            else:
                                result_template["status"] = "TAKEN"
                                age_desc = f"Created: {account_created_at} (<1y ago)" if account_created_at else "New account (<1y)"
                                result_template["details"] = f"Fresh account ({age_desc}, 0 games). Too new to claim (<1 year old)."
                        else:
                            result_template["status"] = "TAKEN"
                            details_parts = []
                            if real_nickname != nickname:
                                details_parts.append(f"Registered as: {real_nickname}")
                            if account_created_at:
                                details_parts.append(f"Created: {account_created_at} ({account_age_years}y)")
                            if country:
                                details_parts.append(f"Region: {country.upper()}")
                            if result_template.get("faceit_elo"):
                                details_parts.append(f"ELO: {result_template['faceit_elo']}")
                            elif skill_level and skill_level != "0":
                                details_parts.append(f"Skill: Lvl {skill_level}")
                            details_parts.append(f"Games: {games_count}")
                            result_template["details"] = ", ".join(details_parts) if details_parts else "Active account"

                        return result_template

                    else:
                        # No exact match found among search items -> Name is AVAILABLE!
                        result_template["status"] = "AVAILABLE"
                        result_template["details"] = "Username is not taken on Faceit and is available for registration."
                        return result_template

                # HTTP 429: Too Many Requests -> Backoff and rotate
                elif resp.status_code == 429:
                    retries += 1
                    retry_after = resp.headers.get("Retry-After")
                    sleep_time = float(retry_after) if retry_after else (backoff_delay + random.uniform(0.5, 1.5))
                    self.rotate_key()
                    self.rotate_proxy()
                    time.sleep(sleep_time)
                    backoff_delay *= 1.5
                    continue

                # HTTP 401 or 403: Unauthorized API Key
                elif resp.status_code in (401, 403):
                    result_template["status"] = "ERROR"
                    result_template["details"] = f"API Key unauthorized (HTTP {resp.status_code}). Check your Faceit API key."
                    return result_template

                # HTTP 400 or 422: Invalid request / bad parameters
                elif resp.status_code in (400, 422):
                    result_template["status"] = "INVALID"
                    result_template["details"] = f"Invalid username parameter (HTTP {resp.status_code})."
                    return result_template

                else:
                    retries += 1
                    time.sleep(1.0)
                    continue

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                retries += 1
                if self.proxies:
                    self.rotate_proxy()
                time.sleep(1.0)
                continue
            except Exception as e:
                result_template["status"] = "ERROR"
                result_template["details"] = f"Request error: {str(e)}"
                return result_template

        result_template["status"] = "ERROR"
        result_template["details"] = "Max retries exceeded (Rate limit or network instability)."
        return result_template
