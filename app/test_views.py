from django.test import SimpleTestCase
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
            "Sitemap: https://www.semprini.me/sitemap.xml\n",
        )