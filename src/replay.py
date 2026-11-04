"""Persistent offline state-machine replay, with injected synthetic observations."""

import hashlib
import json
from pathlib import Path

from .core import COLUMNS, Pause, Store, atomic_json, edit_fields, profile_fields


def observe(frame):
    for key in ("focus_ok", "geometry_ok", "account_ok"):
        if frame.get(key, True) is not True:
            raise Pause("context_changed:" + key)
    if frame.get("stop_before_save"):
        raise Pause("stop_requested_before_save")
    person = profile_fields(frame["profile"])
    if person["identity_needs_confirmation"]:
        confirmed = profile_fields(frame.get("profile_alt", []))
        if confirmed["identity"] != person["identity"]:
            raise Pause("identity_readings_disagree")
    first = edit_fields(frame["edit"], person["no_remark"])
    second = edit_fields(frame.get("edit_alt", frame["edit"]), person["no_remark"])
    for key in ("phone", "remark"):
        if first[key] != second[key]:
            raise Pause("field_readings_disagree:" + key)
    if "待核对" in (first["phone"], first["remark"]):
        raise Pause("incomplete_or_uncertain_field")
    phone_rows = [row for row in frame["edit"] if any(c.isdigit() for c in row["text"])]
    if any(row.get("confidence", 0) < 0.85 for row in phone_rows):
        raise Pause("low_confidence_digits")
    return person["identity"], dict(zip(COLUMNS, [person["name"], first["remark"], first["phone"]]))


def run_replay(frames, directory, resume=False, use_repairs=False, limit=None, stop_requested=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    state_path = directory / "state.json"
    fingerprint = hashlib.sha256(json.dumps(frames, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if resume:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["fixture_sha256"] != fingerprint:
            raise ValueError("Resume fixture mismatch; create a new task instead of mixing sources")
    else:
        if state_path.exists() or (directory / "progress.sqlite3").exists():
            raise ValueError("New replay requires a new output directory")
        state = {"mode": "synthetic_offline_replay", "fixture_sha256": fingerprint,
                 "next_index": 0, "status": "ready", "records": 0, "events": [], "attempts": 0}
    store = Store(directory)
    processed = 0
    try:
        state["attempts"] += 1
        state["status"] = "running"
        state.pop("reason", None)
        state.pop("export_error", None)
        for index in range(state["next_index"], len(frames)):
            if stop_requested:
                raise Pause("stop_requested_before_save")
            if limit is not None and processed >= limit:
                state["status"] = "limit_reached_not_full_address_book"
                break
            frame = dict(frames[index])
            if use_repairs and "repaired" in frame:
                frame.update(frame["repaired"])
            identity, record = observe(frame)
            existed = store.has(identity)
            store.save(identity, record, {"fixture_index": index, "synthetic": True})
            state["events"].append({"index": index, "screen": frame.get("screen", 1),
                                    "action": "deduplicated" if existed else "committed"})
            state["next_index"] = index + 1
            state["records"] = len(store.records())
            atomic_json(state_path, state)
            processed += 1
        else:
            state["status"] = "synthetic_fixture_complete_not_live_address_book"
    except Pause as exc:
        state["status"] = "paused"
        state["reason"] = str(exc)
        state["events"].append({"index": state["next_index"], "action": "paused", "reason": str(exc)})
    finally:
        try:
            state["records"] = len(store.records())
            try:
                store.export()
            except OSError as exc:
                state["export_error"] = type(exc).__name__
            finally:
                atomic_json(state_path, state)
        finally:
            store.db.close()
    return state
