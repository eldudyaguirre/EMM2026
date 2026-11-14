import time
from datetime import date, timedelta
from urllib.error import HTTPError, URLError

from django.core.management.base import BaseCommand, CommandError

from core.calendario_liturgico import datos_dia
from core.models import ReferenciaLecturaLiturgica
from core.referencias_liturgicas import obtener_referencias_misal


class Command(BaseCommand):
    help = 'Importa únicamente referencias bíblicas de Misal.mx; no copia textos bíblicos.'

    def add_arguments(self, parser):
        parser.add_argument('--desde', type=date.fromisoformat, required=True, help='YYYY-MM-DD')
        parser.add_argument('--hasta', type=date.fromisoformat, required=True, help='YYYY-MM-DD')
        parser.add_argument('--pausa', type=float, default=1.0)
        parser.add_argument('--sobrescribir', action='store_true')
        parser.add_argument(
            '--forzar-validada',
            action='store_true',
            help='Permite reemplazar registros validados manualmente (usar con cautela).',
        )

    def handle(self, *args, **options):
        desde, hasta = options['desde'], options['hasta']
        pausa = options['pausa']
        if hasta < desde:
            raise CommandError('--hasta debe ser igual o posterior a --desde.')
        if pausa < 0:
            raise CommandError('--pausa no puede ser negativa.')

        creadas = actualizadas = existentes = no_publicadas = incompletas = errores = 0
        fecha = desde

        while fecha <= hasta:
            try:
                url, refs = obtener_referencias_misal(fecha)
                if not refs.get('primera_lectura_ref') or not refs.get('salmo_ref') or not refs.get('evangelio_ref'):
                    incompletas += 1
                    self.stderr.write(self.style.WARNING(
                        f'{fecha}: referencias incompletas; no se guarda. '
                        f'Primera={bool(refs.get("primera_lectura_ref"))}, '
                        f'Salmo={bool(refs.get("salmo_ref"))}, '
                        f'Evangelio={bool(refs.get("evangelio_ref"))}'
                    ))
                else:
                    datos = datos_dia(fecha)
                    defaults = {
                        'anio_liturgico': datos['anio_liturgico'],
                        'tiempo_liturgico': datos['tiempo_liturgico'],
                        'semana_liturgica': datos['semana_liturgica'],
                        'dia_semana': datos['dia_semana'],
                        'ciclo_dominical': datos['ciclo_dominical'],
                        'ciclo_ferial': datos['ciclo_ferial'] or '',
                        'celebracion': datos['celebracion_calculada'],
                        **refs,
                        'fuente': 'misal_mx',
                        'url_fuente': url,
                        'validada': False,
                    }
                    registro = ReferenciaLecturaLiturgica.objects.filter(fecha=fecha, fuente='misal_mx').first()
                    if registro is None:
                        ReferenciaLecturaLiturgica.objects.create(fecha=fecha, **defaults)
                        creadas += 1
                        self.stdout.write(self.style.SUCCESS(f'{fecha}: referencias guardadas (pendientes de validar)'))
                    elif options['sobrescribir'] and (not registro.validada or options['forzar_validada']):
                        for campo, valor in defaults.items():
                            setattr(registro, campo, valor)
                        registro.save()
                        actualizadas += 1
                        self.stdout.write(self.style.SUCCESS(f'{fecha}: referencias actualizadas'))
                    else:
                        existentes += 1
                        self.stdout.write(f'{fecha}: ya existe; se conserva el registro actual')

            except HTTPError as exc:
                if exc.code == 404:
                    no_publicadas += 1
                    self.stderr.write(self.style.WARNING(
                        f'{fecha}: Misal.mx respondió 404; se considera no publicada/no disponible, no una fecha sin lecturas.'
                    ))
                else:
                    errores += 1
                    self.stderr.write(self.style.ERROR(f'{fecha}: HTTP {exc.code}'))
            except (URLError, TimeoutError, ValueError) as exc:
                errores += 1
                self.stderr.write(self.style.ERROR(f'{fecha}: {exc}'))
            except Exception as exc:
                errores += 1
                self.stderr.write(self.style.ERROR(f'{fecha}: error inesperado: {exc}'))

            fecha += timedelta(days=1)
            if fecha <= hasta and pausa:
                time.sleep(pausa)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            'Resumen: '
            f'{creadas} nuevas, {actualizadas} actualizadas, {existentes} conservadas, '
            f'{no_publicadas} no publicadas/404, {incompletas} incompletas, {errores} errores.'
        ))
        self.stdout.write(self.style.WARNING(
            'Las referencias importadas quedan con validada=False. '
            'No se descargaron ni almacenaron textos bíblicos.'
        ))
