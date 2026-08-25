import unittest
from unittest.mock import patch

from backend.app.services.news_translation_service import localize_market_brief
from news_panel import _translation_looks_incomplete


class KoreanNewsLocalizationTests(unittest.TestCase):
    def test_incomplete_provider_responses_are_rejected(self):
        self.assertTrue(_translation_looks_incomplete("유나이티드 커뮤니티 뱅크 (United Community"))
        self.assertTrue(_translation_looks_incomplete("집행 조치를 내"))
        self.assertFalse(_translation_looks_incomplete("집행 조치를 내렸습니다."))

    @patch("backend.app.services.news_translation_service._translate_to_korean")
    def test_display_translation_preserves_original_signal_title(self, translate):
        translate.side_effect = lambda title: f"번역: {title}"
        brief = {"bias": "neutral", "top": [{"title": "Bitcoin rises", "long_event_score": 2.0}]}

        localized = localize_market_brief(brief)

        self.assertEqual(localized["top"][0]["title"], "Bitcoin rises")
        self.assertEqual(localized["top"][0]["title_ko"], "번역: Bitcoin rises")
        self.assertNotIn("title_ko", brief["top"][0])

    @patch("backend.app.services.news_translation_service._translate_to_korean")
    def test_existing_translation_is_reused_without_network_call(self, translate):
        localized = localize_market_brief({"top": [{"title": "Original", "title_ko": "기존 번역"}]})

        self.assertEqual(localized["top"][0]["title_ko"], "기존 번역")
        translate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
