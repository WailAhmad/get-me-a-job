import unittest
from unittest.mock import patch

from backend.routers.automation import _is_infrastructure_apply_error, _live_search_keywords, _score
from backend.services.form_brain import best_option_match, normalise_for_match
from backend.services.linkedin_applier import _profile_answer


class AutomationFilterTests(unittest.TestCase):
    def setUp(self):
        self.cv = {
            "skills": ["AI", "Data Governance", "Machine Learning", "Digital Transformation"],
            "years": 15,
        }
        self.prefs = {
            "country": "GCC",
            "countries": ["UAE", "Saudi Arabia", "Qatar", "Kuwait", "Bahrain", "Oman"],
        }

    def test_role_families_become_linkedin_searchable_keywords(self):
        keywords = _live_search_keywords([
            "AI & Data Leadership",
            "Data & AI Product",
            "AI Solutions Architecture",
        ])

        self.assertLessEqual(len(keywords), 10)
        self.assertIn("Head of AI", keywords)
        self.assertIn("AI Product", keywords)
        self.assertIn("AI Architect", keywords)
        self.assertNotIn("AI & Data Leadership", keywords)
        self.assertNotIn("Data & AI Product", keywords)
        self.assertNotIn("AI Solutions Architecture", keywords)

    @patch("backend.routers.automation.random.randint", return_value=0)
    def test_leaky_roles_stay_below_apply_threshold(self, _):
        leaky_titles = [
            "Growth Marketing Executive (Funnels, Automation & AI)",
            "Business Developer — Industrial Services (AI Platform · Startup)",
            "Data Visualization And Media Specialist",
            "AI Engineering Specialist",
            "AI Workflow Engineer (Claude + Cursor)",
        ]

        for title in leaky_titles:
            with self.subTest(title=title):
                score = _score({"title": title, "company": "Example", "location": "Dubai"}, self.cv, self.prefs)
                self.assertLess(score, 60)

    @patch("backend.routers.automation.random.randint", return_value=0)
    def test_real_target_roles_still_match(self, _):
        score = _score(
            {"title": "Data Governance Chief Specialist", "company": "Brainlake", "location": "Kuwait"},
            self.cv,
            self.prefs,
        )
        self.assertGreaterEqual(score, 80)

    def test_name_answers_come_from_current_cv_or_profile(self):
        cv = {"name": "Hend Aboseda"}
        self.assertEqual(_profile_answer("first name", cv, {}), "Hend")
        self.assertEqual(_profile_answer("given name", cv, {}), "Hend")
        self.assertEqual(_profile_answer("last name", cv, {}), "Aboseda")
        self.assertIsNone(_profile_answer("first name", {}, {}))

    def test_proficiency_option_normalization(self):
        self.assertEqual(normalise_for_match("Native / Bilingual"), "native or bilingual")
        self.assertEqual(
            best_option_match("Native or bilingual", ["Fluent", "Native / Bilingual", "Professional working proficiency"]),
            "Native / Bilingual",
        )
        self.assertEqual(
            best_option_match("Research and Development", ["Research & Development", "Operations"]),
            "Research & Development",
        )

    def test_easy_apply_form_errors_are_recoverable(self):
        recoverable_errors = [
            "Too many steps without submit",
            "No Next/Submit button found",
            "Submit clicked but no confirmation",
            "Form field we couldn't fill: Please enter a valid answer",
            "Required Easy Apply field did not accept an answer",
        ]
        for err in recoverable_errors:
            with self.subTest(err=err):
                self.assertFalse(_is_infrastructure_apply_error(err))

    def test_only_infrastructure_errors_become_failed(self):
        infrastructure_errors = [
            "LinkedIn session expired (redirected to login)",
            "checkpoint challenge",
            "captcha required",
            "webdriver disconnected from chrome",
            "Navigation failed: timeout",
        ]
        for err in infrastructure_errors:
            with self.subTest(err=err):
                self.assertTrue(_is_infrastructure_apply_error(err))


if __name__ == "__main__":
    unittest.main()
