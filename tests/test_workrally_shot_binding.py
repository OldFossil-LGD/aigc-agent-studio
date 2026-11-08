import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import workrally_bridge


class WorkrallyShotBindingTests(unittest.TestCase):
    def test_row_matching_distinguishes_longer_identifiers(self):
        rows = [{"镜号": "镜1", "时长": "2"}, {"镜号": "镜10", "时长": "6"}]
        self.assertIs(workrally_bridge._match_row("镜10 · 收束", rows, "镜号"), rows[1])
        self.assertIsNone(workrally_bridge._match_row("镜100", rows, "镜号"))
        self.assertIs(workrally_bridge._match_row("镜1 · 建立", rows, "镜号"), rows[0])

    def test_actual_bridge_preserves_segment_and_row_binding(self):
        text = "| 镜号 | 景别 | 时长 | 叙事职能 | 唯一信息 |\n|---|---|---|---|---|\n| 镜1 | 大远景 | 2 | 建立 | FIRST_INFO |\n| 镜10 | 近景 | 6 | 收束 | TENTH_INFO |\n画幅16:9\n"
        for label in ["镜1", "镜10"]:
            text += "──────── " + label + " ────────\n决策树路径：参考主体\n```\n故事板\n```\n```\n【镜头规格】35mm\n【构图】居中\n【人物与环境】空房\n【光位与影调】窗光\n【时间线】门缓慢开启\n【运镜】固定\n【声音】无配乐，只留门声\n```\n"
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "shotlist.md"
            output = Path(temp) / "payload.json"
            source.write_text(text, encoding="utf-8")
            with patch.object(workrally_bridge, "_gate", return_value=(0, "")), contextlib.redirect_stdout(io.StringIO()) as captured:
                rc = workrally_bridge.bridge(str(source), out_json=str(output))
            self.assertEqual(rc, 0, captured.getvalue())
            shots = json.loads(output.read_text(encoding="utf-8"))["per_shot"]
            self.assertEqual([shot["label"] for shot in shots], ["镜1", "镜10"])
            self.assertEqual([shot["dur"] for shot in shots], [2.0, 6.0])
            self.assertEqual([shot["info"] for shot in shots], ["FIRST_INFO", "TENTH_INFO"])


if __name__ == "__main__":
    unittest.main()
