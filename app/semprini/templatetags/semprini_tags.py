from django import template
from semprini.models import Subtitle
from random import choice

register = template.Library()

# Subtitle snippets
@register.inclusion_tag('semprini/tags/subtitle.html', takes_context=True)
def subtitle(context):
    pks = list(Subtitle.objects.values_list('pk', flat=True))
    random_obj = Subtitle.objects.get(pk=choice(pks)) if pks else None

    return {
        'subtitle': random_obj,
        'request': context['request'],
    }
