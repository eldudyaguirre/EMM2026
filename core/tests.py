from datetime import date

from django.test import SimpleTestCase

from core.management.commands.extraer_documentos_liturgicos import (
    _fecha_desde_texto_pdf,
    _texto_pagina_por_columnas,
)
from core.management.commands.generar_catalogo_liturgico import (
    _extraer_secciones,
)
from core.management.commands.auditar_calidad_catalogo_liturgico import (
    PATRONES_MEZCLA,
    UMBRAL_CRITICO,
    referencia_biblica,
)


class FechaDocumentalLiturgicaTests(SimpleTestCase):
    def test_fecha_del_encabezado_se_reconoce(self):
        texto = (
            "DOMINGO DÍA DEL SEÑOR\n"
            "7 DE ENERO DE 2018\n"
            "EL BAUTISMO DEL SEÑOR\n"
            "Año XII - Ciclo B"
        )
        self.assertEqual(_fecha_desde_texto_pdf(texto), date(2018, 1, 7))

    def test_fecha_separada_del_titulo_se_reconoce(self):
        texto = (
            "II DOMINGO DE PASCUA\n"
            "11 DE ABRIL DEL2021\n"
            "Ciclo B"
        )
        self.assertEqual(_fecha_desde_texto_pdf(texto), date(2021, 4, 11))

    def test_fecha_citada_en_mensaje_papal_no_se_toma_como_fecha_documental(self):
        texto = (
            "DOMINGO XXXIV DEL TIEMPO ORDINARIO CICLO B\n"
            "SOLEMNIDAD DE CRISTO REY DEL UNIVERSO\n"
            "(S.S. Papa Francisco, 24-11-2013).\n"
        )
        self.assertIsNone(_fecha_desde_texto_pdf(texto))

    def test_fecha_de_colecta_editorial_no_se_toma_como_fecha_documental(self):
        texto = (
            "DOMINGO DÍA DEL SEÑOR\n"
            "MENSAJE DEL PASTOR\n"
            "23 de noviembre 2014: Colecta por el Día de la Iglesia Católica"
        )
        self.assertIsNone(_fecha_desde_texto_pdf(texto))


class OrdenColumnasPDFTests(SimpleTestCase):
    class PaginaFalsa:
        def __init__(self, bloques):
            self.bloques = bloques
            self.rect = type("Rect", (), {"width": 400})()

        def get_text(self, modo, sort=False):
            if modo == "blocks":
                return self.bloques
            if modo == "text":
                return "\n".join(bloque[4] for bloque in self.bloques)
            raise AssertionError(f"Modo de extracción inesperado: {modo}")

    def test_lee_columna_izquierda_antes_de_derecha_y_respeta_bandas(self):
        largo_izq_1 = "PRIMERA LECTURA " + ("texto izquierdo " * 5)
        largo_der_1 = "SALMO RESPONSORIAL " + ("texto derecho " * 5)
        largo_izq_2 = "SEGUNDA LECTURA " + ("texto izquierdo final " * 4)
        largo_der_2 = "ACLAMACIÓN " + ("texto derecho final " * 4)
        bloques = [
            (25, 10, 185, 38, largo_izq_1, 0, 0),
            (215, 10, 375, 38, largo_der_1, 1, 0),
            (20, 80, 380, 105, "LITURGIA DE LA PALABRA", 2, 0),
            (25, 120, 185, 150, largo_izq_2, 3, 0),
            (215, 120, 375, 150, largo_der_2, 4, 0),
        ]
        pagina = self.PaginaFalsa(bloques)
        texto = _texto_pagina_por_columnas(pagina)

        self.assertLess(texto.index(largo_izq_1), texto.index(largo_der_1))
        self.assertLess(texto.index(largo_der_1), texto.index("LITURGIA DE LA PALABRA"))
        self.assertLess(texto.index("LITURGIA DE LA PALABRA"), texto.index(largo_izq_2))
        self.assertLess(texto.index(largo_izq_2), texto.index(largo_der_2))


class SegmentacionLecturasTests(SimpleTestCase):
    def test_separa_cinco_secciones_y_recorta_oracion_universal(self):
        texto = """
6. PRIMERA LECTURA
Lectura del libro del profeta Isaías 45, 1-6
Así habla el Señor a su pueblo. Esta lectura contiene el texto bíblico de prueba
que debe conservarse íntegro hasta el marcador final. Palabra de Dios.
7. Salmo Responsorial (Salmo 95)
Salmista: Cantemos la grandeza del Señor.
Asamblea: Cantemos la grandeza del Señor.
Cantemos al Señor un canto nuevo. R.
8. SEGUNDA LECTURA
Lectura de la primera carta del apóstol san Pablo a los tesalonicenses 1, 1-5
Hermanos: damos gracias a Dios por ustedes y por su fe. Palabra de Dios.
9, | Aclamación
Flp 2,15.16
Asamblea: Aleluya, aleluya.
Cantor: Iluminen al mundo con la luz del Evangelio.
Asamblea: Aleluya, aleluya.
10. Evangelio
Lectura del santo Evangelio según san Mateo 22, 15-21
En aquel tiempo, Jesús enseñó a sus discípulos una parábola y les habló del Reino.
Palabra del Señor.
11. Profesión de Fe
12. Oración Universal
1. Por la Iglesia y por el Papa. Oremos.
"""
        secciones = _extraer_secciones(texto)

        self.assertIn("Isaías 45, 1-6", secciones["primera_lectura"])
        self.assertIn("Salmo 95", secciones["salmo_responsorial"])
        self.assertIn("Cantemos al Señor", secciones["salmo_responsorial"])
        self.assertNotIn("Lectura de la primera carta", secciones["salmo_responsorial"])
        self.assertIn("tesalonicenses 1, 1-5", secciones["segunda_lectura"])
        self.assertIn("Flp 2,15.16", secciones["aclamacion"])
        self.assertIn("Iluminen al mundo", secciones["aclamacion"])
        self.assertNotIn("Oración Universal", secciones["aclamacion"])
        self.assertIn("san Mateo 22, 15-21", secciones["evangelio"])
        self.assertIn("Jesús enseñó", secciones["evangelio"])
        self.assertNotIn("Profesión de Fe", secciones["evangelio"])


class AuditoriaCalidadLiturgicaTests(SimpleTestCase):
    def test_reconoce_referencias_biblicas_abreviadas(self):
        self.assertEqual(referencia_biblica("Jn 1,14.12"), "Jn 1,14.12")
        self.assertEqual(referencia_biblica("Flp 2,15.16"), "Flp 2,15.16")
        self.assertEqual(referencia_biblica("Mt 22, 34-40"), "Mt 22, 34-40")

    def test_detecta_oracion_universal_dentro_de_aclamacion(self):
        texto = (
            "Asamblea: Aleluya. Cantor: Dichosos los que escuchan. "
            "Asamblea: Aleluya. Oración Universal: Por la Iglesia..."
        )
        self.assertIsNotNone(PATRONES_MEZCLA["aclamacion"].search(texto))

    def test_un_evangelio_de_74_caracteres_es_criticamente_corto(self):
        self.assertEqual(UMBRAL_CRITICO["evangelio"], 100)
        self.assertLess(74, UMBRAL_CRITICO["evangelio"])
