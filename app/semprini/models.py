from django.db import models
from django.utils.translation import gettext_lazy as _

from wagtail.models import Page, Site


class HomePage(Page):
    pass


class Subtitle(models.Model):
    id = models.AutoField(primary_key=True)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="subtitles", )
    value = models.CharField(
        verbose_name=_("subtitle text"), max_length=200, )
    reference = models.URLField(max_length=200, blank=True, null=False)
