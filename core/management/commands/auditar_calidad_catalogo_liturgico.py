import csv
import re
from collections import Counter
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


SECCIONES = (
    ("primera_lectura", "PRIMERA LECTURA", 80),
    ("salmo_responsorial", "SALMO RESPONSORIAL", 60),
    ("segunda_lectura", "SEGUNDA LECTURA", 80),
    ("aclamacion", "ACLAMACIÓN", 20),
    ("evangelio", "EVANGELIO", 100),
)

LIBROS_BIBLICOS = (
    "Génesis", "Genesis", "Éxodo", "Exodo", "Levítico", "Levitico",
    "Números", "Numeros", "Deuteronomio", "Josué", "Josue", "Jueces",
    "Rut", "Samuel", "Reyes", "Crónicas", "Cronicas", "Esdras",
    "Nehemías", "Nehemias", "Tobías", "Tobias", "Judit", "Ester",
    "Job", "Salmo", "Salmos", "Proverbios", "Eclesiastés", "Eclesiastes",
    "Cantar", "Sabiduría", "Sabiduria", "Eclesiástico", "Eclesiastico",
    "Isaías", "Isaias", "Jeremías", "Jeremias", "Lamentaciones", "Baruc",
    "Ezequiel", "Daniel", "Oseas", "Joel", "Amós", "Amos", "Abdías",
    "Abdias", "Jonás", "Jonas", "Miqueas", "Nahúm", "Nahum", "Habacuc",
    "Sofonías", "Sofonias", "Ageo", "Hageo", "Zacarías", "Zacarias",
    "Malaquías", "Malaquias", "Mateo", "Marcos", "Lucas", "Juan",
    "Hechos", "Romanos", "Corintios", "Gálatas", "Galatas", "Efesios",
    "Filipenses", "Colosenses", "Tesalonicenses", "Timoteo", "Tito",
    "Filemón", "Filemon", "Hebreos", "Santiago", "Pedro", "Judas",
    "Apocalipsis",
)

ABREVIATURAS_BIBLICAS = (
    "Gn", "Gen", "Ex", "Lv", "Nm", "Dt", "Jos", "Jue", "Rt",
    "1 Sam", "2 Sam", "1 Re", "2 Re", "1 Cr", "2 Cr", "Esd", "Neh",
    "Tob", "Jdt", "Est", "Sal", "Prov", "Ecl", "Cant", "Sab", "Sir",
    "Is", "Jer", "Lam", "Bar", "Ez", "Dn", "Os", "Jl", "Am", "Abd",
    "Jon", "Miq", "Nah", "Hab", "Sof", "Ag", "Zac", "Mal",
    "Mt", "Mc", "Lc", "Jn", "Hch", "Rom", "1 Cor", "2 Cor",
    "Gal", "Ef", "Flp", "Col", "1 Tes", "2 Tes", "1 Tim", "2 Tim",
    "Tit", "Flm", "Heb", "Sant", "Stg", "1 Pe", "2 Pe",
    "1 Jn", "2 Jn", "3 Jn", "Jud", "Ap",
)

NOMBRES_REFERENCIA = LIBROS_BIBLICOS + ABREVIATURAS_BIBLICAS
PATRON_REFERENCIA = re.compile(
    r"(?<![A-ZÁÉÍÓÚÑ])(?:[1-3]\s*)?(?:"
    + "|".join(re.escape(nombre) for nombre in sorted(NOMBRES_REFERENCIA, key=len, reverse=True))
    + r")\s+\d{1,3}\b(?:\s*[,.:]\s*\d{1,3}(?:[-–]\d{1,3})?)?",
    re.IGNORECASE,
)

PATRONES_MEZCLA = {
    "primera_lectura": re.compile(
        r"\b(?:SALMISTA\s*:|SALMO\s+RESPONSORIAL|ACLAMACI[ÓO]N|"
        r"LECTURA\s+DEL\s+(?:SANTO\s+)?EVANGELIO|"
        r"ASAMBLEA\s*:\s*ALELUYA)\b",
        re.I,
    ),
    "salmo_responsorial": re.compile(
        r"\b(?:MONICI[ÓO]N\s+A\s+LAS\s+LECTURAS|RITOS\s+INICIALES|"
        r"ORACI[ÓO]N\s+COLECTA|LECTURA\s+(?:DEL|DE\s+LA)|"
        r"PALABRA\s+DE\s+DIOS|PALABRA\s+DEL\s+SE[ÑN]OR|"
        r"ACLAMACI[ÓO]N|ORACI[ÓO]N\s+UNIVERSAL)\b",
        re.I,
    ),
    "segunda_lectura": re.compile(
        r"\b(?:SALMISTA\s*:|SALMO\s+RESPONSORIAL|ACLAMACI[ÓO]N|"
        r"LECTURA\s+DEL\s+(?:SANTO\s+)?EVANGELIO|"
        r"ASAMBLEA\s*:\s*ALELUYA)\b",
        re.I,
    ),
    "aclamacion": re.compile(
        r"\b(?:ORACI[ÓO]N\s+UNIVERSAL|PROFESI[ÓO]N\s+DE\s+FE|"
        r"LECTURA\s+DEL\s+(?:SANTO\s+)?EVANGELIO|"
        r"PALABRA\s+DEL\s+SE[ÑN]OR|"
        r"\d{1,2}\s*[.)]\s*POR\s+(?:EL\s+PAPA|LA\s+IGLESIA|LOS\s+GOBERNANTES))\b",
        re.I,
    ),
    "evangelio": re.compile(
        r"\b(?:ORACI[ÓO]N\s+SOBRE\s+LAS\s+OFRENDAS|"
        r"ORACI[ÓO]N\s+UNIVERSAL|PROFESI[ÓO]N\s+DE\s+FE|"
        r"LITURGIA\s+EUCAR[ÍI]STICA|RITOS\s+INICIALES|"
        r"ORACI[ÓO]N\s+COLECTA|SALMISTA\s*:)\b",
        re.I,
    ),
}

UMBRAL_CRITICO = {
    "primera_lectura": 80,
    "salmo_responsorial": 25,
    "segunda_lectura": 80,
    "aclamacion": 35,
    "evangelio": 50,
}

CAMPOS_REPORTE = [
    "archivo_pdf",
    "fecha_publicacion",
    "fecha_documento",
    "titulo_publicacion",
    "titulo_celebracion",
    "ciclo",
    "categoria",
    "metodo_extraccion",
    "estado_extraccion",
    "paginas",
    "caracteres_extraidos",
    "primera_lectura_caracteres",
    "primera_lectura_referencia",
    "salmo_responsorial_caracteres",
    "salmo_responsorial_referencia",
    "segunda_lectura_caracteres",
    "segunda_lectura_referencia",
    "aclamacion_caracteres",
    "aclamacion_referencia",
    "evangelio_caracteres",
    "evangelio_referencia",
    "primera_lectura_estado",
    "salmo_responsorial_estado",
    "segunda_lectura_estado",
    "aclamacion_estado",
    "evangelio_estado",
    "secciones_faltantes",
    "secciones_sospechosas",
    "alertas",
    "prioridad_revision",
]


def leer_csv(ruta):
    if not ruta.is_file():
        raise CommandError(f"No existe el archivo requerido: {ruta}")
    with ruta.open("r", newline="", encoding="utf-8-sig") as archivo:
        lector = csv.DictReader(archivo)
        if not lector.fieldnames:
            raise CommandError(f"El CSV no tiene encabezados: {ruta}")
        return list(lector)


def fecha_iso(valor):
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


def referencia_biblica(texto):
    coincidencia = PATRON_REFERENCIA.search((texto or "")[:900])
    return coincidencia.group(0).strip() if coincidencia else ""


def nombre_archivo(valor):
    return Path((valor or "").replace("\\", "/")).name


def agregar_alerta(alertas, alerta):
    if alerta not in alertas:
        alertas.append(alerta)


class Command(BaseCommand):
    help = (
        "Audita la calidad del índice litúrgico y prepara material de revisión humana. "
        "Solo lee CSV/TXT y genera informes; no modifica PostgreSQL, calendario ni PDF."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--salida",
            default="documentos_liturgicos_arquidiocesis",
            help="Carpeta con el inventario, catálogo, índice y TXT.",
        )

    def handle(self, *args, **options):
        base = Path(options["salida"]).expanduser().resolve()
        ruta_inventario = base / "inventario_documentos.csv"
        ruta_catalogo = base / "catalogo_documental.csv"
        ruta_indice = base / "indice_liturgico_cronologico.csv"
        carpeta_txt = base / "texto_por_documento"

        inventario = leer_csv(ruta_inventario)
        catalogo = leer_csv(ruta_catalogo)
        indice = leer_csv(ruta_indice)
        if not carpeta_txt.is_dir():
            raise CommandError(f"No existe la carpeta de TXT: {carpeta_txt}")

        por_archivo = lambda filas: {
            nombre_archivo(fila.get("archivo_pdf")): fila
            for fila in filas
            if nombre_archivo(fila.get("archivo_pdf"))
        }
        inv_por_archivo = por_archivo(inventario)
        cat_por_archivo = por_archivo(catalogo)
        idx_por_archivo = por_archivo(indice)

        conteo_fechas = Counter(
            (fila.get("fecha_documento") or "").strip()
            for fila in indice
            if (fila.get("fecha_documento") or "").strip()
        )

        filas_reporte = []
        detalle_revision = []
        resumen_alertas = Counter()
        cantidad_ocr = 0
        cantidad_ocr_incompleta = 0
        cantidad_fecha_distinta = 0
        cantidad_fecha_nombre_distinta = 0
        cantidad_duplicadas = sum(1 for _, cantidad in conteo_fechas.items() if cantidad > 1)
        cantidad_con_titulo_vacio = 0
        cantidad_con_ciclo_vacio = 0
        cantidad_texto_sospechoso = 0
        total_faltantes = Counter()

        for catalogo_fila in catalogo:
            archivo = nombre_archivo(catalogo_fila.get("archivo_pdf"))
            inventario_fila = inv_por_archivo.get(archivo, {})
            indice_fila = idx_por_archivo.get(archivo, {})
            ruta_txt = carpeta_txt / (Path(archivo).stem + ".txt") if archivo else None
            texto_completo = ""
            if ruta_txt and ruta_txt.is_file():
                texto_completo = ruta_txt.read_text(encoding="utf-8", errors="replace")

            metodo = (
                catalogo_fila.get("metodo_extraccion")
                or inventario_fila.get("metodo_extraccion")
                or ""
            ).upper()
            es_ocr = "OCR_TESSERACT" in metodo
            if es_ocr:
                cantidad_ocr += 1

            fecha_publicacion = (catalogo_fila.get("fecha_publicacion") or "").strip()
            fecha_documento = (catalogo_fila.get("fecha_documento") or "").strip()
            fecha_pub = fecha_iso(fecha_publicacion)
            fecha_doc = fecha_iso(fecha_documento)
            titulo = (catalogo_fila.get("titulo_celebracion") or "").strip()
            ciclo = (catalogo_fila.get("ciclo") or "").strip()
            categoria = (catalogo_fila.get("categoria") or "").strip()
            alertas = []
            secciones_faltantes = []

            if not ruta_txt or not ruta_txt.is_file():
                agregar_alerta(alertas, "TXT_NO_ENCONTRADO")
            if not fecha_documento:
                agregar_alerta(alertas, "FECHA_DOCUMENTAL_VACIA")
            elif not fecha_doc:
                agregar_alerta(alertas, "FECHA_DOCUMENTAL_INVALIDA")
            if fecha_publicacion and not fecha_pub:
                agregar_alerta(alertas, "FECHA_PUBLICACION_INVALIDA")
            if fecha_doc and fecha_pub and fecha_doc != fecha_pub:
                cantidad_fecha_distinta += 1
                agregar_alerta(alertas, "FECHA_DOCUMENTO_DIFIERE_DE_PUBLICACION")

            coincidencia_nombre = re.match(r"^(\d{4}-\d{2}-\d{2})_", archivo)
            if coincidencia_nombre and fecha_doc:
                fecha_nombre = fecha_iso(coincidencia_nombre.group(1))
                if fecha_nombre and fecha_nombre != fecha_doc:
                    cantidad_fecha_nombre_distinta += 1
                    agregar_alerta(alertas, "FECHA_NOMBRE_DIFIERE_DE_DOCUMENTO")

            if fecha_documento and conteo_fechas[fecha_documento] > 1:
                agregar_alerta(alertas, "FECHA_DUPLICADA_EN_INDICE")
            es_registro_lectura = categoria == "LECTURA_LITURGICA" and bool(indice_fila)
            es_secuencia_pascual_2020 = (
                archivo == "2020-04-12_339.pdf"
                and fecha_documento == "2020-04-12"
            )

            if es_registro_lectura:
                if not titulo:
                    cantidad_con_titulo_vacio += 1
                    agregar_alerta(alertas, "TITULO_CELEBRACION_VACIO")
                if not ciclo:
                    cantidad_con_ciclo_vacio += 1
                    agregar_alerta(alertas, "CICLO_NO_IDENTIFICADO")

            if es_ocr:
                agregar_alerta(alertas, "OCR_REQUIERE_COTEJO_HUMANO")
            if categoria != "LECTURA_LITURGICA":
                agregar_alerta(alertas, "DOCUMENTO_FUERA_DEL_INDICE_DE_LECTURAS")
            if "\ufffd" in texto_completo:
                cantidad_texto_sospechoso += 1
                agregar_alerta(alertas, "CARACTER_REEMPLAZO_EN_TEXTO")

            referencias = {}
            longitudes = {}
            secciones = {}
            for campo, etiqueta, minimo in SECCIONES:
                contenido = (indice_fila.get(campo) or "").strip()
                secciones[campo] = contenido
                longitud = len(contenido)
                longitudes[campo] = longitud
                referencia = referencia_biblica(contenido)
                referencias[campo] = referencia

                if es_registro_lectura and not contenido:
                    if es_secuencia_pascual_2020 and campo == "aclamacion":
                        agregar_alerta(alertas, "ACLAMACION_NO_APLICA_SECUENCIA_PASCUAL")
                    else:
                        secciones_faltantes.append(campo)
                        total_faltantes[campo] += 1
                        agregar_alerta(alertas, f"FALTA_{campo.upper()}")
                elif es_registro_lectura and contenido and longitud < minimo:
                    agregar_alerta(alertas, f"TEXTO_CORTO_{campo.upper()}")
                if es_registro_lectura and contenido and not referencia:
                    agregar_alerta(alertas, f"REFERENCIA_NO_DETECTADA_{campo.upper()}")

            if es_ocr and secciones_faltantes:
                cantidad_ocr_incompleta += 1

            estado = (catalogo_fila.get("estado_extraccion") or "").upper()
            if estado in {"ERROR", "SIN_TEXTO"}:
                agregar_alerta(alertas, f"ESTADO_EXTRACCION_{estado}")

            observacion_fecha = (
                catalogo_fila.get("observacion_fecha")
                or inventario_fila.get("observacion_fecha")
                or ""
            ).strip()
            if observacion_fecha:
                agregar_alerta(alertas, "OBSERVACION_DE_FECHA_EXISTENTE")

            prioridad = "BAJA"
            if any(
                alerta.startswith("FALTA_")
                or alerta in {"TXT_NO_ENCONTRADO", "FECHA_DOCUMENTAL_INVALIDA", "CARACTER_REEMPLAZO_EN_TEXTO"}
                or alerta.startswith("ESTADO_EXTRACCION_")
                for alerta in alertas
            ):
                prioridad = "ALTA"
            elif es_ocr or any(
                alerta.startswith("TEXTO_CORTO_")
                or alerta.startswith("REFERENCIA_NO_DETECTADA_")
                or alerta.startswith("FECHA_")
                or alerta == "TITULO_CELEBRACION_VACIO"
                for alerta in alertas
            ):
                prioridad = "MEDIA"

            for alerta in alertas:
                resumen_alertas[alerta] += 1

            fila_salida = {
                "archivo_pdf": catalogo_fila.get("archivo_pdf", ""),
                "fecha_publicacion": fecha_publicacion,
                "fecha_documento": fecha_documento,
                "titulo_publicacion": catalogo_fila.get("titulo_publicacion", ""),
                "titulo_celebracion": titulo,
                "ciclo": ciclo,
                "categoria": categoria,
                "metodo_extraccion": metodo,
                "estado_extraccion": catalogo_fila.get("estado_extraccion", ""),
                "paginas": catalogo_fila.get("paginas", ""),
                "caracteres_extraidos": catalogo_fila.get("caracteres_extraidos", ""),
                "secciones_faltantes": ";".join(secciones_faltantes),
                "alertas": ";".join(alertas),
                "prioridad_revision": prioridad,
            }
            for campo, _etiqueta, _minimo in SECCIONES:
                fila_salida[f"{campo}_caracteres"] = longitudes[campo]
                fila_salida[f"{campo}_referencia"] = referencias[campo]
            filas_reporte.append(fila_salida)

            if es_ocr:
                detalle_revision.extend([
                    "",
                    "=" * 88,
                    f"DOCUMENTO: {archivo}",
                    f"Fecha publicación: {fecha_publicacion or 'SIN FECHA'}",
                    f"Fecha documental: {fecha_documento or 'SIN FECHA'}",
                    f"Celebración: {titulo or 'NO IDENTIFICADA'}",
                    f"Ciclo: {ciclo or 'NO IDENTIFICADO'}",
                    f"Método: {metodo}",
                    f"Observación de fecha: {observacion_fecha or 'Ninguna'}",
                    "Alertas: " + ("; ".join(alertas) if alertas else "Ninguna"),
                ])
                for campo, etiqueta, _minimo in SECCIONES:
                    contenido = secciones[campo]
                    nota_seccion = (
                        "NO APLICA: el documento contiene la Secuencia de Pascua; "
                        "no se considera aclamación."
                        if es_secuencia_pascual_2020 and campo == "aclamacion" and not contenido
                        else "NO DETECTADA" if not contenido else "CONTENIDO DETECTADO"
                    )
                    detalle_revision.extend([
                        "",
                        f"--- {etiqueta} ({len(contenido)} caracteres) ---",
                        f"Estado: {nota_seccion}",
                        f"Referencia detectada: {referencias[campo] or 'NO DETECTADA'}",
                        contenido if contenido else "[SIN CONTENIDO EN EL CAMPO DEL ÍNDICE]",
                    ])

        ruta_csv = base / "auditoria_calidad_liturgica.csv"
        with ruta_csv.open("w", newline="", encoding="utf-8-sig") as archivo:
            escritor = csv.DictWriter(
                archivo,
                fieldnames=CAMPOS_REPORTE,
                extrasaction="ignore",
            )
            escritor.writeheader()
            escritor.writerows(filas_reporte)

        ruta_ocr = base / "revision_humana_ocr.txt"
        ruta_ocr.write_text(
            "REVISIÓN HUMANA DE DOCUMENTOS CON OCR\n"
            "Este informe reproduce los textos detectados en el índice actual. "
            "No corrige ni completa las lecturas.\n"
            + "\n".join(detalle_revision)
            + "\n",
            encoding="utf-8",
        )

        ruta_resumen = base / "resumen_auditoria_calidad.txt"
        lineas = [
            "AUDITORÍA DE CALIDAD DEL CATÁLOGO LITÚRGICO",
            f"Documentos en inventario: {len(inventario)}",
            f"Documentos en catálogo: {len(catalogo)}",
            f"Registros en índice: {len(indice)}",
            f"Documentos con OCR (incluye OCR parcial): {cantidad_ocr}",
            f"Documentos OCR con alguna sección faltante: {cantidad_ocr_incompleta}",
            f"Fechas documentales distintas de la publicación: {cantidad_fecha_distinta}",
            f"Fechas del nombre del PDF distintas de la fecha documental: {cantidad_fecha_nombre_distinta}",
            f"Fechas duplicadas en el índice: {cantidad_duplicadas}",
            f"Documentos sin título de celebración: {cantidad_con_titulo_vacio}",
            f"Documentos sin ciclo identificado: {cantidad_con_ciclo_vacio}",
            f"Documentos con carácter de reemplazo OCR: {cantidad_texto_sospechoso}",
            "",
            "FALTANTES POR SECCIÓN:",
        ]
        for campo, etiqueta, _minimo in SECCIONES:
            lineas.append(f"- {etiqueta}: {total_faltantes[campo]}")

        lineas.extend(["", "ALERTAS POR TIPO:"])
        for alerta, cantidad in sorted(resumen_alertas.items()):
            lineas.append(f"- {alerta}: {cantidad}")

        lineas.extend([
            "",
            "ARCHIVOS GENERADOS:",
            "- auditoria_calidad_liturgica.csv: una fila por documento del catálogo.",
            "- revision_humana_ocr.txt: contenido detectado en cada documento con OCR.",
            "- resumen_auditoria_calidad.txt: conteos y alertas generales.",
            "",
            "CRITERIOS:",
            "- Las alertas automáticas son indicios para revisión, no correcciones.",
            "- La detección de referencias bíblicas es orientativa; no valida la cita contra una edición bíblica.",
            "- La diferencia entre fecha de publicación, nombre del PDF y fecha documental requiere cotejo con la portada/encabezado original.",
            "- La aclamación del 12-04-2020 se trata como excepción: la fuente presenta una Secuencia de Pascua y no se registra como aclamación.",
            "",
            "No se modificaron PostgreSQL, el calendario litúrgico ni los PDF originales.",
        ])
        ruta_resumen.write_text("\n".join(lineas), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS("Auditoría de calidad generada."))
        self.stdout.write(f"CSV: {ruta_csv}")
        self.stdout.write(f"Revisión OCR: {ruta_ocr}")
        self.stdout.write(f"Resumen: {ruta_resumen}")
        self.stdout.write(
            f"Documentos con OCR: {cantidad_ocr}; registros auditados: {len(filas_reporte)}."
        )
        self.stdout.write(
            self.style.WARNING(
                "Solo se leyeron los archivos locales y se generaron informes; "
                "no se modificaron PostgreSQL, el calendario ni los PDF originales."
            )
        )
