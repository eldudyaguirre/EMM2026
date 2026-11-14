import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.calendario_liturgico import datos_dia
from core.models import ReferenciaLecturaLiturgica


class Command(BaseCommand):
    help = 'Carga referencias extraídas de los PDF de Domingo Día del Señor adjuntados para revisión.'

    def add_arguments(self, parser):
        parser.add_argument('--sobrescribir', action='store_true')

    def handle(self, *args, **options):
        archivo = Path(__file__).resolve().parents[2] / 'data' / 'referencias_cuenca_muestra_2023_2025.csv'
        if not archivo.exists():
            raise CommandError(f'No existe el archivo de referencias: {archivo}')

        creadas = actualizadas = conservadas = 0
        with archivo.open(encoding='utf-8-sig', newline='') as entrada:
            for fila in csv.DictReader(entrada):
                from datetime import date
                fecha = date.fromisoformat(fila['fecha'])
                datos = datos_dia(fecha)
                defaults = {
                    'anio_liturgico': datos['anio_liturgico'],
                    'tiempo_liturgico': datos['tiempo_liturgico'],
                    'semana_liturgica': datos['semana_liturgica'],
                    'dia_semana': datos['dia_semana'],
                    'ciclo_dominical': datos['ciclo_dominical'],
                    'ciclo_ferial': datos['ciclo_ferial'] or '',
                    'celebracion': fila.get('celebracion') or datos['celebracion_calculada'],
                    'primera_lectura_ref': fila['primera_lectura_ref'],
                    'salmo_ref': fila['salmo_ref'],
                    'segunda_lectura_ref': fila['segunda_lectura_ref'],
                    'aclamacion_ref': fila['aclamacion_ref'],
                    'evangelio_ref': fila['evangelio_ref'],
                    'fuente': 'arquidiocesis_cuenca',
                    'url_fuente': '',
                    'validada': True,
                    'observaciones': f"Referencia transcrita de {fila['documento_origen']}; conservar el PDF como comprobante.",
                }
                existente = ReferenciaLecturaLiturgica.objects.filter(fecha=fecha).first()
                if existente is None:
                    ReferenciaLecturaLiturgica.objects.create(fecha=fecha, **defaults)
                    creadas += 1
                elif options['sobrescribir']:
                    for campo, valor in defaults.items():
                        setattr(existente, campo, valor)
                    existente.save()
                    actualizadas += 1
                else:
                    conservadas += 1

        self.stdout.write(self.style.SUCCESS(
            f'Muestra cargada: {creadas} nuevas, {actualizadas} actualizadas, {conservadas} conservadas.'
        ))
        self.stdout.write(
            'Incluye 24 fechas: 11–18 jun 2023, 10–17 nov 2024 y 9–16 nov 2025.'
        )
