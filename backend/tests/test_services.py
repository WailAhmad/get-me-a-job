import unittest

from app.services.cv_parser import parse_cv_text
from app.services.job_import import parse_job_text


class ServiceTests(unittest.TestCase):
    def test_parse_job_text(self):
        job = parse_job_text(
            """
            Job Title: Head of AI
            Company: Example Bank
            Location: Bahrain
            Lead Azure, Databricks, LLM, RAG and governance delivery.
            https://careers.examplebank.test/head-ai
            """,
            "",
            "Manual",
        )
        self.assertEqual(job["title"], "Head of AI")
        self.assertEqual(job["company"], "Example Bank")
        self.assertEqual(job["country"], "Bahrain")
        self.assertIn("https://careers.examplebank.test/head-ai", job["job_url"])

    def test_parse_cv_text(self):
        parsed = parse_cv_text(
            """
            Wael Example
            Head of AI at Example Group
            Bahrain
            wael@example.com
            https://www.linkedin.com/in/wael-example
            15+ years experience in AI strategy, data architecture, Azure, AWS, Databricks, Collibra and Purview.
            Education
            MSc Computer Science
            Certifications
            Azure Architect
            Delivered enterprise AI transformation across banking and government.
            """,
            "cv.docx",
        )
        self.assertEqual(parsed.profile["full_name"], "Wael Example")
        self.assertEqual(parsed.profile["email"], "wael@example.com")
        self.assertIn("Azure", parsed.profile["cloud_platforms"])
        self.assertIn("Collibra", parsed.profile["governance_tools"])


if __name__ == "__main__":
    unittest.main()

