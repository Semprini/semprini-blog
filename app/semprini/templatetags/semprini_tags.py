from django import template
from semprini.models import Subtitle
from random import choice

register = template.Library()

# Subtitle snippets
@register.inclusion_tag('semprini/tags/subtitle.html', takes_context=True)
def subtitle(context):
    pks = Subtitle.objects.values_list('pk', flat=True)
    random_pk = choice(pks)
    random_obj = Subtitle.objects.get(pk=random_pk)


    return {
        'subtitle': random_obj,
        'request': context['request'],
    }
