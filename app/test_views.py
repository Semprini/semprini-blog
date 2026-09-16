from django.test import SimpleTestCase, override_settings
from django.urls import reverse


class RobotsTxtTests(SimpleTestCase):
    def test_robots_txt(self):
        response = self.client.get(reverse("robots_txt"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertEqual(
            response.content.decode(),
            "User-agent: *\n"
            "Disallow: /admin/\n"
            "Disallow: /django-admin/\n"
            "Disallow: /feedback/\n"
            "Sitemap: https://www.semprini.me/sitemap.xml\n",
        )

    def test_feedback_is_disallowed(self):
        """Crawlers that follow the comment form's action only collect 405s."""
        body = self.client.get(reverse("robots_txt")).content.decode()

        self.assertIn("Disallow: /feedback/", body)


class HeartbeatTests(SimpleTestCase):
    def test_heartbeat_is_routed(self):
        """An external monitor has polled this every 30 minutes since the app
        moved off Lambda, and got a 404 for as long as the route was missing."""
        response = self.client.get("/api/heartbeat/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/json")

    def test_heartbeat_reports_build_number(self):
        response = self.client.get(reverse("heartbeat"))

        self.assertIn("build_number", response.json())


class FaviconTests(SimpleTestCase):
    def test_favicon_redirects_to_static(self):
        response = self.client.get("/favicon.ico")

        self.assertEqual(response.status_code, 301)
        self.assertTrue(response.headers["Location"].endswith("images/favicon.ico"))

    @override_settings(
        STATIC_URL="https://s3.ap-southeast-2.amazonaws.com/semprini.me/static/"
    )
    def test_favicon_follows_static_url_to_s3(self):
        """STATIC_URL is S3 in production, so the target cannot be baked in at
        import time the way a plain RedirectView(url=...) would."""
        response = self.client.get(reverse("favicon_ico"))

        self.assertEqual(
            response.headers["Location"],
            "https://s3.ap-southeast-2.amazonaws.com/semprini.me/static/"
            "images/favicon.ico",
        )
