import re
import time
from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import LecturaLiturgica

SECCIONES = (
    ('primera_lectura', 'PRIMERA LECTURA'),
    ('salmo', 'SALMO'),
    ('segunda_lectura', 'SEGUNDA LECTURA'),
    ('aclamacion', 'ACLAMACIÓN'),
    ('evangelio', 'EVANGELIO'),
)
FINES = [x[1] for x in SECCIONES] + [
    'ORACIÓN SOBRE LAS OFRENDAS', 'ANTÍFONA DE LA COMUNIÓN',
    'ORACIÓN DESPUÉS DE LA COMUNIÓN', 'ORACIÓN DESPÚES DE LA COMUNIÓN',
]


class TextoHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.partes = []

    def handle_data(self, data):
        texto = ' '.join(data.split())
        if texto:
            self.partes.append(texto)


def domingo_advento(anio):
    fecha = date(anio, 11, 27)
    return fecha + timedelta(days=(6 - fecha.weekday()) % 7)


def ciclo_fecha(fecha):
    if fecha.weekday() == 6:
        anio_liturgico = fecha.year if fecha >= domingo_advento(fecha.year) else fecha.year - 1
        return ('A', 'B', 'C')[(anio_liturgico - 2025) % 3]
    return 'I' if fecha.year % 2 else 'II'


def extraer_seccion(texto, titulo):
    """
    Extrae una sección cuyo encabezado ocupa una línea completa.
    Así no confunde palabras dentro del contenido, por ejemplo
    'Del salmo 118' o 'Del santo Evangelio'.
    """
    patron_titulo = re.compile(
        r'^\s*' + re.escape(titulo) + r'\s*$',
        re.IGNORECASE | re.MULTILINE,
    )
    coincidencia = patron_titulo.search(texto)
    if not coincidencia:
        return ''

    inicio = coincidencia.end()
    fin = len(texto)

    for siguiente in FINES:
        patron_siguiente = re.compile(
            r'^\s*' + re.escape(siguiente) + r'\s*$',
            re.IGNORECASE | re.MULTILINE,
        )
        match = patron_siguiente.search(texto, inicio)
        if match:
            fin = min(fin, match.start())

    return texto[inicio:fin].strip(' :-–—\n\r')


def extraer_nombre_celebracion(texto):
    """
    Misal.mx puede separar el rótulo 'Santos:' y los nombres en nodos
    de texto distintos. Se admite que el santoral esté en la misma línea
    o en la siguiente, sin confundirlo con el nombre de la celebración.
    """
    match = re.search(
        r'^[ \t]*Santos:[ \t]*(?:\n[ \t]*)?([^\n]+)',
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        return ''
    return ('Santos del día: ' + match.group(1).strip())[:200]


def obtener_lecturas(fecha):
    url = 'https://misal.mx/' + fecha.isoformat()
    request = Request(url, headers={'User-Agent': 'EmausLiturgicalCalendar/1.0'})
    with urlopen(request, timeout=25) as response:
        html = response.read().decode(
            response.headers.get_content_charset() or 'utf-8',
            errors='replace'
        )

    parser = TextoHTML()
    parser.feed(html)
    texto = '\n'.join(parser.partes)

    datos = {campo: extraer_seccion(texto, titulo) for campo, titulo in SECCIONES}
    datos['nombre_celebracion'] = extraer_nombre_celebracion(texto)

    if not datos['primera_lectura'] or not datos['salmo'] or not datos['evangelio']:
        faltantes = [
            campo for campo in ('primera_lectura', 'salmo', 'evangelio')
            if not datos[campo]
        ]
        raise ValueError(
            'No se encontraron secciones obligatorias: ' + ', '.join(faltantes)
            + '; se omitió la fecha.'
        )

    return url, datos


class Command(BaseCommand):
    help = 'Importa lecturas de Misal.mx por día/mes y ciclo litúrgico.'

    def add_arguments(self, parser):
        parser.add_argument('--desde', type=date.fromisoformat, required=True, help='YYYY-MM-DD')
        parser.add_argument('--hasta', type=date.fromisoformat, required=True, help='YYYY-MM-DD')
        parser.add_argument('--pausa', type=float, default=1.0)
        parser.add_argument('--sobrescribir', action='store_true')

    def handle(self, *args, **opciones):
        desde, hasta = opciones['desde'], opciones['hasta']
        if hasta < desde:
            raise CommandError('--hasta debe ser igual o posterior a --desde.')
        if opciones['pausa'] < 0:
            raise CommandError('--pausa no puede ser negativa.')

        fecha = desde
        nuevas = actualizadas = existentes = errores = 0

        while fecha <= hasta:
            ciclo = ciclo_fecha(fecha)
            try:
                url, datos = obtener_lecturas(fecha)
                defaults = {**datos, 'fecha_fuente': fecha, 'url_fuente': url}

                with transaction.atomic():
                    registro, creada = LecturaLiturgica.objects.get_or_create(
                        dia=fecha.day,
                        mes=fecha.month,
                        ciclo=ciclo,
                        fecha_especifica__isnull=True,
                        defaults=defaults,
                    )

                    if creada:
                        nuevas += 1
                    elif opciones['sobrescribir']:
                        for campo, valor in defaults.items():
                            setattr(registro, campo, valor)
                        registro.save()
                        actualizadas += 1
                    else:
                        existentes += 1

                self.stdout.write(self.style.SUCCESS(f'{fecha} · ciclo {ciclo}: OK'))

            except Exception as exc:
                errores += 1
                self.stderr.write(self.style.WARNING(f'{fecha}: {exc}'))

            fecha += timedelta(days=1)
            if fecha <= hasta and opciones['pausa']:
                time.sleep(opciones['pausa'])

        self.stdout.write(self.style.SUCCESS(
            f'Finalizado: {nuevas} nuevas, {actualizadas} actualizadas, '
            f'{existentes} existentes, {errores} errores.'
        ))
