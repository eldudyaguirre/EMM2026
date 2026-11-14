import csv
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.calendario_liturgico import generar_calendario_anual
from core.models import ReferenciaLecturaLiturgica


class Command(BaseCommand):
    help = 'Audita la cobertura de referencias bíblicas de un año, sin modificar la base de datos.'

    def add_arguments(self, parser):
        parser.add_argument('--anio', type=int, required=True)
        parser.add_argument('--salida', default='')

    def handle(self, *args, **options):
        anio = options['anio']
        if not 1900 <= anio <= 2200:
            raise CommandError('--anio debe estar entre 1900 y 2200.')

        calendario = generar_calendario_anual(anio)
        inicio, fin = date(anio, 1, 1), date(anio, 12, 31)
        referencias = {
            item.fecha: item
            for item in ReferenciaLecturaLiturgica.objects.filter(fecha__range=(inicio, fin))
        }

        salida = Path(options['salida'] or f'referencias_liturgicas_{anio}.csv')
        campos = [
            'fecha', 'anio_liturgico', 'tiempo_liturgico', 'semana_liturgica',
            'ciclo_dominical', 'ciclo_ferial', 'celebracion', 'primera_lectura_ref',
            'salmo_ref', 'segunda_lectura_ref', 'aclamacion_ref', 'evangelio_ref',
            'fuente', 'validada', 'estado',
        ]
        presentes = validadas = incompletas = 0
        with salida.open('w', newline='', encoding='utf-8-sig') as archivo:
            writer = csv.DictWriter(archivo, fieldnames=campos)
            writer.writeheader()
            for dia in calendario:
                ref = referencias.get(dia['fecha'])
                if ref:
                    presentes += 1
                    completas = bool(ref.primera_lectura_ref and ref.salmo_ref and ref.evangelio_ref)
                    if not completas:
                        incompletas += 1
                    if ref.validada:
                        validadas += 1
                    estado = 'validada' if ref.validada else ('pendiente' if completas else 'incompleta')
                    datos = {
                        'fecha': dia['fecha'].isoformat(),
                        'anio_liturgico': ref.anio_liturgico,
                        'tiempo_liturgico': ref.tiempo_liturgico,
                        'semana_liturgica': ref.semana_liturgica or '',
                        'ciclo_dominical': ref.ciclo_dominical,
                        'ciclo_ferial': ref.ciclo_ferial,
                        'celebracion': ref.celebracion,
                        'primera_lectura_ref': ref.primera_lectura_ref,
                        'salmo_ref': ref.salmo_ref,
                        'segunda_lectura_ref': ref.segunda_lectura_ref,
                        'aclamacion_ref': ref.aclamacion_ref,
                        'evangelio_ref': ref.evangelio_ref,
                        'fuente': ref.get_fuente_display(),
                        'validada': ref.validada,
                        'estado': estado,
                    }
                else:
                    datos = {
                        'fecha': dia['fecha'].isoformat(),
                        'anio_liturgico': dia['anio_liturgico'],
                        'tiempo_liturgico': dia['tiempo_liturgico'],
                        'semana_liturgica': dia['semana_liturgica'] or '',
                        'ciclo_dominical': dia['ciclo_dominical'],
                        'ciclo_ferial': dia['ciclo_ferial'] or '',
                        'celebracion': dia['celebracion_calculada'],
                        'primera_lectura_ref': '',
                        'salmo_ref': '',
                        'segunda_lectura_ref': '',
                        'aclamacion_ref': '',
                        'evangelio_ref': '',
                        'fuente': '',
                        'validada': False,
                        'estado': 'sin referencia',
                    }
                writer.writerow(datos)

        faltantes = len(calendario) - presentes
        self.stdout.write(self.style.SUCCESS(
            f'Auditoría {anio}: {presentes}/{len(calendario)} fechas con referencia; '
            f'{validadas} validadas; {incompletas} incompletas; {faltantes} sin referencia.'
        ))
        self.stdout.write(f'Archivo: {salida.resolve()}')
