from django import template
from django.utils.safestring import mark_safe
import re

register = template.Library()

def limpiar_letra(texto):

    # convertir tabs a espacios reales
    texto = texto.replace('\t', '    ')

    return texto

@register.filter(name='colorear_acordes')
def colorear_acordes(texto):

    acordes = [
        'DO','RE','MI','FA','SOL','LA','SI',
        'DOM','REM','MIM','FAM','SOLM','LAM','SIM',
        'do','re','mi','fa','sol','la','si',
        'DO#','RE#','FA#','SOL#','LA#',
        'DOm','REm','MIm','FAm','SOLm','LAm','SIm',
        'DO7','RE7','MI7','FA7','SOL7','LA7','SI7',
        'DOB','REB','MIB','FAB','SOLB','LAB','SIB',
    ]

    patron = r'\b(' + '|'.join(acordes) + r')\b'

    texto = re.sub(
        patron,
        r'<span class="acorde">\1</span>',
        texto
    )

    texto = texto.replace('\n','<br>')

    return mark_safe(texto)