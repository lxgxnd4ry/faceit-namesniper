"""
Namesniper - Steam Checker Engine Module
Multi-threaded worker queue for checking Steam vanity IDs,
with real-time stats, thread-safe persistence, callbacks, and rate limiting.
"""
import time
import queue
import threading
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from config import EXPORTS_DIR, load_config
from database import Database, SteamDatabase
from steam_api import SteamAPIClient

class SteamCheckerEngine:
    def __init__(
        self,
        api_client: SteamAPIClient,
        database: SteamDatabase,
        threads: int = 3,
        delay_between_requests: float = 0.35,
        save_taken: bool = False,
        cooldown_duration: int = 60,
        on_result: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_finish: Optional[Callable[[], None]] = None
    ):
        self.api_client = api_client
        self.database = database
        self.num_threads = max(1, min(threads, 10))
        self.delay = delay_between_requests
        self.save_taken = save_taken
        self.cooldown_duration = cooldown_duration

        # Callbacks
        self.on_result = on_result
        self.on_progress = on_progress
        self.on_finish = on_finish

        # State flags & queue
        self.queue = queue.Queue()
        self.workers: List[threading.Thread] = []
        self.is_running = False
        self.is_paused = False
        self.stop_requested = False
        self.is_rate_limited = False
        self.cooldown_remaining = 0

        # Synchronization
        self.lock = threading.Lock()
        self.pause_event = threading.Event()
        self.pause_event.set()

        # Statistics
        self.total_queued = 0
        self.checked_count = 0
        self.available_count = 0
        self.taken_count = 0
        self.invalid_count = 0
        self.error_count = 0
        self.start_time: Optional[float] = None

        # Files
        self.available_txt = EXPORTS_DIR / "steam_available_names.txt"
        self.available_csv = EXPORTS_DIR / "steam_available_names.csv"
        self._ensure_csv_headers()

    def _ensure_csv_headers(self) -> None:
        """Initialize Steam CSV export file with headers if it does not exist."""
        if not self.available_csv.exists():
            with open(self.available_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Vanity", "Status", "Length", "SteamID64", "Steam URL", "Details", "Checked At"])

    def _append_to_exports(self, result: Dict[str, Any]) -> None:
        """Thread-safe append of an available Steam ID to txt and csv files."""
        vanity = result["vanity"]
        status = result["status"]

        # Write to TXT
        with open(self.available_txt, "a", encoding="utf-8") as f:
            f.write(f"{vanity}\n")

        # Write to CSV
        with open(self.available_csv, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                vanity,
                status,
                result.get("length", len(vanity)),
                result.get("steamid64") or "N/A",
                result.get("profile_url") or f"https://steamcommunity.com/id/{vanity}/",
                result.get("details", ""),
                time.strftime("%Y-%m-%d %H:%M:%S")
            ])

    def load_names(
        self,
        names: List[str],
        skip_checked: bool = True,
        min_len: int = 3,
        max_len: int = 32
    ) -> int:
        """Filter names and load into processing queue."""
        with self.queue.mutex:
            self.queue.queue.clear()

        already_checked = self.database.get_already_checked_steam_set() if skip_checked else set()
        loaded = 0
        seen = set()

        for name in names:
            clean = name.strip()
            if not clean:
                continue
            lower_clean = clean.lower()
            if lower_clean in seen:
                continue
            seen.add(lower_clean)

            if len(clean) < min_len or len(clean) > max_len:
                continue

            if skip_checked and lower_clean in already_checked:
                continue

            self.queue.put(clean)
            loaded += 1

        self.total_queued = loaded
        self.checked_count = 0
        self.available_count = 0
        self.taken_count = 0
        self.invalid_count = 0
        self.error_count = 0
        self.is_rate_limited = False
        self.cooldown_remaining = 0
        return loaded

    def start(self) -> None:
        """Start worker threads to process queue."""
        if self.is_running:
            return

        self.is_running = True
        self.is_paused = False
        self.stop_requested = False
        self.is_rate_limited = False
        self.cooldown_remaining = 0
        self.pause_event.set()
        self.start_time = time.time()
        self.workers.clear()

        for i in range(self.num_threads):
            t = threading.Thread(target=self._worker_loop, name=f"SteamWorker-{i+1}", daemon=True)
            self.workers.append(t)
            t.start()

    def pause(self) -> None:
        """Pause checking."""
        self.is_paused = True
        self.pause_event.clear()

    def resume(self) -> None:
        """Resume checking."""
        self.is_paused = False
        with self.lock:
            self.is_rate_limited = False
            self.cooldown_remaining = 0
        self.pause_event.set()

    def stop(self) -> None:
        """Stop checking and drain queue."""
        self.stop_requested = True
        with self.lock:
            self.is_rate_limited = False
            self.cooldown_remaining = 0
        self.pause_event.set()
        with self.queue.mutex:
            self.queue.queue.clear()
        self.is_running = False
        self.is_paused = False

    def _worker_loop(self) -> None:
        """Thread worker loop consuming names from queue."""
        while not self.stop_requested:
            self.pause_event.wait()
            if self.stop_requested:
                break

            try:
                vanity = self.queue.get(timeout=1.0)
            except queue.Empty:
                break

            try:
                result = self.api_client.check_vanity(vanity)
                status = result["status"]

                if status == "RATE_LIMITED":
                    # Re-enqueue vanity so it is not skipped or marked as error
                    self.queue.put(vanity)
                    with self.lock:
                        should_start_cooldown = not self.is_rate_limited and not self.stop_requested
                        if should_start_cooldown:
                            self.is_rate_limited = True
                            self.pause_event.clear()

                    if should_start_cooldown:
                        cooldown_t = threading.Thread(
                            target=self._run_cooldown,
                            args=(self.cooldown_duration, vanity),
                            name="SteamCooldownCoordinator",
                            daemon=True
                        )
                        cooldown_t.start()
                    continue

                with self.lock:
                    self.checked_count += 1
                    if status == "AVAILABLE":
                        self.available_count += 1
                        self.database.record_steam_result(
                            vanity=result["vanity"],
                            status=status,
                            length=result["length"],
                            steamid64=result.get("steamid64"),
                            profile_url=result.get("profile_url"),
                            details=result.get("details")
                        )
                        self._append_to_exports(result)
                    elif status == "TAKEN":
                        self.taken_count += 1
                        if self.save_taken:
                            self.database.record_steam_result(
                                vanity=result["vanity"],
                                status=status,
                                length=result["length"],
                                steamid64=result.get("steamid64"),
                                profile_url=result.get("profile_url"),
                                details=result.get("details")
                            )
                    elif status == "INVALID":
                        self.invalid_count += 1
                    else:
                        self.error_count += 1

                # Notify GUI
                if self.on_result:
                    self.on_result(result)

                if self.on_progress:
                    self._emit_progress()

            except Exception as e:
                with self.lock:
                    self.error_count += 1
                if self.on_result:
                    self.on_result({
                        "status": "ERROR",
                        "vanity": vanity,
                        "length": len(vanity),
                        "steamid64": None,
                        "profile_url": f"https://steamcommunity.com/id/{vanity}/",
                        "details": str(e)
                    })
            finally:
                self.queue.task_done()
                if self.delay > 0:
                    time.sleep(self.delay)

        with self.lock:
            # If all workers are finished and queue is empty and not waiting in cooldown
            if self.queue.empty() and self.is_running and not self.is_rate_limited:
                alive_others = any(t.is_alive() for t in self.workers if t != threading.current_thread())
                if not alive_others:
                    self.is_running = False
                    if self.on_progress:
                        self._emit_progress()
                    if self.on_finish:
                        self.on_finish()

    def _run_cooldown(self, wait_seconds: int = 60, triggering_vanity: str = "") -> None:
        """Coordinated cooldown pause across all workers when Steam rate limit is encountered."""
        if self.on_result:
            self.on_result({
                "status": "COOLDOWN_START",
                "vanity": triggering_vanity,
                "seconds": wait_seconds,
                "details": f"Steam rate limit reached. Pausing for {wait_seconds}s cooldown before resuming..."
            })

        for sec in range(wait_seconds, 0, -1):
            if self.stop_requested or not self.is_rate_limited:
                with self.lock:
                    self.is_rate_limited = False
                    self.cooldown_remaining = 0
                return

            with self.lock:
                self.cooldown_remaining = sec
            if self.on_progress:
                self._emit_progress()
            time.sleep(1.0)

        with self.lock:
            self.is_rate_limited = False
            self.cooldown_remaining = 0
            if not self.is_paused and not self.stop_requested:
                self.pause_event.set()

        if self.on_result and not self.stop_requested:
            self.on_result({
                "status": "COOLDOWN_END",
                "vanity": "",
                "details": "Cooldown completed. Resuming checks..."
            })

        if self.on_progress:
            self._emit_progress()

    def _emit_progress(self) -> None:
        """Emit progress stats snapshot to callback."""
        elapsed = time.time() - (self.start_time or time.time())
        speed = round(self.checked_count / elapsed, 1) if elapsed > 0 else 0.0
        percent = round((self.checked_count / max(1, self.total_queued)) * 100, 1)

        stats = {
            "total": self.total_queued,
            "checked": self.checked_count,
            "available": self.available_count,
            "taken": self.taken_count,
            "invalid": self.invalid_count,
            "errors": self.error_count,
            "speed": speed,
            "percent": percent,
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "is_cooldown": self.is_rate_limited,
            "cooldown_remaining": self.cooldown_remaining
        }
        if self.on_progress:
            self.on_progress(stats)
