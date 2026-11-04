import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from src.core import COLUMNS, Pause, Store, advance, edit_fields, profile_fields, selected_row
from src.fixtures import edit, line, navigation_image, profile, replay_cases
from src.replay import observe, run_replay


class ParsingTests(unittest.TestCase):
    def test_nickname_is_not_remark(self):
        self.assertEqual(profile_fields(profile())["name"], "演示甲")

    def test_expected_annotations_do_not_drive_parsing(self):
        frame = replay_cases()[0]
        before = observe(frame)
        frame["expected"] = {"电话号码": "deliberately_wrong_answer"}
        self.assertEqual(observe(frame), before)

    def test_missing_identity_pauses(self):
        with self.assertRaises(Pause):
            profile_fields([row for row in profile() if "微信号" not in row["text"]])

    def test_unconfirmed_id_separator_pauses(self):
        frame = replay_cases()[0]
        frame["profile"] = profile(identity="wxid alpha")
        with self.assertRaises(Pause):
            observe(frame)

    def test_id_separator_confirmation_matches(self):
        frame = replay_cases()[0]
        frame["profile"] = profile(identity="wxid alpha")
        frame["profile_alt"] = profile(identity="wxid_alpha")
        self.assertEqual(observe(frame)[0], "wxid_alpha")

    def test_empty_requires_complete_boundary(self):
        self.assertEqual(edit_fields(edit(), False)["phone"], "没有")
        self.assertEqual(edit_fields(edit(complete=False), False)["phone"], "待核对")

    def test_blank_is_not_empty(self):
        with self.assertRaises(Pause):
            edit_fields([], False)

    def test_multiple_numbers_preserved(self):
        result = edit_fields(edit(phones=["00000000001", "00000000002"]), False)
        self.assertEqual(result["phone"], "00000000001；00000000002")

    def test_unusual_length_not_repaired(self):
        self.assertEqual(edit_fields(edit(phones=["000000000003"]), False)["phone"], "000000000003")

    def test_long_remark_is_retained(self):
        value = "长备注测试" * 8
        self.assertEqual(edit_fields(edit(remark=value), False)["remark"], value)

    def test_explicit_missing_remark(self):
        self.assertEqual(edit_fields(edit(remark="占位文字"), True)["remark"], "没有")

    def test_missing_cancel_pauses(self):
        with self.assertRaises(Pause):
            edit_fields([row for row in edit() if row["text"] != "取消"], False)

    def test_partial_cancel_needs_done_on_same_row(self):
        rows = [row for row in edit() if row["text"] not in ("取消", "完成")]
        with self.assertRaises(Pause):
            edit_fields(rows + [line("取", 740, 300)], False)
        self.assertIn("cancel", edit_fields(rows + [line("完成", 740, 40), line("取", 740, 300)], False))

    def test_low_confidence_digits_pause(self):
        frame = replay_cases()[0]
        frame["edit"][-4]["confidence"] = 0.2
        for row in frame["edit"]:
            if row["text"] == "00000000001":
                row["confidence"] = 0.2
        with self.assertRaises(Pause):
            observe(frame)

    def test_two_readings_disagree(self):
        frame = replay_cases()[0]
        frame["edit_alt"] = edit(phones=["00000000009"])
        with self.assertRaises(Pause):
            observe(frame)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pause_then_resume_without_duplication(self):
        frames = replay_cases()
        first = run_replay(frames, self.root)
        self.assertEqual((first["status"], first["records"], first["next_index"]), ("paused", 2, 2))
        second = run_replay(frames, self.root, resume=True, use_repairs=True)
        self.assertEqual((second["records"], second["next_index"]), (6, 7))
        self.assertEqual(second["status"], "synthetic_fixture_complete_not_live_address_book")
        self.assertEqual(sum(e["action"] == "deduplicated" for e in second["events"]), 1)

    def test_stop_before_first_save(self):
        state = run_replay(replay_cases(), self.root, stop_requested=True)
        self.assertEqual((state["status"], state["records"]), ("paused", 0))

    def test_limited_scope_not_full_book(self):
        state = run_replay(replay_cases(), self.root, limit=1)
        self.assertEqual(state["status"], "limit_reached_not_full_address_book")
        self.assertEqual(state["records"], 1)

    def test_changed_fixture_resume_rejected(self):
        frames = replay_cases()
        run_replay(frames, self.root)
        frames[0]["screen"] = 99
        with self.assertRaises(ValueError):
            run_replay(frames, self.root, resume=True)

    def test_new_run_does_not_overwrite(self):
        run_replay(replay_cases(), self.root)
        with self.assertRaises(ValueError):
            run_replay(replay_cases(), self.root)

    def test_focus_geometry_account_changes_pause(self):
        for key in ("focus_ok", "geometry_ok", "account_ok"):
            with self.subTest(key=key):
                frames = replay_cases()
                frames[0][key] = False
                state = run_replay(frames, self.root / key)
                self.assertEqual(state["records"], 0)
                self.assertIn(key, state["reason"])

    def test_user_stop_in_frame_pauses(self):
        frames = replay_cases()
        frames[1]["stop_before_save"] = True
        state = run_replay(frames, self.root)
        self.assertEqual(state["records"], 1)

    def test_same_remark_different_identity_kept(self):
        state = run_replay(replay_cases(), self.root, limit=2)
        self.assertEqual(state["records"], 2)

    def test_identity_collision_does_not_overwrite(self):
        frames = replay_cases()[:2]
        frames[1]["profile"] = profile("另一演示", "demo_alpha")
        state = run_replay(frames, self.root)
        self.assertEqual(state["records"], 1)
        self.assertIn("冲突", state["reason"])

    def test_export_error_keeps_database_and_state(self):
        frames = replay_cases()
        with patch.object(Store, "export", side_effect=PermissionError("simulated lock")):
            state = run_replay(frames, self.root)
        self.assertEqual(state["records"], 2)
        self.assertEqual(json.loads((self.root / "state.json").read_text(encoding="utf-8"))["export_error"], "PermissionError")
        resumed = run_replay(frames, self.root, resume=True, use_repairs=True)
        self.assertEqual(resumed["records"], 6)
        self.assertNotIn("export_error", resumed)

    def test_text_export_prevents_numeric_coercion_and_formulas(self):
        store = Store(self.root)
        row = dict(zip(COLUMNS, ["=DEMO()", "+demo", "00000000001"]))
        store.save("fictional", row, {"synthetic": True})
        store.export()
        self.assertIn("'=DEMO()", (self.root / "联系人.csv").read_text(encoding="utf-8-sig"))
        with zipfile.ZipFile(self.root / "联系人.xlsx") as archive:
            xml = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            self.assertTrue(all(c.attrib["t"] == "inlineStr" for c in xml.findall(".//m:c", ns)))
            self.assertFalse(xml.findall(".//m:f", ns))
            self.assertEqual(xml.findall(".//m:t", ns)[-1].text, "00000000001")
        store.db.close()


class NavigationTests(unittest.TestCase):
    class Desktop:
        def __init__(self, current, clicked=None, scrolled=None):
            self.current, self.clicked, self.scrolled, self.scrolls = current, clicked, scrolled, 0
        def capture(self):
            return self.current
        def click(self, x, y):
            if self.clicked is not None:
                self.current = self.clicked
        def scroll_list(self):
            self.scrolls += 1
            if self.scrolled is not None:
                self.current = self.scrolled

    def test_selected_row_from_synthetic_image(self):
        a, b = selected_row(navigation_image())
        self.assertGreater(b - a, 25)

    def test_advance_uses_changed_profile(self):
        desktop = self.Desktop(navigation_image(), navigation_image("demo_next", selected=1))
        self.assertEqual(advance(desktop), "advanced")

    def test_cross_screen_navigation(self):
        old = navigation_image("demo_same", selected=1, rows=(180, 260))
        scrolled = navigation_image("demo_same", selected=0, rows=(180, 260))
        desktop = self.Desktop(old, navigation_image("demo_next", selected=1), scrolled)
        self.assertEqual(advance(desktop), "advanced")
        self.assertGreaterEqual(desktop.scrolls, 1)

    def test_stalled_is_not_completed(self):
        desktop = self.Desktop(navigation_image())
        self.assertEqual(advance(desktop), "navigation_stalled_or_end_needs_check")

    def test_visible_end_requires_two_stable_scrolls(self):
        desktop = self.Desktop(navigation_image(selected=0, rows=(180,)))
        self.assertEqual(advance(desktop), "visible_list_end_reached_scope_from_selected_start")
        self.assertEqual(desktop.scrolls, 2)

    def test_tail_content_prevents_end_claim(self):
        desktop = self.Desktop(navigation_image(selected=0, rows=(180,), tail_noise=True))
        self.assertEqual(advance(desktop), "navigation_stalled_or_end_needs_check")

    def test_missing_selection_pauses(self):
        from PIL import Image
        with self.assertRaises(Pause):
            selected_row(Image.new("RGB", (846, 832), (43, 43, 43)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
