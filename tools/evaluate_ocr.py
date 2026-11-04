"""Measure actual local OCR on generated fictional panels, never real accounts."""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.core import Pause, edit_fields, extract_candidates
from src.fixtures import draw_edit, edit, ocr_cases


def evaluate(output):
    import numpy as np
    from PIL import ImageOps
    from rapidocr_onnxruntime import RapidOCR
    output.mkdir(parents=True, exist_ok=True)
    engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
    results = []
    for item in ocr_cases():
        image = draw_edit(edit(item["remark"], item["phones"], item["complete"]), item["blur"])
        image.save(output / (item["id"] + ".png"))
        reads = []
        started = time.perf_counter()
        for invert in (False, True):
            source = ImageOps.invert(image) if invert else image
            raw, _ = engine(np.asarray(source.resize((880, 1600))))
            rows = [{"text": text.strip(), "confidence": float(conf),
                     "box": [[float(x) / 2, float(y) / 2] for x, y in box]}
                    for box, text, conf in raw or []]
            try:
                parsed = edit_fields(rows, False)
                value = parsed["phone"]
                if any(candidate["confidence"] < 0.85 for candidate in extract_candidates(rows)):
                    value = "待核对"
                reads.append({"phone": value, "remark": parsed["remark"]})
            except Pause:
                reads.append({"phone": "待核对", "remark": "待核对"})
        phone = reads[0]["phone"] if reads[0]["phone"] == reads[1]["phone"] else "待核对"
        remark = reads[0]["remark"] if reads[0]["remark"] == reads[1]["remark"] else "待核对"
        expected = ("；".join(item["phones"]) if item["phones"] else "没有") if item["complete"] else "待核对"
        results.append({"case": item["id"], "expected_phone": expected, "observed_phone": phone,
                        "phone_exact": phone == expected, "remark_exact": remark == item["remark"],
                        "needs_review": phone == "待核对", "false_empty": phone == "没有" and expected != "没有",
                        "seconds": round(time.perf_counter() - started, 3)})
    complete = [r for r in results if r["case"] != "missing_boundary"]
    summary = {"date": "2026-11-04", "input": "generated_fictional_images", "engine": "rapidocr-onnxruntime==1.4.4",
               "cloud_calls": 0, "cases": len(results), "complete_field_cases": len(complete),
               "phone_exact_on_complete_fields": sum(r["phone_exact"] for r in complete),
               "remark_exact_on_complete_fields": sum(r["remark_exact"] for r in complete),
               "needs_review_count": sum(r["needs_review"] for r in results),
               "false_empty_count": sum(r["false_empty"] for r in results), "results": results,
               "limits": "Synthetic panel benchmark only; no live navigation, real contacts or general accuracy claim."}
    (output / "ocr-evaluation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs/ocr-evaluation"))
    evaluate(parser.parse_args().output)
