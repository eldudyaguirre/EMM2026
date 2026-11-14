import csv
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.liturgia import referencias_ordenadas


CAMPOS_CITA = (
    'primera_lectura_ref',
    'salmo_ref',
    'segunda_lectura_ref',
    'aclamacion_ref',
    'evangelio_ref',
)


class Command(BaseCommand):
    help = 'Compara las referencias de distintas fuentes cuando existen para una misma fecha.'

    def add_arguments(self, parser):
        parser.add_argument('--anio', type=int, required=True)
        parser.add_argument('--salida', default='')

    def handle(self, *args, **options):
        anio = options['anio']
        if not 1900 <= anio <= 2200:
            raise CommandError('--anio debe estar entre 1900 y 2200.')

        inicio, fin = date(anio, 1, 1), date(anio, 12, 31)
        grupos = {}
        for item in referencias_ordenadas().filter(fecha__range=(inicio, fin)):
            grupos.setdefault(item.fecha, []).append(item)

        salida = Path(options['salida'] or f'comparacion_referencias_{anio}.csv')
        campos = [
            'fecha', 'comparacion', 'fuente', 'validada',
            'primera_lectura_ref', 'salmo_ref', 'segunda_lectura_ref',
            'aclamacion_ref', 'evangelio_ref', 'url_fuente',
        ]
        fechas_comparadas = con_diferencias = 0
        with salida.open('w', newline='', encoding='utf-8-sig') as archivo:
            writer = csv.DictWriter(archivo, fieldnames=campos)
            writer.writeheader()
            for fecha, registros in sorted(grupos.items()):
                if len(registros) < 2:
                    continue
                fechas_comparadas += 1
                firmas = {
                    tuple(getattr(item, campo) for campo in CAMPOS_CITA)
                    for item in registros
                }
                comparacion = 'coinciden' if len(firmas) == 1 else 'revisar diferencias'
                if len(firmas) > 1:
                    con_diferencias += 1
                for item in registros:
                    writer.writerow({
                        'fecha': fecha.isoformat(),
                        'comparacion': comparacion,
                        'fuente': item.get_fuente_display(),
                        'validada': item.validada,
                        **{campo: getattr(item, campo) for campo in CAMPOS_CITA},
                        'url_fuente': item.url_fuente,
                    })

        self.stdout.write(self.style.SUCCESS(
            f'{fechas_comparadas} fechas con varias fuentes; '
            f'{con_diferencias} con diferencias en las citas.'
        ))
        self.stdout.write(f'Archivo: {salida.resolve()}')
