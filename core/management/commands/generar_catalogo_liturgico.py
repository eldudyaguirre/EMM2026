import csv
import json
import re
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


CATEGORIA_LECTURAS = "LECTURA_LITURGICA"
CATEGORIA_COMPLEMENTARIO = "DOCUMENTO_COMPLEMENTARIO"
CATEGORIA_PENDIENTE = "PENDIENTE_RECUPERACION"

CAMPOS_CATALOGO = (
    "fecha_publicacion",
    "fecha_documento",
    "origen_fecha",
    "titulo_publicacion",
    "titulo_celebracion",
    "ciclo",
    "ciclo_origen",
    "anio_liturgico",
    "liturgia_horas",
    "anio_liturgia_horas",
    "categoria",
    "motivo_clasificacion",
    "archivo_pdf",
    "archivo_texto",
    "url_pdf",
    "paginas",
    "caracteres_extraidos",
    "metodo_extraccion",
    "estado_descarga",
    "estado_extraccion",
    "observacion",
    "observacion_fecha",
)

CAMPOS_INDICE = (
    "fecha_documento",
    "fecha_publicacion",
    "titulo_celebracion",
    "ciclo",
    "ciclo_origen",
    "anio_liturgico",
    "primera_lectura",
    "salmo_responsorial",
    "segunda_lectura",
    "aclamacion",
    "evangelio",
    "archivo_pdf",
    "archivo_texto",
    "url_pdf",
    "metodo_extraccion",
    "estado_extraccion",
    "observacion_revision",
)

PATRONES_SECCION = (
    (
        "primera_lectura",
        re.compile(
            r"(?<![A-ZÁÉÍÓÚÑ])(?P<numero>\d{1,3}\s*[,.)|!]{0,3}\s*)?"
            r"(?P<titulo>PRIMERA\s+LECTURA\b)",
            re.I,
        ),
    ),
    (
        "salmo_responsorial",
        re.compile(
            r"(?<![A-ZÁÉÍÓÚÑ])(?P<numero>\d{1,3}\s*[,.)|!]{0,3}\s*)?"
            r"(?P<titulo>SALMO\s+RESPONSORIAL\b)",
            re.I,
        ),
    ),
    (
        "segunda_lectura",
        re.compile(
            r"(?<![A-ZÁÉÍÓÚÑ])(?P<numero>\d{1,3}\s*[,.)|!]{0,3}\s*)?"
            r"(?P<titulo>SE{1,2}[GC]UN[DO]A\s+LECTURA)",
            re.I,
        ),
    ),
    (
        "aclamacion",
        re.compile(
            r"(?<![A-ZÁÉÍÓÚÑ])(?P<numero>\d{1,3}\s*[,.)|!]{0,3}\s*)?"
            r"(?P<titulo>AC[CLT]AMACI[ÓO]N(?:\s+ANTES\s+DEL\s+EVANGELIO)?|ALELUYA)\b",
            re.I,
        ),
    ),
    (
        "evangelio",
        re.compile(
            r"(?<![A-ZÁÉÍÓÚÑ])(?P<numero>\d{1,3}\s*[,.)|!]{0,3}\s*)?"
            r"(?P<titulo>EVANGELIO\b|LECTURA\s+DEL\s+(?:SANTO\s+)?EVANGELIO\b)",
            re.I,
        ),
    ),
)

FIN_LECTURA = re.compile(
    r"^\s*(?:PALABRA\s+DE\s+DIOS|PALABRA\s+DEL\s+SEÑOR|"
    r"PALABRA\s+DEL\s+SENOR)\s*\.?\s*$",
    re.I,
)

MARCADORES_OTRAS_SECCIONES = re.compile(
    r"^\s*(?:\d{1,2}\s*[\.\)]\s*)?"
    r"(?:ORACI[ÓO]N\s+COLECTA|ORACI[ÓO]N\s+DE\s+LOS\s+FIELES|"
    r"ORACI[ÓO]N\s+UNIVERSAL|MONICI[ÓO]N|PRESENTACI[ÓO]N\s+DE\s+OFRENDAS|"
    r"PLEGARIA\s+EUCAR[ÍI]STICA|PADRE\s+NUESTRO|RITO\s+DE\s+COMUNI[ÓO]N|"
    r"LITURGIA\s+EUCAR[ÍI]STICA|PROFESI[ÓO]N\s+DE\s+FE|"
    r"ORACI[ÓO]N\s+SOBRE\s+LAS\s+OFRENDAS|ORACI[ÓO]N\s+DESPU[ÉE]S\s+DE\s+LA\s+COMUNI[ÓO]N|"
    r"DESPEDIDA|AVISOS\s+PARROQUIALES)\b",
    re.I,
)


def _normalizar(texto):
    texto = unicodedata.normalize("NFD", texto or "")
    texto = "".join(
        caracter for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )
    return re.sub(r"\s+", " ", texto).strip().upper()


def _int(valor, defecto=0):
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return defecto


def _leer_csv(ruta):
    with ruta.open("r", newline="", encoding="utf-8-sig") as archivo:
        lector = csv.DictReader(archivo)
        if not lector.fieldnames:
            raise CommandError(f"El inventario no tiene encabezados: {ruta}")
        return list(lector), set(lector.fieldnames)


def _guardar_csv(ruta, campos, filas):
    with ruta.open("w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.DictWriter(
            archivo,
            fieldnames=campos,
            extrasaction="ignore",
        )
        escritor.writeheader()
        escritor.writerows(filas)


def _lineas_documento(texto):
    lineas = []
    for linea in (texto or "").replace("\ufeff", "").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        if re.match(r"^={5,}\s*P[ÁA]GINA\s+\d+\s*={5,}$", linea, re.I):
            continue
        lineas.append(linea)
    return lineas



def _texto_pdf_por_columnas(ruta_pdf):
    """
    Recupera el texto del PDF ordenando primero la columna izquierda y luego
    la derecha cuando la geometría confirma una página a dos columnas.
    En páginas de una columna conserva el orden vertical habitual.
    """
    try:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        documento = fitz.open(str(ruta_pdf))
    except Exception:
        return ""

    paginas = []
    try:
        for pagina in documento:
            mitad = float(pagina.rect.width) / 2
            izquierda = []
            derecha = []
            centro = []
            todos = []

            for bloque in pagina.get_text("blocks"):
                if len(bloque) < 5:
                    continue
                x0, y0, x1, _y1, contenido = bloque[:5]
                contenido = (contenido or "").strip()
                if not contenido:
                    continue
                item = (float(y0), float(x0), float(x1), contenido)
                todos.append(item)

                if float(x1) <= mitad + 3:
                    izquierda.append(item)
                elif float(x0) >= mitad - 3:
                    derecha.append(item)
                else:
                    centro.append(item)

            # Solo aplicar el orden por columnas si hay bloques de texto
            # claramente ubicados a ambos lados de la página.
            if len(izquierda) >= 2 and len(derecha) >= 2:
                centro_izquierda = []
                centro_derecha = []
                for item in centro:
                    if (item[1] + item[2]) / 2 < mitad:
                        centro_izquierda.append(item)
                    else:
                        centro_derecha.append(item)

                ordenados = (
                    sorted(izquierda + centro_izquierda, key=lambda x: (x[0], x[1]))
                    + sorted(derecha + centro_derecha, key=lambda x: (x[0], x[1]))
                )
            else:
                ordenados = sorted(todos, key=lambda x: (x[0], x[1]))

            texto_pagina = "\n".join(item[3] for item in ordenados).strip()
            if texto_pagina:
                paginas.append(texto_pagina)
    except Exception:
        return ""
    finally:
        documento.close()

    return "\n".join(paginas).strip()


def _texto_para_catalogo(base, fila, texto_respaldo):
    """
    Prioriza el TXT cuando contiene OCR (incluidos PDF mixtos), porque puede
    incorporar páginas escaneadas que no tienen capa de texto digital.
    Para PDF exclusivamente digitales aplica el orden geométrico por columnas.
    """
    metodo = (fila.get("metodo_extraccion") or "").upper()
    if "OCR_TESSERACT" in metodo:
        return texto_respaldo or ""

    archivo_pdf = (fila.get("archivo_pdf") or "").strip()
    if archivo_pdf:
        ruta_relativa = Path(archivo_pdf.replace("\\", "/"))
        if not ruta_relativa.is_absolute():
            ruta_pdf = base / ruta_relativa
            if ruta_pdf.is_file():
                texto_pdf = _texto_pdf_por_columnas(ruta_pdf)
                minimo = max(80, int(len((texto_respaldo or "").strip()) * 0.40))
                if len(texto_pdf) >= minimo:
                    return texto_pdf
    return texto_respaldo or ""


def _recortar_fin_lectura(texto):
    """
    Recorta el marcador final sobre el texto original para conservar
    exactamente los desplazamientos de caracteres.
    """
    coincidencia = re.search(
        r"\bPALABRA\s+(?:DE\s+DIOS|DEL\s+SE[ÑN]OR)\b",
        texto or "",
        re.I,
    )
    if coincidencia:
        return texto[:coincidencia.start()].strip(), True
    return texto, False


def _es_prefijo_ocr_encabezado(prefijo):
    """
    Reconoce únicamente artefactos OCR observados delante de títulos.
    No acepta palabras normales como 'La' o 'En' para evitar falsos positivos.
    """
    return bool(
        re.fullmatch(
            r"(?:\[[0-9sSoO., )|!]{1,6}\]?|\[EJ\]|\[EY|\[E|\[ON|\[EX|"
            r"110\.\||EEN|EM|EJ|UY|EN|E|\(O\)|\(0\)|\[O\]|\[0\]|\(O|\[O|Q)",
            (prefijo or "").strip(),
        )
    )


def _extraer_secciones(texto):
    """
    Detecta encabezados en cualquier posición de una línea cuando van
    precedidos por un número de sección, y tolera prefijos OCR conocidos.
    Separa también varios encabezados que aparecen en una misma línea.
    """
    lineas = _lineas_documento(texto)
    detecciones = []

    for indice, linea in enumerate(lineas):
        candidatos = []
        for nombre, patron in PATRONES_SECCION:
            for coincidencia in patron.finditer(linea):
                prefijo = linea[:coincidencia.start()].strip()
                numerado = bool(coincidencia.group("numero"))

                # Un encabezado numerado puede aparecer después de texto de
                # otra columna en la misma línea. Sin número, solo se acepta
                # al inicio o tras un artefacto OCR reconocido.
                if not numerado:
                    if prefijo and not _es_prefijo_ocr_encabezado(prefijo):
                        continue
                    if len(linea) > 110:
                        continue

                candidatos.append(
                    (
                        coincidencia.start(),
                        coincidencia.end(),
                        nombre,
                    )
                )

        # Resolver posibles coincidencias solapadas y conservar el orden real.
        candidatos.sort(key=lambda item: (item[0], -(item[1] - item[0])))
        fin_anterior = -1
        for inicio, fin, nombre in candidatos:
            if inicio < fin_anterior:
                continue
            detecciones.append((indice, inicio, fin, nombre))
            fin_anterior = fin

    primeras = {}
    for indice, inicio, fin, nombre in detecciones:
        primeras.setdefault(nombre, (indice, inicio, fin))

    posiciones = sorted(
        (indice, inicio, fin, nombre)
        for nombre, (indice, inicio, fin) in primeras.items()
    )

    secciones = {
        "primera_lectura": "",
        "salmo_responsorial": "",
        "segunda_lectura": "",
        "aclamacion": "",
        "evangelio": "",
    }

    for posicion, (linea_inicio, inicio, fin_encabezado, nombre) in enumerate(posiciones):
        if posicion + 1 < len(posiciones):
            linea_fin, inicio_siguiente, _fin_siguiente, _nombre_siguiente = posiciones[posicion + 1]
        else:
            linea_fin = len(lineas)
            inicio_siguiente = 0

        partes = []

        # El encabezado y el contenido pueden compartir la misma línea.
        if linea_inicio == linea_fin:
            partes.append(lineas[linea_inicio][fin_encabezado:inicio_siguiente])
        else:
            partes.append(lineas[linea_inicio][fin_encabezado:])
            for indice_linea in range(linea_inicio + 1, linea_fin):
                partes.append(lineas[indice_linea])
            if linea_fin < len(lineas):
                partes.append(lineas[linea_fin][:inicio_siguiente])

        bloque = []
        terminado = False
        for parte in partes:
            if not parte.strip():
                continue

            contenido, es_fin = _recortar_fin_lectura(parte)
            if contenido:
                if MARCADORES_OTRAS_SECCIONES.match(_normalizar(contenido)):
                    break
                bloque.append(contenido.strip())

            if es_fin:
                terminado = True
                break

        secciones[nombre] = "\n".join(bloque).strip()

    return secciones


def _clasificar(fila, texto_disponible, tiene_lecturas=False):
    paginas = _int(fila.get("paginas"))
    estado = (fila.get("estado_extraccion") or "").upper()
    caracteres = _int(fila.get("caracteres_extraidos"))

    if estado in {"SIN_TEXTO", "ERROR"} or paginas == 0 or not texto_disponible:
        motivos = []
        if paginas == 0:
            motivos.append("El PDF no contiene páginas válidas reconocibles.")
        if estado in {"SIN_TEXTO", "ERROR"}:
            motivos.append(f"Estado de extracción: {estado}.")
        if not texto_disponible:
            motivos.append("No se encontró el TXT asociado en el archivo local.")
        return CATEGORIA_PENDIENTE, " ".join(motivos)

    titulo = (fila.get("titulo_celebracion") or "").strip()
    ciclo = (fila.get("ciclo") or "").strip()
    if titulo or ciclo or tiene_lecturas:
        return (
            CATEGORIA_LECTURAS,
            "Se identificó título, ciclo o encabezados de lecturas litúrgicas.",
        )

    if caracteres > 0:
        return (
            CATEGORIA_COMPLEMENTARIO,
            "Tiene texto recuperado, pero no presenta título de celebración ni ciclo identificados.",
        )

    return (
        CATEGORIA_PENDIENTE,
        "No se pudo confirmar texto utilizable del documento.",
    )


class Command(BaseCommand):
    help = (
        "Clasifica la biblioteca documental y genera un índice cronológico "
        "de lecturas. Solo crea CSV/JSONL/TXT; no modifica PostgreSQL ni PDF."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--salida",
            default="documentos_liturgicos_arquidiocesis",
            help="Carpeta que contiene el inventario y los TXT.",
        )

    def handle(self, *args, **options):
        base = Path(options["salida"]).expanduser().resolve()
        ruta_inventario = base / "inventario_documentos.csv"
        carpeta_txt = base / "texto_por_documento"

        if not ruta_inventario.is_file():
            raise CommandError(
                f"No existe el inventario: {ruta_inventario}"
            )
        if not carpeta_txt.is_dir():
            raise CommandError(
                f"No existe la carpeta de textos: {carpeta_txt}"
            )

        documentos, campos = _leer_csv(ruta_inventario)
        requeridos = {"fecha_publicacion", "archivo_pdf", "estado_extraccion"}
        faltantes = requeridos - campos
        if faltantes:
            raise CommandError(
                "El inventario no contiene columnas requeridas: "
                + ", ".join(sorted(faltantes))
            )

        catalogo = []
        indice = []
        complementarios = []
        pendientes = []
        contadores = Counter()

        for fila in documentos:
            archivo_pdf = (fila.get("archivo_pdf") or "").strip()
            nombre_pdf = Path(archivo_pdf.replace("\\", "/")).name
            nombre_txt = Path(nombre_pdf).stem + ".txt" if nombre_pdf else ""
            ruta_txt = carpeta_txt / nombre_txt
            texto_disponible = ruta_txt.is_file()
            texto = ""
            if texto_disponible:
                texto = ruta_txt.read_text(encoding="utf-8", errors="replace")

            texto = _texto_para_catalogo(base, fila, texto)
            secciones = _extraer_secciones(texto) if texto else {}
            tiene_lecturas = any(
                contenido.strip() for contenido in secciones.values()
            )
            categoria, motivo = _clasificar(
                fila, texto_disponible, tiene_lecturas=tiene_lecturas
            )

            archivo_texto = (
                str(ruta_txt.relative_to(base)).replace("\\", "/")
                if texto_disponible else ""
            )

            registro = {
                "fecha_publicacion": fila.get("fecha_publicacion", ""),
                "fecha_documento": fila.get("fecha_documento", ""),
                "origen_fecha": fila.get("origen_fecha", ""),
                "titulo_publicacion": fila.get("titulo_publicacion", ""),
                "titulo_celebracion": fila.get("titulo_celebracion", ""),
                "ciclo": fila.get("ciclo", ""),
                "ciclo_origen": fila.get("ciclo_origen", ""),
                "anio_liturgico": fila.get("anio_liturgico", ""),
                "liturgia_horas": fila.get("liturgia_horas", ""),
                "anio_liturgia_horas": fila.get("anio_liturgia_horas", ""),
                "categoria": categoria,
                "motivo_clasificacion": motivo,
                "archivo_pdf": archivo_pdf,
                "archivo_texto": archivo_texto,
                "url_pdf": fila.get("url_pdf", ""),
                "paginas": fila.get("paginas", ""),
                "caracteres_extraidos": fila.get("caracteres_extraidos", ""),
                "metodo_extraccion": fila.get("metodo_extraccion", ""),
                "estado_descarga": fila.get("estado_descarga", ""),
                "estado_extraccion": fila.get("estado_extraccion", ""),
                "observacion": fila.get("observacion", ""),
                "observacion_fecha": fila.get("observacion_fecha", ""),
            }
            catalogo.append(registro)
            contadores[categoria] += 1

            if categoria == CATEGORIA_PENDIENTE:
                pendientes.append(registro)
                continue

            if categoria == CATEGORIA_COMPLEMENTARIO:
                complementarios.append(registro)
                continue

            fecha = (fila.get("fecha_documento") or "").strip()
            if fecha:
                try:
                    date.fromisoformat(fecha)
                except ValueError:
                    fecha = ""

            lecturas = {
                "primera_lectura": secciones.get("primera_lectura", ""),
                "salmo_responsorial": secciones.get("salmo_responsorial", ""),
                "segunda_lectura": secciones.get("segunda_lectura", ""),
                "aclamacion": secciones.get("aclamacion", ""),
                "evangelio": secciones.get("evangelio", ""),
            }
            faltantes_lecturas = [
                nombre for nombre, contenido in lecturas.items() if not contenido.strip()
            ]
            observacion_revision = ""
            if not fecha:
                observacion_revision = "Fecha documental ausente o inválida; revisar."
            if faltantes_lecturas:
                nota = (
                    "No se detectaron automáticamente estas secciones: "
                    + ", ".join(faltantes_lecturas)
                    + ". Revisar el TXT; el índice no completa contenido faltante."
                )
                observacion_revision = (
                    f"{observacion_revision} {nota}".strip()
                )
            if "OCR_TESSERACT" in (fila.get("metodo_extraccion") or ""):
                observacion_revision = (
                    f"{observacion_revision} Texto OCR: requiere cotejo humano."
                ).strip()

            fila_indice = {
                "fecha_documento": fecha,
                "fecha_publicacion": fila.get("fecha_publicacion", ""),
                "titulo_celebracion": fila.get("titulo_celebracion", ""),
                "ciclo": fila.get("ciclo", ""),
                "ciclo_origen": fila.get("ciclo_origen", ""),
                "anio_liturgico": fila.get("anio_liturgico", ""),
                **lecturas,
                "archivo_pdf": archivo_pdf,
                "archivo_texto": archivo_texto,
                "url_pdf": fila.get("url_pdf", ""),
                "metodo_extraccion": fila.get("metodo_extraccion", ""),
                "estado_extraccion": fila.get("estado_extraccion", ""),
                "observacion_revision": observacion_revision,
            }
            indice.append(fila_indice)

        def clave_fecha(registro):
            valor = (registro.get("fecha_documento") or "").strip()
            try:
                return (0, date.fromisoformat(valor), registro.get("archivo_pdf", ""))
            except ValueError:
                return (1, date.max, registro.get("archivo_pdf", ""))

        catalogo.sort(key=clave_fecha)
        indice.sort(key=clave_fecha)
        complementarios.sort(key=clave_fecha)
        pendientes.sort(key=clave_fecha)

        _guardar_csv(base / "catalogo_documental.csv", CAMPOS_CATALOGO, catalogo)
        _guardar_csv(
            base / "indice_liturgico_cronologico.csv",
            CAMPOS_INDICE,
            indice,
        )
        _guardar_csv(
            base / "documentos_complementarios.csv",
            CAMPOS_CATALOGO,
            complementarios,
        )
        _guardar_csv(
            base / "pendientes_recuperacion.csv",
            CAMPOS_CATALOGO,
            pendientes,
        )

        ruta_jsonl = base / "indice_liturgico_cronologico.jsonl"
        with ruta_jsonl.open("w", encoding="utf-8") as archivo:
            for registro in indice:
                archivo.write(
                    json.dumps(registro, ensure_ascii=False) + "\n"
                )

        ruta_resumen = base / "RESUMEN_CATALOGO.txt"
        lineas = [
            "CATÁLOGO DOCUMENTAL LITÚRGICO - EMAÚS",
            f"Documentos inventariados: {len(catalogo)}",
            f"Lecturas litúrgicas: {contadores[CATEGORIA_LECTURAS]}",
            f"Documentos complementarios: {contadores[CATEGORIA_COMPLEMENTARIO]}",
            f"Pendientes de recuperación: {contadores[CATEGORIA_PENDIENTE]}",
            f"Registros en índice cronológico: {len(indice)}",
            "",
            "Archivos generados:",
            "- catalogo_documental.csv: clasificación de los documentos.",
            "- indice_liturgico_cronologico.csv: fechas y bloques de lecturas detectados.",
            "- indice_liturgico_cronologico.jsonl: índice estructurado para integración posterior.",
            "- documentos_complementarios.csv: avisos y documentos sin lecturas identificadas.",
            "- pendientes_recuperacion.csv: archivos sin texto o sin páginas válidas.",
            "",
            "Las lecturas se copian únicamente cuando se detecta su encabezado.",
            "El contenido OCR se marca para revisión humana.",
            "No se modificaron los PDF originales, PostgreSQL ni el calendario litúrgico.",
        ]
        ruta_resumen.write_text("\n".join(lineas), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS("Catálogo generado correctamente."))
        self.stdout.write(f"Total documentos: {len(catalogo)}")
        self.stdout.write(f"Lecturas litúrgicas: {contadores[CATEGORIA_LECTURAS]}")
        self.stdout.write(
            f"Documentos complementarios: {contadores[CATEGORIA_COMPLEMENTARIO]}"
        )
        self.stdout.write(
            f"Pendientes de recuperación: {contadores[CATEGORIA_PENDIENTE]}"
        )
        self.stdout.write(f"Índice cronológico: {len(indice)} registros")
        self.stdout.write(f"Resultados: {base}")
        self.stdout.write(
            self.style.WARNING(
                "No se modificó PostgreSQL, los PDF originales ni el calendario existente."
            )
        )
