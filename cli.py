"""
Namesniper - Interactive Terminal CLI
Full-featured colorized command-line interface for headless environments or terminal enthusiasts.
"""
import sys
import time
import argparse
from pathlib import Path
from typing import List

try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)
except ImportError:
    class Fore:
        GREEN = RED = YELLOW = CYAN = MAGENTA = WHITE = RESET = ""
    class Style:
        BRIGHT = DIM = RESET_ALL = ""

from config import WORDLISTS_DIR, EXPORTS_DIR, VERSION, load_config, save_config, get_wordlist_path
from database import Database
from faceit_api import FaceitAPIClient
from generator import NameGenerator
from checker import CheckerEngine

BANNER = (
    Fore.CYAN + Style.BRIGHT + r"""
  _   _                               _                 
 | \ | | __ _ _ __ ___   ___  ___ _ __ (_)_ __   ___ _ __ 
 |  \| |/ _` | '_ ` _ \ / _ \/ __| '_ \| | '_ \ / _ \ '__|
 | |\  | (_| | | | | | |  __/\__ \ | | | | |_) |  __/ |   
 |_| \_|\__,_|_| |_| |_|\___||___/_| |_|_| .__/ \___|_|   
          """ + Fore.RED + "FACEIT USERNAME SNIPER" + Fore.CYAN + r"""          |_|     v2.0
""" + Style.RESET_ALL
)

def print_banner():
    print(BANNER)

def run_cli():
    parser = argparse.ArgumentParser(description=f"Namesniper v{VERSION} - High-Speed Faceit & Steam Username Checker")
    parser.add_argument("-v", "--version", action="version", version=f"Namesniper v{VERSION}")
    parser.add_argument("-w", "--wordlist", type=str, help="Wordlist name or file path ('og', '3l', '4l', 'dict', or path to .txt)")
    parser.add_argument("-g", "--generate", type=str, choices=["3l", "4l", "3_alnum", "4_alnum", "3_mixed", "4_mixed", "compound"], help="Algorithmically generate names")
    parser.add_argument("--leet", action="store_true", help="Randomly insert leet language into names")
    parser.add_argument("--leet-amount", type=int, default=1, choices=range(1, 6), help="Leet substitutions amount (1-5, default: 1)")
    parser.add_argument("-k", "--key", type=str, help="Faceit API key (Bearer token)")
    parser.add_argument("-t", "--threads", type=int, default=3, help="Concurrent checking threads (default: 3)")
    parser.add_argument("-d", "--delay", type=float, default=0.35, help="Delay between checks in seconds (default: 0.35)")
    parser.add_argument("--no-idle", action="store_true", help="Disable idle account detection")
    parser.add_argument("--test-key", type=str, help="Test a Faceit API key and exit")
    parser.add_argument("--stats", action="store_true", help="Display database summary stats and exit")

    args = parser.parse_args()
    cfg = load_config()
    db = Database()

    print_banner()

    # Handle --stats
    if args.stats:
        stats = db.get_stats()
        print(f"{Fore.CYAN}--- Database Records Summary ---{Style.RESET_ALL}")
        print(f"Total checked: {stats['total']}")
        print(f"{Fore.GREEN}Available:     {stats['available']}")
        print(f"{Fore.YELLOW}Claimable:     {stats['claimable']}")
        print(f"{Fore.WHITE}Taken:         {stats['taken']}")
        print(f"{Fore.RED}Invalid:       {stats['invalid']}")
        sys.exit(0)

    # Handle --test-key
    if args.test_key:
        client = FaceitAPIClient()
        print(f"{Fore.CYAN}Testing Faceit API Key...{Style.RESET_ALL}")
        valid, msg = client.test_api_key(args.test_key)
        if valid:
            print(f"{Fore.GREEN}[SUCCESS] {msg}")
        else:
            print(f"{Fore.RED}[FAILED] {msg}")
        sys.exit(0)

    # Resolve API Key
    api_key = args.key or cfg.get("active_key")
    if not api_key and cfg.get("api_keys"):
        api_key = cfg["api_keys"][0]

    if not api_key:
        print(f"{Fore.YELLOW}[!] No Faceit API key configured.{Style.RESET_ALL}")
        print(f"Get a free API key at: {Fore.CYAN}https://developers.faceit.com{Style.RESET_ALL}")
        api_key = input(f"{Fore.WHITE}Enter your Faceit API Key: {Style.RESET_ALL}").strip()
        if not api_key:
            print(f"{Fore.RED}[ERROR] API Key is required to check Faceit usernames. Exiting.{Style.RESET_ALL}")
            sys.exit(1)
        cfg["active_key"] = api_key
        save_config(cfg)

    # Initialize Faceit API Client
    api_client = FaceitAPIClient(
        api_keys=[api_key],
        detect_idle=not args.no_idle
    )

    # Quick test API Key
    print(f"{Fore.CYAN}[*] Verifying API Key with Faceit...{Style.RESET_ALL}")
    valid, msg = api_client.test_api_key(api_key)
    if not valid:
        print(f"{Fore.RED}[ERROR] Key verification failed: {msg}{Style.RESET_ALL}")
        sys.exit(1)
    print(f"{Fore.GREEN}[OK] {msg}{Style.RESET_ALL}\n")

    # Resolve Wordlist or Generator
    names: List[str] = []
    if args.generate:
        print(f"{Fore.CYAN}[*] Generating names using algorithm: {args.generate}...{Style.RESET_ALL}")
        if args.generate == "3l":
            names = NameGenerator.generate_3l_pronounceable(limit=1000)
        elif args.generate == "4l":
            names = NameGenerator.generate_4l_pronounceable(limit=1500)
        elif args.generate == "3_alnum":
            names = NameGenerator.generate_3_alnum(limit=1500)
        elif args.generate == "4_alnum":
            names = NameGenerator.generate_4_alnum(limit=2000)
        elif args.generate == "3_mixed":
            names = NameGenerator.generate_3_mixed(limit=1500)
        elif args.generate == "4_mixed":
            names = NameGenerator.generate_4_mixed(limit=2000)
        elif args.generate == "compound":
            names = NameGenerator.generate_compound_words(count=800)
    elif args.wordlist:
        preset_map = {
            "og": "og_cool_words.txt",
            "3l": "short_3l.txt",
            "4l": "short_4l.txt",
            "dict": "dictionary_words.txt"
        }
        filename = preset_map.get(args.wordlist, args.wordlist)
        path = Path(filename)
        if not path.exists():
            path = get_wordlist_path(filename)
        if not path.exists():
            print(f"{Fore.RED}[ERROR] Wordlist not found: {args.wordlist}{Style.RESET_ALL}")
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            names = [line.strip() for line in f if line.strip()]
    else:
        # Interactive selection
        print(f"{Fore.WHITE}Select a username source:{Style.RESET_ALL}")
        print("  1) Curated OG & Cool Gamer Words (600+)")
        print("  2) Short 3-Letter Words (1,050+)")
        print("  3) Short 4-Letter Words (1,400+)")
        print("  4) 1-Word Clean Dictionary (2,200+)")
        print("  5) 3-Char Letters & Numbers (1,500)")
        print("  6) 4-Char Letters & Numbers (2,000)")
        print("  7) Pronounceable 3L Generator (CVC)")
        print("  8) Pronounceable 4L Generator (CVCV)")
        print("  9) Custom File Path")
        choice = input(f"{Fore.YELLOW}Select option [1-9] (default: 1): {Style.RESET_ALL}").strip() or "1"

        if choice == "1":
            with open(get_wordlist_path("og_cool_words.txt"), "r", encoding="utf-8") as f:
                names = [l.strip() for l in f if l.strip()]
        elif choice == "2":
            with open(get_wordlist_path("short_3l.txt"), "r", encoding="utf-8") as f:
                names = [l.strip() for l in f if l.strip()]
        elif choice == "3":
            with open(get_wordlist_path("short_4l.txt"), "r", encoding="utf-8") as f:
                names = [l.strip() for l in f if l.strip()]
        elif choice == "4":
            with open(get_wordlist_path("dictionary_words.txt"), "r", encoding="utf-8") as f:
                names = [l.strip() for l in f if l.strip()]
        elif choice == "5":
            names = NameGenerator.generate_3_alnum(limit=1500)
        elif choice == "6":
            names = NameGenerator.generate_4_alnum(limit=2000)
        elif choice == "7":
            names = NameGenerator.generate_3l_pronounceable(limit=1000)
        elif choice == "8":
            names = NameGenerator.generate_4l_pronounceable(limit=1500)
        elif choice == "9":
            custom_path = input(f"{Fore.WHITE}Enter file path: {Style.RESET_ALL}").strip()
            with open(custom_path, "r", encoding="utf-8") as f:
                names = [l.strip() for l in f if l.strip()]
        else:
            with open(get_wordlist_path("og_cool_words.txt"), "r", encoding="utf-8") as f:
                names = [l.strip() for l in f if l.strip()]

    if args.leet:
        leet_amt = max(1, min(args.leet_amount, 5))
        print(f"{Fore.CYAN}[*] Applying leetspeak substitutions (amount: {leet_amt})...{Style.RESET_ALL}")
        names = NameGenerator.apply_leet_to_list(names, amount=leet_amt)

    # Result handler
    def on_result(result):
        status = result["status"]
        nick = result["nickname"]
        if status == "AVAILABLE":
            print(f"\n{Fore.GREEN}{Style.BRIGHT}[★ AVAILABLE ★]  {nick:<12} (Length: {len(nick)}) -> Saved to exports!{Style.RESET_ALL}")
        elif status == "CLAIMABLE_IDLE":
            created_str = f" | Created: {result.get('account_created_at')} ({result.get('account_age_years')}y)" if result.get('account_created_at') else ""
            print(f"\n{Fore.YELLOW}{Style.BRIGHT}[★ CLAIMABLE ★]  {nick:<12} (Idle 0 games{created_str}) -> Saved to exports!{Style.RESET_ALL}")
        elif status == "ERROR":
            print(f"\n{Fore.RED}[!] Error checking '{nick}': {result.get('details')}{Style.RESET_ALL}")

    def on_progress(stats):
        pct = (stats["checked"] / stats["total"] * 100) if stats["total"] > 0 else 0
        sys.stdout.write(
            f"\r{Fore.CYAN}[{pct:5.1f}%]{Style.RESET_ALL} "
            f"Progress: {stats['checked']}/{stats['total']} | "
            f"{Fore.GREEN}Avail: {stats['available']}{Style.RESET_ALL} | "
            f"{Fore.YELLOW}Claimable: {stats['claimable']}{Style.RESET_ALL} | "
            f"Taken: {stats['taken']} | "
            f"Speed: {stats['speed_per_sec']:.1f}/s | "
            f"ETA: {stats['eta_seconds']}s   "
        )
        sys.stdout.flush()

    engine = CheckerEngine(
        api_client=api_client,
        database=db,
        threads=args.threads,
        delay_between_requests=args.delay,
        detect_idle=not args.no_idle,
        on_result=on_result,
        on_progress=on_progress
    )

    queued = engine.load_names(names, skip_checked=True)
    print(f"{Fore.CYAN}[*] Loaded {queued} names into check queue (skipped duplicates and already-checked).{Style.RESET_ALL}")
    print(f"{Fore.WHITE}[*] Starting {args.threads} worker threads (delay: {args.delay}s)... Press Ctrl+C to stop.\n{Style.RESET_ALL}")

    try:
        engine.start()
        while engine.is_running:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}[!] Stopping scan...{Style.RESET_ALL}")
        engine.stop()

    stats = engine.get_stats()
    print(f"\n\n{Fore.GREEN}{Style.BRIGHT}================ SCAN COMPLETED ================{Style.RESET_ALL}")
    print(f"Total Checked:        {stats['checked']}")
    print(f"{Fore.GREEN}Available Usernames:  {stats['available']}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Claimable (Idle):     {stats['claimable']}{Style.RESET_ALL}")
    print(f"Taken Accounts:       {stats['taken']}")
    print(f"Results saved to:     {Fore.CYAN}{EXPORTS_DIR / 'available_names.txt'}{Style.RESET_ALL}")
    print(f"Detailed CSV at:      {Fore.CYAN}{EXPORTS_DIR / 'available_names.csv'}{Style.RESET_ALL}")

if __name__ == "__main__":
    run_cli()
