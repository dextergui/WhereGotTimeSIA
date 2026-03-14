"""
Local test for Availability Mode logic.

Simulates multiple crew sending extracted trip messages.
Prints best meeting slots result.

Usage:
    python scripts/test_availability_local.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import service


def run_test_case(title, people, month, year):
    print("\n==============================")
    print("TEST:", title)
    print("==============================")

    result = service.find_common_locations(
        people,
        month,
        year
    )

    print(result)


# -------------------------------
# MOCK TRIP BLOCKS
# -------------------------------

P1_TEXT = """
Flights for MARCH 2026:
01Mar - 03Mar | NRT | 09:00 (SQ12) | 18:00 (SQ11)
10Mar - 12Mar | SYD | 20:00 (SQ221) | 06:00 (SQ222)
"""

P2_TEXT = """
Flights for MARCH 2026:
02Mar - 04Mar | NRT | 10:00 (SQ12) | 17:00 (SQ11)
15Mar - 18Mar | LHR | 23:00 (SQ322) | 15:00 (SQ317)
"""

P3_TEXT = """
Flights for MARCH 2026:
01Mar - 05Mar | NRT | 08:00 (SQ12) | 19:00 (SQ11)
20Mar - 22Mar | SYD | 21:00 (SQ221) | 07:00 (SQ222)
"""


def build_person(name, text):
    ok, result = service.validate_extracted_block(text)

    if not ok:
        raise Exception(result)

    return {
        "name": name,
        "trips": result["trips"]
    }


if __name__ == "__main__":

    p1 = build_person("Alice", P1_TEXT)
    p2 = build_person("Bob", P2_TEXT)
    p3 = build_person("Charlie", P3_TEXT)

    # TEST 1 — two people overlap overseas
    run_test_case(
        "NRT overlap Alice + Bob",
        [p1, p2],
        3,
        2026
    )

    # TEST 2 — 3 people overlap overseas
    run_test_case(
        "3-crew NRT overlap",
        [p1, p2, p3],
        3,
        2026
    )

    # TEST 3 — SIN ground overlap
    run_test_case(
        "Ground SIN overlap",
        [p1, p2, p3],
        3,
        2026
    )