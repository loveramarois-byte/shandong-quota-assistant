from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from utils import sessions


def _result(query: str, code: str, record_id: str) -> dict:
    return {
        "query": query,
        "quota_edition": "2025",
        "standard_edition": "2024",
        "discipline": "building",
        "conditions": {"object_type": "沟槽"},
        "timing": {"local_ms": 12.3},
        "search_backend": "fts",
        "bills": [],
        "quotas": [{
            "record_id": record_id,
            "reference": "R1",
            "code": code,
            "title": f"候选 {code}",
            "unit": "10m³",
            "edition": "2025",
            "discipline": "building",
            "text": "不写入会话的大段原文",
            "metadata": {"private": True},
            "source_path": r"X:\\fixtures\\source.pdf",
        }],
        "links": [],
        "guidance": [],
    }


class SessionStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        patcher = mock.patch.object(sessions, "sessions_dir", lambda: self.tmp_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def _create(self, title: str = "测试会话") -> dict:
        return sessions.create_session(title)

    def test_create_and_load_v2_roundtrip(self):
        session = self._create("挖沟槽分析")
        turn = sessions.create_turn(session, "挖沟槽土方", quota_edition="2025", standard_edition="2024", discipline="building", request_id=1)
        result = _result("挖沟槽土方", "1-2-9", "quota:171:33")
        sessions.set_turn_local_result(session, turn["turn_id"], result, ai_enabled=False)
        sessions.save_session(session)

        loaded = sessions.load_session(session["id"])

        self.assertEqual(loaded["schema_version"], 2)
        self.assertEqual(loaded["title"], "挖沟槽分析")
        self.assertEqual(loaded["turns"][0]["query"], "挖沟槽土方")
        self.assertEqual(loaded["turns"][0]["retrieval_snapshot"]["quotas"][0]["record_id"], "quota:171:33")

    def test_three_turns_keep_result_ai_and_selection_bound(self):
        session = self._create("三轮测试")
        expected = []
        for index in range(3):
            query = f"第{index + 1}轮"
            code = f"1-2-{index + 8}"
            record_id = f"quota:171:{index + 32}"
            turn = sessions.create_turn(session, query, quota_edition="2025", standard_edition="2024", discipline="building", request_id=index + 1)
            result = _result(query, code, record_id)
            sessions.set_turn_local_result(session, turn["turn_id"], result, ai_enabled=True)
            sessions.start_ai_attempt(session, turn["turn_id"], request_id=index + 1, model="test-model")
            sessions.finish_ai_attempt(session, turn["turn_id"], request_id=index + 1, status="completed", response=f"AI {index + 1} [{result['quotas'][0]['reference']}]", validation={"evidence_verified": False})
            sessions.set_turn_selection(session, turn["turn_id"], "quota", result["quotas"][0])
            expected.append((query, code, record_id, f"AI {index + 1} [R1]"))
        sessions.save_session(session)

        loaded = sessions.load_session(session["id"])
        actual = []
        for turn in loaded["turns"]:
            quota = turn["retrieval_snapshot"]["quotas"][0]
            selected = turn["human_selections"]["primary"]["quota"]
            actual.append((turn["query"], quota["code"], selected["record_id"], turn["ai_attempts"][-1]["response"]))
        self.assertEqual(actual, expected)

    def test_serialize_result_does_not_silently_slice_candidates(self):
        result = _result("q", "1-1-1", "quota:1:1")
        result["links"] = [
            {"record_id": f"link:2024:{index}", "code": f"1-1-{index}", "title": "关联"}
            for index in range(24)
        ]

        slim = sessions.serialize_result(result)

        self.assertEqual(len(slim["links"]), 24)
        self.assertNotIn("text", slim["quotas"][0])
        self.assertNotIn("metadata", slim["quotas"][0])
        self.assertNotIn("source_path", slim["quotas"][0])

    def test_auto_discipline_switch_survives_save_and_load(self):
        session = self._create("自动识别专业")
        turn = sessions.create_turn(
            session,
            "C15混凝土垫层，厚度100mm",
            quota_edition="2025",
            standard_edition="2024",
            discipline="installation",
        )
        result = _result("C15混凝土垫层，厚度100mm", "2-1-28", "quota:building:28")
        result.update({
            "requested_discipline": "installation",
            "discipline_auto_switched": True,
            "discipline_switch_reason": "安装专业没有可靠清单，已按施工描述切换到建筑专业。",
        })
        sessions.set_turn_local_result(session, turn["turn_id"], result, ai_enabled=False)
        sessions.save_session(session)

        loaded = sessions.load_session(session["id"])
        snapshot = loaded["turns"][0]["retrieval_snapshot"]

        self.assertEqual(snapshot["requested_discipline"], "installation")
        self.assertTrue(snapshot["discipline_auto_switched"])
        self.assertEqual(snapshot["discipline_switch_reason"], result["discipline_switch_reason"])

    def test_ai_validation_does_not_persist_machine_specific_source_paths(self):
        session = self._create("证据路径测试")
        turn = sessions.create_turn(session, "测试", quota_edition="2025", standard_edition="2024", discipline="building")
        sessions.finish_ai_attempt(
            session,
            turn["turn_id"],
            request_id=1,
            status="completed",
            response="回答 [R1]",
            validation={
                "evidence_verified": True,
                "evidence_located": 1,
                "evidence_total": 1,
                "evidence": [{"reference": "R1", "source_path": r"D:\private\source.pdf", "pdf_page": 9}],
                "located_references": [{"reference": "R1", "source_path": r"D:\private\source.pdf"}],
            },
        )

        saved = turn["ai_attempts"][-1]["validation"]

        self.assertEqual(saved["evidence_located"], 1)
        self.assertNotIn("source_path", saved["evidence"][0])
        self.assertNotIn("source_path", saved["located_references"][0])

    def test_v1_migration_preserves_original_backup_and_unpaired_messages(self):
        session_id = "legacy123"
        source_path = self.tmp_dir / f"{session_id}.json"
        source_path.write_text(json.dumps({
            "id": session_id,
            "title": "旧记录",
            "created_at": 1,
            "updated_at": 2,
            "messages": [
                {"role": "user", "text": "第一次"},
                {"role": "ai", "text": "第一次回答"},
                {"role": "user", "text": "第二次"},
                {"role": "ai", "text": "第二次回答"},
            ],
            "result": _result("第二次", "1-2-9", "quota:171:33"),
            "selections": {},
        }, ensure_ascii=False), encoding="utf-8")

        migrated = sessions.load_session(session_id)
        self.assertEqual(migrated["schema_version"], 2)
        self.assertIn("legacy_unpaired_messages", migrated)
        sessions.save_session(migrated)

        self.assertTrue(source_path.with_suffix(".v1.bak").exists())
        reloaded = sessions.load_session(session_id)
        self.assertEqual(reloaded["turns"][0]["query"], "第二次")

    def test_corrupt_primary_file_recovers_last_backup(self):
        session = self._create("恢复测试")
        sessions.save_session(session)
        path = self.tmp_dir / f"{session['id']}.json"
        self.assertTrue(path.with_suffix(".bak").exists())
        path.write_text("{broken", encoding="utf-8")

        recovered = sessions.load_session(session["id"])

        self.assertIsNotNone(recovered)
        self.assertEqual(recovered["title"], "恢复测试")

    def test_disk_full_during_fsync_keeps_primary_and_cleans_temp_file(self):
        session = self._create("磁盘满测试")
        sessions.create_turn(session, "未保存轮次", quota_edition="2025", standard_edition="2024", discipline="building")

        with mock.patch.object(sessions.os, "fsync", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                sessions.save_session(session)

        loaded = sessions.load_session(session["id"])
        self.assertEqual(loaded["turns"], [])
        self.assertEqual(list(self.tmp_dir.glob("*.tmp")), [])

    def test_permission_error_during_replace_keeps_primary_and_cleans_temp_file(self):
        session = self._create("权限测试")
        sessions.create_turn(session, "未保存轮次", quota_edition="2025", standard_edition="2024", discipline="building")

        with mock.patch.object(sessions.os, "replace", side_effect=PermissionError("access denied")):
            with self.assertRaises(PermissionError):
                sessions.save_session(session)

        loaded = sessions.load_session(session["id"])
        self.assertEqual(loaded["turns"], [])
        self.assertEqual(list(self.tmp_dir.glob("*.tmp")), [])

    def test_legal_json_with_wrong_field_types_is_rejected(self):
        path = self.tmp_dir / "invalid.json"
        path.write_text(json.dumps({"schema_version": 2, "id": "invalid", "turns": "not-a-list"}), encoding="utf-8")
        self.assertIsNone(sessions.load_session("invalid"))

    def test_delete_tombstone_prevents_late_save_resurrection(self):
        session = self._create("待删除")
        self.assertTrue(sessions.delete_session(session["id"]))
        self.assertIsNone(sessions.load_session(session["id"]))
        with self.assertRaises(sessions.SessionDeletedError):
            sessions.save_session(session)
        self.assertFalse((self.tmp_dir / f"{session['id']}.json").exists())
        self.assertTrue(list((self.tmp_dir / "trash").glob(f"{session['id']}-*.json")))

    def test_list_and_rename(self):
        first = self._create("较早")
        second = self._create("较新")
        self.assertTrue(sessions.rename_session(first["id"], "新名字"))
        listing = sessions.list_sessions()
        self.assertEqual(listing[0]["id"], first["id"])
        self.assertEqual(sessions.load_session(first["id"])["title"], "新名字")
        self.assertIn(second["id"], {item["id"] for item in listing})

    def test_list_reads_header_without_parsing_large_session_body(self):
        session = self._create('带“引号”的会话')
        turn = sessions.create_turn(session, "测试摘要读取", quota_edition="2025", standard_edition="2024", discipline="building")
        sessions.set_turn_local_result(session, turn["turn_id"], _result("测试摘要读取", "1-2-9", "quota:171:33"), ai_enabled=False)
        sessions.save_session(session)

        with mock.patch.object(sessions, "load_session", side_effect=AssertionError("fast summary path should be used")):
            listing = sessions.list_sessions()

        self.assertEqual(listing[0]["id"], session["id"])
        self.assertEqual(listing[0]["title"], '带“引号”的会话')

    def test_export_markdown_keeps_turn_boundaries_and_disclaimer(self):
        session = self._create("导出测试")
        turn = sessions.create_turn(session, "挖沟槽", quota_edition="2025", standard_edition="2024", discipline="building")
        sessions.set_turn_local_result(session, turn["turn_id"], _result("挖沟槽", "1-2-9", "quota:171:33"), ai_enabled=False)

        text = sessions.export_session_markdown(session)

        self.assertIn("第 1 轮", text)
        self.assertIn("候选快照", text)
        self.assertIn("不等于正式计价成果", text)


if __name__ == "__main__":
    unittest.main()
