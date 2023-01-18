from django import template
from colorhash import ColorHash


register = template.Library()

@register.filter(name='colorize')
def colorize(name):
    try:
        color = ColorHash(name)
        return color.hex
    except KeyError:
        return '#FFF'
