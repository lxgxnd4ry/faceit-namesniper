"""
Namesniper - GUI Window & JS Bridge Module
Integrates pywebview Edge Chromium window with Python checker engine and database.
"""
import os
import json
import webview
from pathlib import Path
from typing import Dict, Any, List

from config import BASE_DIR, RESOURCE_DIR, WORDLISTS_DIR, EXPORTS_DIR, load_config, save_config, get_wordlist_path
from database import Database, SteamDatabase
from faceit_api import FaceitAPIClient
from generator import NameGenerator
from checker import CheckerEngine
from steam_api import SteamAPIClient
from steam_checker import SteamCheckerEngine

class NamesniperAPI:
    def __init__(self):
        self._config = load_config()
        self._database = Database()
        self._steam_database = SteamDatabase()
        self._api_client = FaceitAPIClient(
            api_keys=self._get_keys_from_config(),
            proxies=self._config.get("proxies", []),
            detect_idle=self._config.get("detect_idle_accounts", True)
        )
        self._steam_api_client = SteamAPIClient(
            api_key=self._config.get("steam_api_key", ""),
            proxies=self._config.get("proxies", [])
        )
        self._window = None
        self._engine = CheckerEngine(
            api_client=self._api_client,
            database=self._database,
            threads=self._config.get("threads", 3),
            delay_between_requests=self._config.get("delay_between_requests", 0.35),
            detect_idle=self._config.get("detect_idle_accounts", True),
            on_result=self._on_result,
            on_progress=self._on_progress,
            on_finish=self._on_finish
        )
        self._steam_engine = SteamCheckerEngine(
            api_client=self._steam_api_client,
            database=self._steam_database,
            threads=self._config.get("threads", 3),
            delay_between_requests=self._config.get("delay_between_requests", 0.35),
            save_taken=self._config.get("save_taken", False),
            on_result=self._on_steam_result,
            on_progress=self._on_steam_progress,
            on_finish=self._on_steam_finish
        )

    def set_window(self, window):
        self._window = window

    def _get_keys_from_config(self) -> List[str]:
        keys = []
        if self._config.get("active_key"):
            keys.append(self._config["active_key"])
        for k in self._config.get("api_keys", []):
            if k not in keys:
                keys.append(k)
        return keys

    def _on_result(self, result: Dict[str, Any]) -> None:
        if self._window:
            self._window.evaluate_js(f"window.onCheckerResult({json.dumps(result)})")

    def _on_progress(self, stats: Dict[str, Any]) -> None:
        if self._window:
            self._window.evaluate_js(f"window.onCheckerProgress({json.dumps(stats)})")

    def _on_finish(self) -> None:
        if self._window:
            self._window.evaluate_js("window.onCheckerFinish()")

    def _on_steam_result(self, result: Dict[str, Any]) -> None:
        if self._window:
            self._window.evaluate_js(f"window.onSteamResult({json.dumps(result)})")

    def _on_steam_progress(self, stats: Dict[str, Any]) -> None:
        if self._window:
            self._window.evaluate_js(f"window.onSteamProgress({json.dumps(stats)})")

    def _on_steam_finish(self) -> None:
        if self._window:
            self._window.evaluate_js("window.onSteamFinish()")

    def get_config(self) -> Dict[str, Any]:
        """Return current configuration to frontend."""
        return self._config

    def save_config(self, new_cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Save updated configuration from frontend."""
        self._config.update(new_cfg)
        save_config(self._config)

        # Update engine and api client params
        keys = self._get_keys_from_config()
        self._api_client.api_keys = keys
        self._engine.num_threads = self._config.get("threads", 3)
        self._engine.delay = self._config.get("delay_between_requests", 0.35)
        self._engine.detect_idle = self._config.get("detect_idle_accounts", True)
        self._api_client.detect_idle = self._config.get("detect_idle_accounts", True)

        self._steam_api_client.api_key = self._config.get("steam_api_key", "").strip() or None
        self._steam_engine.num_threads = self._config.get("threads", 3)
        self._steam_engine.delay = self._config.get("delay_between_requests", 0.35)
        self._steam_engine.save_taken = self._config.get("save_taken", False)

        return {"success": True}

    def test_api_key(self, api_key: str) -> Dict[str, Any]:
        """Verify an API key."""
        valid, message = self._api_client.test_api_key(api_key)
        return {"valid": valid, "message": message}

    def generate_words(self, mode: str, count: int = 500, pattern: str = "") -> Dict[str, Any]:
        """Generate candidate usernames based on chosen mode."""
        count = min(max(10, count), 5000)
        words = []
        if mode == "3l_cvc":
            words = NameGenerator.generate_3l_pronounceable(limit=count)
        elif mode == "4l_cvcv":
            words = NameGenerator.generate_4l_pronounceable(limit=count)
        elif mode == "compound":
            words = NameGenerator.generate_compound_words(count=count)
        elif mode == "custom_pattern":
            words = NameGenerator.generate_by_pattern(pattern or "CVCV", count=count)
        else:
            words = NameGenerator.generate_3l_pronounceable(limit=count)

        return {"words": words}

    def get_db_records(self, filter_status: str = "ALL", search: str = "") -> List[Dict[str, Any]]:
        """Fetch results stored in SQLite database."""
        return self._database.get_results(
            status_filter=filter_status if filter_status != "ALL" else None,
            limit=500,
            search_query=search.strip() if search.strip() else None
        )

    def clear_db(self) -> Dict[str, Any]:
        """Clear database cache."""
        self._database.clear_database()
        return {"success": True}

    def open_exports_dir(self) -> None:
        """Open exports folder in Windows Explorer."""
        try:
            os.startfile(str(EXPORTS_DIR))
        except Exception as e:
            print(f"Error opening folder: {e}")

    def open_url(self, url: str) -> None:
        """Open external URL in system default browser."""
        import webbrowser
        try:
            if url and (url.startswith("http://") or url.startswith("https://")):
                webbrowser.open(url)
        except Exception as e:
            print(f"Error opening URL: {e}")

    def _collect_names_for_source(self, source: str, custom_text: str = "") -> List[str]:
        """Collect names based on selected source (shared by Faceit and Steam)."""
        names = []
        if source == "custom_input":
            names = [line.strip() for line in custom_text.splitlines() if line.strip()]
        elif source == "gen_3l":
            names = NameGenerator.generate_3l_pronounceable(limit=1000)
        elif source == "gen_4l":
            names = NameGenerator.generate_4l_pronounceable(limit=1500)
        elif source == "gen_gaming":
            names = NameGenerator.generate_compound_words(count=800)
        else:
            wordlist_path = get_wordlist_path(source)
            if wordlist_path.exists():
                with open(wordlist_path, "r", encoding="utf-8") as f:
                    names = [line.strip() for line in f if line.strip()]
        return names

    def start_checker(self, source: str, custom_text: str = "", force_recheck: bool = False) -> Dict[str, Any]:
        """Start the checker engine with selected source."""
        # 1. Ensure active API key is set
        keys = self._get_keys_from_config()
        if not keys:
            return {"success": False, "error": "No Faceit API key provided. Please configure one in Settings."}

        self._api_client.api_keys = keys

        # 2. Collect names based on source
        names = self._collect_names_for_source(source, custom_text)
        if not names:
            return {"success": False, "error": "No valid names found in the selected source."}

        # 3. Load names into queue
        skip_checked = False if force_recheck else self._config.get("skip_already_checked", True)
        min_len = self._config.get("filter_min_length", 3)
        max_len = self._config.get("filter_max_length", 12)

        queued_count = self._engine.load_names(names, skip_checked=skip_checked, min_len=min_len, max_len=max_len)
        if queued_count == 0:
            already_in_db = self._database.get_already_checked_set()
            checked_count = sum(1 for n in names if n.lower() in already_in_db)
            if checked_count > 0:
                return {
                    "success": False,
                    "error": f"All {checked_count} names already checked. View in Database or select Bypass DB cache."
                }
            return {"success": False, "error": "None of the names match the 3-12 length criteria."}

        # 4. Start engine
        self._engine.start()
        return {"success": True, "queued": queued_count}

    def pause_checker(self) -> Dict[str, Any]:
        """Toggle pause/resume."""
        if self._engine.is_paused:
            self._engine.resume()
            return {"is_paused": False}
        else:
            self._engine.pause()
            return {"is_paused": True}

    def stop_checker(self) -> Dict[str, Any]:
        """Stop current checking session."""
        self._engine.stop()
        return {"success": True}

    def start_steam_checker(self, source: str, custom_text: str = "", force_recheck: bool = False, threads: int = 3, delay: float = 0.35) -> Dict[str, Any]:
        """Start Steam vanity checker engine."""
        self._steam_engine.num_threads = max(1, min(int(threads), 10))
        self._steam_engine.delay = max(0.05, float(delay))
        self._steam_api_client.api_key = self._config.get("steam_api_key", "").strip() or None

        names = self._collect_names_for_source(source, custom_text)
        if not names:
            return {"success": False, "error": "No valid names found in the selected source."}

        skip_checked = False if force_recheck else self._config.get("skip_already_checked", True)
        queued_count = self._steam_engine.load_names(names, skip_checked=skip_checked, min_len=3, max_len=32)

        if queued_count == 0:
            already_in_db = self._steam_database.get_already_checked_steam_set()
            checked_count = sum(1 for n in names if n.lower() in already_in_db)
            if checked_count > 0:
                return {
                    "success": False,
                    "error": f"All {checked_count} names already checked for Steam. Select Bypass DB cache to recheck."
                }
            return {"success": False, "error": "None of the names match Steam vanity criteria (3-32 characters)."}

        self._steam_engine.start()
        return {"success": True, "queued": queued_count}

    def pause_steam_checker(self) -> Dict[str, Any]:
        """Toggle pause/resume for Steam checker."""
        if self._steam_engine.is_paused:
            self._steam_engine.resume()
            return {"is_paused": False}
        else:
            self._steam_engine.pause()
            return {"is_paused": True}

    def stop_steam_checker(self) -> Dict[str, Any]:
        """Stop current Steam checking session."""
        self._steam_engine.stop()
        return {"success": True}

    def open_steam_profile(self, vanity: str) -> None:
        """Open Steam profile in browser."""
        clean = vanity.strip()
        if clean:
            self.open_url(f"https://steamcommunity.com/id/{clean}/")

    def get_steam_db_records(self, filter_status: str = "ALL", search: str = "", limit: int = 500, offset: int = 0) -> List[Dict[str, Any]]:
        """Fetch checked Steam records from database."""
        return self._steam_database.get_all_steam_records(
            limit=limit,
            offset=offset,
            filter_status=filter_status if filter_status != "ALL" else None,
            search_query=search.strip() if search.strip() else None
        )

    def clear_steam_db(self) -> Dict[str, Any]:
        """Clear all Steam records in database."""
        self._steam_database.clear_steam_records()
        return {"success": True}

    def resize_window_bounds(self, x: int, y: int, w: int, h: int) -> None:
        """Resize and position window smoothly using Win32 API."""
        import ctypes
        hwnd = ctypes.windll.user32.FindWindowW(None, "Namesniper")
        if hwnd:
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0, int(x), int(y), int(w), int(h),
                0x0004 | 0x0010  # SWP_NOZORDER | SWP_NOACTIVATE
            )

    def minimize_window(self) -> None:
        """Minimize frameless window."""
        if self._window:
            self._window.minimize()

    def close_window(self) -> None:
        """Close application window."""
        if self._window:
            self._window.destroy()

def _enforce_square_corners(title: str = "Namesniper"):
    import time
    import ctypes
    time.sleep(0.4)
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if hwnd:
            preference = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                33,
                ctypes.byref(preference),
                ctypes.sizeof(preference)
            )
    except Exception:
        pass

def launch_gui():
    """Create and start pywebview desktop window."""
    import threading
    api = NamesniperAPI()
    html_file = RESOURCE_DIR / "ui" / "index.html"

    window = webview.create_window(
        title="Namesniper",
        url=str(html_file.resolve()),
        js_api=api,
        width=1000,
        height=660,
        min_size=(840, 540),
        frameless=True,
        easy_drag=False,
        background_color="#141414"
    )
    api.set_window(window)
    threading.Thread(target=_enforce_square_corners, daemon=True).start()
    webview.start(debug=False)

if __name__ == "__main__":
    launch_gui()
