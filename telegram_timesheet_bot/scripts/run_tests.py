import difflib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import service, models

TESTS = {"nov25", "dec25", "mar26", "apr26Brandon", "apr26Bing"}

def entries_to_string(entries: list[models.FlightRow]) -> str:
    lines = []
    for e in entries:
        lines.append(
            f"{e.start_date} | {e.arrival_date} | "
            f"{e.flight_number} | {e.sector} | {e.duty_type} | "
            f"{e.rpt} | {e.std} | {e.sta} | "
            f"{e.flight_time} | {e.duty_time} | {e.fdp} | "
        )
    return "\n".join(lines)

def test_entries_snapshot(filename: str):
    raw_path = ROOT / "tests" / f"{filename}_extracted.txt"
    expected_path = ROOT / "tests" / "snapshots" / f"{filename}_entries.txt"
    
    if not expected_path.exists():
        print(f"  - {filename} sheet row snapshot not found, skipping test")
        return

    raw_text = raw_path.read_text()
    expected = expected_path.read_text().strip()

    result = service.parse_timesheet(raw_text)
    actual = entries_to_string(result["entries"]).strip()

    if actual != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                actual.splitlines(),
                fromfile="expected",
                tofile="actual",
                lineterm=""
            )
        )
        raise AssertionError(diff)

    print(f"  - {filename} entries snapshot OK")

def parsing_test():
    print("=== Running parsing tests against snapshots ===")
    for test in TESTS:
        test_entries_snapshot(test)
    print("All parsing snapshot tests passed!")
    print("===============================================")

def test_reply_snapshot(filename: str):
    raw_path = ROOT / "tests" / f"{filename}_extracted.txt"
    expected_path = ROOT / "tests" / "snapshots" / f"{filename}_reply.txt"

    if not expected_path.exists():
        print(f"  - {filename} sheet row snapshot not found, skipping test")
        return

    raw_text = raw_path.read_text()
    expected = expected_path.read_text().strip()

    result = service.parse_timesheet(raw_text)
    actual = service.trips_to_message(result["entries"]).strip()

    if actual != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                actual.splitlines(),
                fromfile="expected",
                tofile="actual",
                lineterm=""
            )
        )
        raise AssertionError(diff)

    print(f"  - {filename} reply snapshot OK")

def reply_test():
    print("=== Running reply message tests against snapshots ===")
    for test in TESTS:
        test_reply_snapshot(test)
    print("All reply message snapshot tests passed!")
    print("=====================================================")

def test_sheet_row_snapshot(filename: str):
    raw_path = ROOT / "tests" / f"{filename}_extracted.txt"
    expected_path = ROOT / "tests" / "snapshots" / f"{filename}_row.txt"

    if not expected_path.exists():
        print(f"  - {filename} sheet row snapshot not found, skipping test")
        return

    raw_text = raw_path.read_text()
    expected = expected_path.read_text().strip().splitlines()

    result = service.parse_timesheet(raw_text)
    actual_rows = service.trips_to_sheet_rows(result["entries"])
    actual = [f"{i}: {v}" for i, v in enumerate(actual_rows, 1)]

    if actual != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected,
                actual,
                fromfile="expected",
                tofile="actual",
                lineterm=""
            )
        )
        raise AssertionError(diff)

    print(f"  - {filename} sheet row snapshot OK")

def sheet_row_test():
    print("=== Running sheet row tests against snapshots ===")
    for test in TESTS:
        test_sheet_row_snapshot(test)
    print("All sheet row snapshot tests passed!")
    print("================================================")

def main():
    parsing_test()
    reply_test()
    sheet_row_test()
    print("All tests passed!")


if __name__ == "__main__":
    main()
