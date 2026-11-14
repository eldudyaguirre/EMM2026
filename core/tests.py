from django.test import TestCase

# Create your tests here.


from datetime import date

from django.test import SimpleTestCase

from core.calendario_liturgico import (
    bautismo_del_senor,
    ciclo_dominical,
    datos_dia,
    domingo_pascua,
    fechas_moviles,
    generar_calendario_anual,
    primer_domingo_adviento,
)


class CalendarioLiturgicoTests(SimpleTestCase):
    def test_fechas_principales_2026_ecuador(self):
        fechas = fechas_moviles(2026)
        self.assertEqual(bautismo_del_senor(2026), date(2026, 1, 11))
        self.assertEqual(fechas['miercoles_ceniza'], date(2026, 2, 18))
        self.assertEqual(fechas['domingo_ramos'], date(2026, 3, 29))
        self.assertEqual(fechas['pascua'], date(2026, 4, 5))
        self.assertEqual(fechas['ascension_ecuador'], date(2026, 5, 17))
        self.assertEqual(fechas['pentecostes'], date(2026, 5, 24))
        self.assertEqual(fechas['corpus_christi_ecuador'], date(2026, 6, 7))
        self.assertEqual(primer_domingo_adviento(2026), date(2026, 11, 29))

    def test_ciclo_dominical_cambia_en_adviento(self):
        self.assertEqual(ciclo_dominical(date(2026, 11, 22)), 'A')
        self.assertEqual(ciclo_dominical(date(2026, 11, 29)), 'B')
        self.assertEqual(ciclo_dominical(date(2027, 1, 3)), 'B')

    def test_tiempos_y_semanas_ordinarias_2026(self):
        self.assertEqual(datos_dia(date(2026, 1, 11))['tiempo_liturgico'], 'Tiempo de Navidad')
        self.assertEqual(datos_dia(date(2026, 1, 12))['semana_liturgica'], 1)
        self.assertEqual(datos_dia(date(2026, 2, 16))['semana_liturgica'], 6)
        self.assertEqual(datos_dia(date(2026, 2, 18))['tiempo_liturgico'], 'Cuaresma')
        self.assertEqual(datos_dia(date(2026, 3, 29))['tiempo_liturgico'], 'Semana Santa')
        self.assertEqual(datos_dia(date(2026, 4, 2))['tiempo_liturgico'], 'Triduo Pascual')
        self.assertEqual(datos_dia(date(2026, 4, 5))['tiempo_liturgico'], 'Tiempo Pascual')
        self.assertEqual(datos_dia(date(2026, 5, 25))['semana_liturgica'], 8)
        self.assertEqual(datos_dia(date(2026, 5, 31))['semana_liturgica'], 9)
        self.assertEqual(datos_dia(date(2026, 11, 22))['semana_liturgica'], 34)
        self.assertEqual(datos_dia(date(2026, 11, 29))['tiempo_liturgico'], 'Adviento')

    def test_ciclo_ferial_solo_se_asigna_en_tiempo_ordinario(self):
        self.assertEqual(datos_dia(date(2026, 1, 12))['ciclo_ferial'], 'II')
        self.assertEqual(datos_dia(date(2026, 5, 25))['ciclo_ferial'], 'II')
        self.assertIsNone(datos_dia(date(2026, 2, 19))['ciclo_ferial'])
        self.assertIsNone(datos_dia(date(2026, 4, 6))['ciclo_ferial'])

    def test_genera_todos_los_dias_del_ano(self):
        filas = generar_calendario_anual(2026)
        self.assertEqual(len(filas), 365)
        self.assertEqual(filas[0]['fecha'], date(2026, 1, 1))
        self.assertEqual(filas[-1]['fecha'], date(2026, 12, 31))

    def test_computo_pascua(self):
        self.assertEqual(domingo_pascua(2025), date(2025, 4, 20))
        self.assertEqual(domingo_pascua(2026), date(2026, 4, 5))
        self.assertEqual(domingo_pascua(2027), date(2027, 3, 28))
