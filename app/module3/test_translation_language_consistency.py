import unittest
from unittest.mock import patch

from app.module3.ai_translate_cached import translate_defect_payload_cached
from app.module3.report_data import build_defect_list


class TranslationLanguageConsistencyTests(unittest.TestCase):
    def test_translate_defect_payload_translates_description_and_remarks(self):
        source_defects = [
            {
                "id": 101,
                "unit": "A-10-1",
                "desc": "Paip bocor di bawah sinki dapur",
                "remarks": "Sila baiki segera",
                "priority": "Tinggi",
            }
        ]

        translated_defects = [
            {
                "id": 101,
                "unit": "A-10-1",
                "desc": "Leaking pipe under the kitchen sink",
                "remarks": "Sila baiki segera",
                "priority": "High",
            }
        ]

        with patch(
            "app.module3.ai_translate_cached.translate_defects_cached",
            return_value=translated_defects,
        ) as mock_translate_defects, patch(
            "app.module3.ai_translate_cached.translate_remark_cached",
            return_value="Please repair immediately",
        ) as mock_translate_remark:
            result = translate_defect_payload_cached(
                source_defects,
                language="en",
                role="Homeowner",
                include_remarks=True,
            )

        self.assertEqual(
            result[0]["desc"],
            "Leaking pipe under the kitchen sink",
        )
        self.assertEqual(result[0]["remarks"], "Please repair immediately")
        self.assertEqual(result[0]["priority"], "High")
        self.assertEqual(source_defects[0]["remarks"], "Sila baiki segera")
        mock_translate_defects.assert_called_once()
        mock_translate_remark.assert_called_once_with(
            "Sila baiki segera",
            language="en",
            role="Homeowner",
        )

    def test_translate_defect_payload_hides_remarks_when_not_requested(self):
        source_defects = [
            {
                "id": 102,
                "unit": "B-05-2",
                "desc": "Tile retak",
                "remarks": "Mohon gantikan",
            }
        ]

        with patch(
            "app.module3.ai_translate_cached.translate_defects_cached",
            return_value=[dict(source_defects[0], desc="Cracked tile")],
        ), patch(
            "app.module3.ai_translate_cached.translate_remark_cached"
        ) as mock_translate_remark:
            result = translate_defect_payload_cached(
                source_defects,
                language="en",
                role="Developer",
                include_remarks=False,
            )

        self.assertEqual(result[0]["desc"], "Cracked tile")
        self.assertEqual(result[0]["remarks"], "")
        mock_translate_remark.assert_not_called()

    def test_build_defect_list_prefers_translated_priority(self):
        defects = [
            {
                "id": 103,
                "unit": "C-01-5",
                "desc": "Keretakan dinding",
                "status": "Completed",
                "reported_date": "2026-01-01",
                "deadline": "2026-01-15",
                "completed_date": "2026-01-10",
                "is_overdue": False,
                "hda_compliant": True,
                "urgency": "High",
                "priority": "Tinggi",
            }
        ]

        result = build_defect_list(defects, role="Homeowner")

        self.assertEqual(result[0]["priority"], "Tinggi")


if __name__ == "__main__":
    unittest.main()
