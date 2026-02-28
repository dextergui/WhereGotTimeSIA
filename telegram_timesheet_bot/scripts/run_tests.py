import difflib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import service, models


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

def test_nov25_snapshot():
    raw_path = ROOT / "tests" / "nov25_extracted.txt"
    expected_path = ROOT / "tests" / "snapshots" / "nov25_entries.txt"

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

    print("  - nov25 snapshot OK")
def test_dec25_snapshot():
    raw_path = ROOT / "tests" / "dec25_extracted.txt"
    expected_path = ROOT / "tests" / "snapshots" / "dec25_entries.txt"

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

    print("  - dec25 snapshot OK")
def test_mar26_snapshot():
    raw_path = ROOT / "tests" / "mar26_extracted.txt"
    expected_path = ROOT / "tests" / "snapshots" / "mar26_entries.txt"

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

    print("  - mar26 snapshot OK")
def test_apr26Brandon_snapshot():
    raw_path = ROOT / "tests" / "apr26Brandon_extracted.txt"
    expected_path = ROOT / "tests" / "snapshots" / "apr26Brandon_entries.txt"

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

    print("  - apr26Brandon snapshot OK")
def test_apr26Bing_snapshot():
    raw_path = ROOT / "tests" / "apr26Bing_extracted.txt"
    expected_path = ROOT / "tests" / "snapshots" / "apr26Bing_entries.txt"

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

    print("  - apr26Bing snapshot OK")

def parsing_test():
    print("=== Running parsing tests against snapshots ===")
    test_nov25_snapshot()
    test_dec25_snapshot()
    test_mar26_snapshot()
    test_apr26Brandon_snapshot()
    test_apr26Bing_snapshot()
    print("All parsing snapshot tests passed!")
    print("===============================================")


def test_nov25_reply_snapshot():
    raw_path = ROOT / "tests" / "nov25_extracted.txt"
    expected_path = ROOT / "tests" / "snapshots" / "nov25_reply.txt"

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

    print("  - nov25 reply snapshot OK")
def test_dec25_reply_snapshot():
    raw_path = ROOT / "tests" / "dec25_extracted.txt"
    expected_path = ROOT / "tests" / "snapshots" / "dec25_reply.txt"

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

    print("  - dec25 reply snapshot OK")
def test_mar26_reply_snapshot():
    raw_path = ROOT / "tests" / "mar26_extracted.txt"
    expected_path = ROOT / "tests" / "snapshots" / "mar26_reply.txt"

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

    print("  - mar26 reply snapshot OK")
def test_apr26Bing_reply_snapshot():
    raw_path = ROOT / "tests" / "apr26Bing_extracted.txt"
    expected_path = ROOT / "tests" / "snapshots" / "apr26Bing_reply.txt"

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

    print("  - apr26Bing reply snapshot OK")
def test_apr26Brandon_reply_snapshot():
    raw_path = ROOT / "tests" / "apr26Brandon_extracted.txt"
    expected_path = ROOT / "tests" / "snapshots" / "apr26Brandon_reply.txt"

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
    print("  - apr26Brandon reply snapshot OK")

def reply_test():
    print("=== Running reply message tests against snapshots ===")
    test_nov25_reply_snapshot()
    test_dec25_reply_snapshot()
    test_mar26_reply_snapshot()
    test_apr26Bing_reply_snapshot()
    test_apr26Brandon_reply_snapshot()
    print("All reply message snapshot tests passed!")
    print("=====================================================")

def main():
    parsing_test()
    reply_test()
    print("All tests passed!")


if __name__ == "__main__":
    main()
