import csv
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.calendario_liturgico import generar_calendario_anual
from core.liturgia import referencias_ordenadas


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
        referencias_por_fecha = {}
        for item in referencias_ordenadas().filter(fecha__range=(inicio, fin)):
            referencias_por_fecha.setdefault(item.fecha, []).append(item)
        referencias = {
            fecha: items[0] for fecha, items in referencias_por_fecha.items()
        }

        salida = Path(options['salida'] or f'referencias_liturgicas_{anio}.csv')
        campos = [
            'fecha', 'anio_liturgico', 'tiempo_liturgico', 'semana_liturgica',
            'ciclo_dominical', 'ciclo_ferial', 'celebracion', 'primera_lectura_ref',
            'salmo_ref', 'segunda_lectura_ref', 'aclamacion_ref', 'evangelio_ref',
            'fuente', 'fuentes_disponibles', 'comparacion_fuentes', 'validada', 'estado',
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
                        'fuentes_disponibles': ' | '.join(item.get_fuente_display() for item in referencias_por_fecha[dia['fecha']]),
                        'comparacion_fuentes': (
                            'diferencias' if len({
                                (item.primera_lectura_ref, item.salmo_ref, item.segunda_lectura_ref, item.aclamacion_ref, item.evangelio_ref)
                                for item in referencias_por_fecha[dia['fecha']]
                            }) > 1 else ('coinciden' if len(referencias_por_fecha[dia['fecha']]) > 1 else 'una fuente')
                        ),
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
                        'fuentes_disponibles': '',
                        'comparacion_fuentes': 'sin comparar',
                        'validada': False,
                        'estado': 'sin referencia',
                    }
                writer.writerow(datos)

        faltantes = len(calendario) - presentes
        fechas_comparadas = sum(1 for items in referencias_por_fecha.values() if len(items) > 1)
        fechas_con_diferencias = sum(
            1 for items in referencias_por_fecha.values()
            if len(items) > 1 and len({
                (item.primera_lectura_ref, item.salmo_ref, item.segunda_lectura_ref, item.aclamacion_ref, item.evangelio_ref)
                for item in items
            }) > 1
        )
        self.stdout.write(self.style.SUCCESS(
            f'Auditoría {anio}: {presentes}/{len(calendario)} fechas con referencia; '
            f'{validadas} validadas; {incompletas} incompletas; {faltantes} sin referencia.'
        ))
        self.stdout.write(
            f'Comparación de fuentes: {fechas_comparadas} fechas con varias fuentes; '
            f'{fechas_con_diferencias} con referencias diferentes.'
        )
        self.stdout.write(f'Archivo: {salida.resolve()}')
