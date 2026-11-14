import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.calendario_liturgico import generar_calendario_anual


class Command(BaseCommand):
    help = 'Genera un CSV de auditoría litúrgica sin consultar ni modificar la base de datos.'

    def add_arguments(self, parser):
        parser.add_argument('--anio', type=int, required=True, help='Año civil que se desea auditar.')
        parser.add_argument('--salida', default='', help='Ruta CSV. Por defecto calendario_liturgico_AAAA.csv.')

    def handle(self, *args, **options):
        anio = options['anio']
        if not 1900 <= anio <= 2200:
            raise CommandError('--anio debe estar entre 1900 y 2200.')

        salida = Path(options['salida'] or f'calendario_liturgico_{anio}.csv')
        filas = generar_calendario_anual(anio)
        campos = [
            'fecha', 'dia_semana', 'anio_liturgico', 'tiempo_liturgico',
            'semana_liturgica', 'ciclo_dominical', 'ciclo_ferial',
            'celebracion_calculada', 'es_domingo',
        ]

        with salida.open('w', newline='', encoding='utf-8-sig') as archivo:
            writer = csv.DictWriter(archivo, fieldnames=campos)
            writer.writeheader()
            for fila in filas:
                registro = dict(fila)
                registro['fecha'] = registro['fecha'].isoformat()
                registro['semana_liturgica'] = registro['semana_liturgica'] or ''
                writer.writerow(registro)

        self.stdout.write(self.style.SUCCESS(
            f'Calendario {anio} generado: {len(filas)} días. Archivo: {salida.resolve()}'
        ))
        self.stdout.write(self.style.WARNING(
            'Auditoría estructural: no asigna textos ni referencias bíblicas y no modifica la base de datos.'
        ))
