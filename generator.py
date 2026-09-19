"""
Namesniper - Username Generator Module
Generates short, clean, pronounceable 3-letter, 4-letter, pattern-based,
and gaming-style usernames.
"""
import random
import itertools
from typing import List, Set, Generator

CONSONANTS = "bcdfghjklmnpqrstvwxyz"
VOWELS = "aeiou"
ALL_LETTERS = "abcdefghijklmnopqrstuvwxyz"
DIGITS = "0123456789"

LEET_MAP = {
    'a': '4',
    'b': '8',
    'e': '3',
    'g': '9',
    'i': '1',
    'l': '1',
    'o': '0',
    's': '5',
    't': '7',
    'z': '2'
}

COOL_PREFIXES = [
    "neo", "zen", "vox", "hex", "arc", "sol", "nox", "lux", "vex", "syn",
    "hyper", "cyber", "omni", "meta", "ultra", "chron", "aero", "cryo",
    "pyro", "astro", "proto", "flux", "void", "dark", "grim", "iron"
]

COOL_SUFFIXES = [
    "ix", "ox", "ex", "ax", "or", "er", "is", "os", "us", "ar",
    "on", "en", "in", "an", "um", "al", "el", "il", "ol", "ul",
    "ly", "ty", "ry", "sy", "my", "ny", "cy", "zy"
]

class NameGenerator:
    @staticmethod
    def generate_3l_pronounceable(limit: int = 1000, shuffle: bool = True) -> List[str]:
        """Generate 3-letter pronounceable words (CVC: Consonant-Vowel-Consonant)."""
        names = []
        for c1 in CONSONANTS:
            for v in VOWELS:
                for c2 in CONSONANTS:
                    names.append(f"{c1}{v}{c2}")
        
        # Also include VCV (e.g. ace, ice, ore, etc.)
        for v1 in VOWELS:
            for c in CONSONANTS:
                for v2 in VOWELS:
                    names.append(f"{v1}{c}{v2}")

        # Also include CCV / VCC
        for c1 in "bcdfghprstvw":
            for c2 in "lr":
                for v in VOWELS:
                    names.append(f"{c1}{c2}{v}")

        unique_names = list(dict.fromkeys(names))
        if shuffle:
            random.shuffle(unique_names)
        return unique_names[:limit] if limit > 0 else unique_names

    @staticmethod
    def generate_3l_all(shuffle: bool = True) -> List[str]:
        """Generate all 17,576 3-letter combinations (aaa-zzz)."""
        names = [''.join(p) for p in itertools.product(ALL_LETTERS, repeat=3)]
        if shuffle:
            random.shuffle(names)
        return names

    @staticmethod
    def generate_4l_pronounceable(limit: int = 2000, shuffle: bool = True) -> List[str]:
        """Generate 4-letter pronounceable words (CVCV, CVCC, and VCCV patterns)."""
        names = []
        # CVCV (e.g., nova, lune, zora, sora, kuro, maki)
        for c1 in CONSONANTS:
            for v1 in VOWELS:
                for c2 in CONSONANTS:
                    for v2 in VOWELS:
                        names.append(f"{c1}{v1}{c2}{v2}")
        
        # CVCC (e.g., dark, dusk, volt, rift, fang, helm)
        for c1 in "bcdfghjklmnpqrstvwxz":
            for v in VOWELS:
                for c2 in "lmnrstx":
                    for c3 in "cdfgkpt":
                        names.append(f"{c1}{v}{c2}{c3}")

        unique_names = list(dict.fromkeys(names))
        if shuffle:
            random.shuffle(unique_names)
        return unique_names[:limit] if limit > 0 else unique_names

    @staticmethod
    def generate_by_pattern(pattern: str, count: int = 500) -> List[str]:
        """
        Generate names following a template string:
        'C' = Consonant, 'V' = Vowel, 'L' = Any letter, 'D' = Digit
        Example: 'CVCV' -> 'zora', 'CVC-D' -> 'dex-7'
        """
        pattern = pattern.strip()
        if not pattern:
            return []

        results = set()
        max_attempts = count * 20
        attempts = 0

        while len(results) < count and attempts < max_attempts:
            attempts += 1
            chars = []
            for char in pattern:
                if char == 'C':
                    chars.append(random.choice(CONSONANTS))
                elif char == 'V':
                    chars.append(random.choice(VOWELS))
                elif char == 'L':
                    chars.append(random.choice(ALL_LETTERS))
                elif char == 'D':
                    chars.append(random.choice(DIGITS))
                else:
                    chars.append(char)
            name = "".join(chars).lower()
            if 3 <= len(name) <= 12:
                results.add(name)

        return list(results)

    @staticmethod
    def generate_compound_words(count: int = 500) -> List[str]:
        """Generate stylish compound words by combining cool prefixes and roots/suffixes."""
        results = set()
        roots = [
            "core", "pulse", "shade", "ghost", "flare", "blade", "storm", "shift",
            "drift", "spark", "surge", "blaze", "crypt", "shard", "prime", "nexus",
            "frost", "glyph", "forge", "scythe", "wrath", "gale", "void", "haze"
        ]
        
        for _ in range(count * 5):
            if len(results) >= count:
                break
            style = random.choice(["pref_root", "root_suff", "pref_suff"])
            if style == "pref_root":
                name = random.choice(COOL_PREFIXES) + random.choice(roots)
            elif style == "root_suff":
                name = random.choice(roots) + random.choice(COOL_SUFFIXES)
            else:
                name = random.choice(COOL_PREFIXES) + random.choice(COOL_SUFFIXES)
            
            if 3 <= len(name) <= 12:
                results.add(name.lower())

        return list(results)[:count]

    @staticmethod
    def generate_3_alnum(limit: int = 1500, shuffle: bool = True) -> List[str]:
        """Generate 3-character strings of letters and numbers (a-z, 0-9)."""
        chars = ALL_LETTERS + DIGITS
        if limit <= 0 or limit >= 46656:
            names = [''.join(p) for p in itertools.product(chars, repeat=3)]
        else:
            names_set = set()
            attempts = 0
            while len(names_set) < limit and attempts < limit * 10:
                attempts += 1
                names_set.add(''.join(random.choices(chars, k=3)))
            names = list(names_set)
        if shuffle:
            random.shuffle(names)
        return names[:limit] if limit > 0 else names

    @staticmethod
    def generate_4_alnum(limit: int = 2000, shuffle: bool = True) -> List[str]:
        """Generate 4-character strings of letters and numbers (a-z, 0-9)."""
        chars = ALL_LETTERS + DIGITS
        names_set = set()
        attempts = 0
        while len(names_set) < limit and attempts < limit * 10:
            attempts += 1
            names_set.add(''.join(random.choices(chars, k=4)))
        names = list(names_set)
        if shuffle:
            random.shuffle(names)
        return names[:limit]

    @staticmethod
    def generate_3_mixed(limit: int = 1500, shuffle: bool = True) -> List[str]:
        """Generate 3-character strings containing both letters and numbers."""
        chars = ALL_LETTERS + DIGITS
        names_set = set()
        attempts = 0
        while len(names_set) < limit and attempts < limit * 15:
            attempts += 1
            s = ''.join(random.choices(chars, k=3))
            if any(c.isalpha() for c in s) and any(c.isdigit() for c in s):
                names_set.add(s)
        names = list(names_set)
        if shuffle:
            random.shuffle(names)
        return names[:limit]

    @staticmethod
    def generate_4_mixed(limit: int = 2000, shuffle: bool = True) -> List[str]:
        """Generate 4-character strings containing both letters and numbers."""
        chars = ALL_LETTERS + DIGITS
        names_set = set()
        attempts = 0
        while len(names_set) < limit and attempts < limit * 15:
            attempts += 1
            s = ''.join(random.choices(chars, k=4))
            if any(c.isalpha() for c in s) and any(c.isdigit() for c in s):
                names_set.add(s)
        names = list(names_set)
        if shuffle:
            random.shuffle(names)
        return names[:limit]

    @staticmethod
    def apply_leet(word: str, amount: int = 1) -> str:
        """
        Randomly substitute between 1 and `amount` characters in `word`
        with valid alphanumeric leetspeak equivalents (e.g. e->3, a->4, o->0, s->5, t->7).
        """
        if not word or amount <= 0:
            return word

        chars = list(word)
        candidates = [i for i, c in enumerate(chars) if c.lower() in LEET_MAP]

        if not candidates:
            return word

        count = min(len(candidates), max(1, amount))
        if amount > 1 and len(candidates) > 1:
            count = random.randint(1, min(amount, len(candidates)))

        chosen_indices = random.sample(candidates, count)
        for idx in chosen_indices:
            orig = chars[idx].lower()
            chars[idx] = LEET_MAP[orig]

        return "".join(chars)

    @staticmethod
    def apply_leet_to_list(names: List[str], amount: int = 1) -> List[str]:
        """Apply random leetspeak to a list of usernames while preserving uniqueness and order."""
        result = []
        seen = set()
        for name in names:
            leet_name = NameGenerator.apply_leet(name, amount=amount)
            clean = leet_name.strip()
            lower = clean.lower()
            if clean and lower not in seen:
                seen.add(lower)
                result.append(clean)
        return result
