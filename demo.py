"""Run a synthetic pause/resume demonstration. Never opens or controls WeChat."""

import argparse
import json
from datetime import datetime
from pathlib import Path

from src.fixtures import replay_cases
from src.replay import run_replay


def demonstrate(directory):
    frames = replay_cases()
    first = run_replay(frames, directory)
    assert first["status"] == "paused" and first["records"] == 2
    before = {key: first[key] for key in ("status", "records", "next_index", "reason")}
    second = run_replay(frames, directory, resume=True, use_repairs=True)
    assert second["records"] == 6 and second["next_index"] == 7
    return {"data": "fictional", "desktop_input_calls": 0, "cloud_ocr_calls": 0,
            "first_pass": before, "after_corrected_fixture_resume": second,
            "scope": "OCR-text fixture replay, not image OCR or a live address-book run"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path("outputs") / datetime.now().strftime("demo-%Y%m%d-%H%M%S-%f"))
    args = parser.parse_args()
    result = demonstrate(args.output)
    (args.output / "replay-summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
