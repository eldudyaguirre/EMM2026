from datetime import date

from django.test import SimpleTestCase

from core.calendario_liturgico import (
    bautismo_del_senor,
    ciclo_dominical,
    ciclo_ferial,
    datos_dia,
    domingo_pascua,
    epifania_del_senor,
    fechas_moviles,
    generar_calendario_anual,
    primer_domingo_adviento,
)


class CalendarioLiturgicoTests(SimpleTestCase):
    def test_fechas_principales_2026_ecuador(self):
        fechas = fechas_moviles(2026)
        self.assertEqual(epifania_del_senor(2026), date(2026, 1, 4))
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

    def test_periodo_del_anio_liturgico_es_explicito(self):
        self.assertEqual(datos_dia(date(2026, 1, 1))['anio_liturgico'], '2025-2026')
        self.assertEqual(datos_dia(date(2026, 11, 28))['anio_liturgico'], '2025-2026')
        self.assertEqual(datos_dia(date(2026, 11, 29))['anio_liturgico'], '2026-2027')

    def test_semanas_del_tiempo_ordinario_2026(self):
        self.assertEqual(datos_dia(date(2026, 1, 11))['tiempo_liturgico'], 'Tiempo de Navidad')
        self.assertEqual(datos_dia(date(2026, 1, 12))['semana_liturgica'], 1)
        self.assertEqual(datos_dia(date(2026, 2, 16))['semana_liturgica'], 6)
        self.assertEqual(datos_dia(date(2026, 5, 25))['semana_liturgica'], 8)
        self.assertEqual(datos_dia(date(2026, 5, 31))['semana_liturgica'], 9)
        self.assertEqual(datos_dia(date(2026, 6, 1))['semana_liturgica'], 9)
        self.assertEqual(datos_dia(date(2026, 6, 7))['semana_liturgica'], 10)
        self.assertEqual(datos_dia(date(2026, 6, 8))['semana_liturgica'], 10)
        self.assertEqual(datos_dia(date(2026, 11, 22))['semana_liturgica'], 34)
        self.assertEqual(datos_dia(date(2026, 11, 29))['tiempo_liturgico'], 'Adviento')

    def test_no_existe_semana_cero_despues_de_ceniza(self):
        for fecha in (date(2026, 2, 18), date(2026, 2, 19), date(2026, 2, 20), date(2026, 2, 21)):
            datos = datos_dia(fecha)
            self.assertEqual(datos['tiempo_liturgico'], 'Cuaresma')
            self.assertIsNone(datos['semana_liturgica'])
        self.assertEqual(datos_dia(date(2026, 2, 22))['semana_liturgica'], 1)

    def test_tiempos_especiales_y_triduo(self):
        self.assertEqual(datos_dia(date(2026, 3, 29))['tiempo_liturgico'], 'Semana Santa')
        self.assertEqual(datos_dia(date(2026, 3, 30))['celebracion_calculada'], 'Lunes Santo')
        self.assertEqual(datos_dia(date(2026, 4, 1))['celebracion_calculada'], 'Miércoles Santo')
        self.assertEqual(datos_dia(date(2026, 4, 2))['tiempo_liturgico'], 'Triduo Pascual')
        self.assertEqual(datos_dia(date(2026, 4, 5))['tiempo_liturgico'], 'Tiempo Pascual')
        self.assertIsNone(datos_dia(date(2026, 5, 24))['semana_liturgica'])
        self.assertEqual(datos_dia(date(2026, 5, 17))['celebracion_calculada'], 'Ascensión del Señor (celebración en domingo, Ecuador)')
        self.assertEqual(datos_dia(date(2026, 5, 24))['celebracion_calculada'], 'Domingo de Pentecostés')

    def test_celebraciones_relevantes_ecuador_2026(self):
        self.assertIn('Mariana de Jesús', datos_dia(date(2026, 5, 26))['celebracion_calculada'])
        self.assertIn('Sumo y Eterno Sacerdote', datos_dia(date(2026, 5, 28))['celebracion_calculada'])
        self.assertIn('Santísima Trinidad', datos_dia(date(2026, 5, 31))['celebracion_calculada'])
        self.assertIn('Cuerpo y Sangre', datos_dia(date(2026, 6, 7))['celebracion_calculada'])
        self.assertIn('Rey del Universo', datos_dia(date(2026, 11, 22))['celebracion_calculada'])
        self.assertIn('Inmaculada', datos_dia(date(2026, 12, 8))['celebracion_calculada'])
        self.assertIn('Sagrada Familia', datos_dia(date(2026, 12, 27))['celebracion_calculada'])

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

    def test_ciclo_ferial_cambia_en_primer_domingo_de_adviento(self):
        # El año litúrgico 2025-2026 usa ciclo II hasta el sábado 28/11/2026.
        self.assertEqual(datos_dia(date(2026, 11, 28))['ciclo_ferial'], 'II')
        self.assertEqual(ciclo_ferial(date(2026, 12, 1)), 'I')
        # El año litúrgico 2026-2027 usa ciclo I; su Adviento comienza el 29/11/2026.
        self.assertEqual(datos_dia(date(2026, 11, 30))['ciclo_ferial'], None)
        self.assertEqual(datos_dia(date(2026, 12, 1))['ciclo_ferial'], None)
        # En el siguiente Tiempo Ordinario, ciclo ferial I.
        self.assertEqual(datos_dia(date(2027, 1, 11))['ciclo_ferial'], 'I')


from core.referencias_liturgicas import analizar_html_misal


class ReferenciasLiturgicasParserTests(SimpleTestCase):
    def test_extrae_referencias_de_misal_mx_sin_guardar_el_texto(self):
        html = """
        <h2>PRIMERA LECTURA</h2>
        <p>El que permanece fiel a la doctrina de Cristo.</p>
        <p>De la segunda carta del apóstol san Juan: 4-9</p>
        <p>Hermanos: Me ha dado mucha alegría enterarme...</p>
        <h2>SALMO</h2>
        <p>Del salmo 118</p>
        <p>R/. Dichoso el que cumple la ley del Señor.</p>
        <h2>ACLAMACIÓN</h2>
        <p>Aleluya, Aleluya. Estén atentos y levanten la cabeza.</p>
        <h2>EVANGELIO</h2>
        <p>Lo mismo sucederá el día en que el Hijo del hombre se manifieste.</p>
        <p>Del santo Evangelio según san Lucas: 17, 26-37</p>
        <p>En aquellos días, Jesús dijo a sus discípulos...</p>
        """
        refs = analizar_html_misal(html)
        self.assertEqual(refs['primera_lectura_ref'], '2 Juan 4-9')
        self.assertEqual(refs['salmo_ref'], 'Salmo 118')
        self.assertEqual(refs['evangelio_ref'], 'Lucas 17, 26-37')
        self.assertEqual(refs['segunda_lectura_ref'], '')
        self.assertEqual(refs['aclamacion_ref'], '')
        self.assertNotIn('Hermanos:', str(refs))

    def test_extrae_citas_con_capitulo_y_versiculos(self):
        html = """
        <h2>PRIMERA LECTURA</h2>
        <p>Del libro del profeta Isaías: 40, 1-5</p>
        <h2>SALMO</h2><p>Del salmo 85</p>
        <h2>SEGUNDA LECTURA</h2>
        <p>De la primera carta del apóstol san Pablo a los Tesalonicenses: 5, 1-6</p>
        <h2>ACLAMACIÓN</h2><p>Aleluya.</p>
        <h2>EVANGELIO</h2>
        <p>Del santo Evangelio según san Mateo: 3, 1-12</p>
        """
        refs = analizar_html_misal(html)
        self.assertEqual(refs['primera_lectura_ref'], 'Isaías 40, 1-5')
        self.assertEqual(refs['salmo_ref'], 'Salmo 85')
        self.assertEqual(refs['segunda_lectura_ref'], '1 Tesalonicenses 5, 1-6')
        self.assertEqual(refs['evangelio_ref'], 'Mateo 3, 1-12')


from core.liturgia import ciclo_lectura


class CicloLecturaResolverTests(SimpleTestCase):
    def test_devuelve_ciclo_dominical_y_ferial_o_propio(self):
        self.assertEqual(ciclo_lectura(date(2026, 11, 22)), 'A')
        self.assertEqual(ciclo_lectura(date(2026, 11, 13)), 'II')
        self.assertEqual(ciclo_lectura(date(2026, 12, 1)), 'F')
        self.assertEqual(ciclo_lectura(date(2026, 2, 19)), 'F')


    def test_acepta_cita_separada_en_nodos_html(self):
        html = """
        <h2>PRIMERA LECTURA</h2>
        <p>De la segunda carta del apóstol san Juan:</p><span>4-9</span>
        <h2>SALMO</h2><p>Del salmo</p><span>118</span>
        <h2>EVANGELIO</h2>
        <p>Del santo Evangelio según san Lucas:</p><span>17, 26-37</span>
        """
        refs = analizar_html_misal(html)
        self.assertEqual(refs['primera_lectura_ref'], '2 Juan 4-9')
        self.assertEqual(refs['salmo_ref'], 'Salmo 118')
        self.assertEqual(refs['evangelio_ref'], 'Lucas 17, 26-37')
