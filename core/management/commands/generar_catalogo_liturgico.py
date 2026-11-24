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
            r"(?<![A-ZÁÉÍÓÚÑ])(?P<numero>\d{1,3}(?:\s*[,.)|!]){0,3}\s*)?"
            r"(?P<titulo>PRIMERA\s+LECTURA\b)",
            re.I,
        ),
    ),
    (
        "salmo_responsorial",
        re.compile(
            r"(?<![A-ZÁÉÍÓÚÑ])(?P<numero>\d{1,3}(?:\s*[,.)|!]){0,3}\s*)?"
            r"(?P<titulo>SALMO\s+RESPONSORIAL\b)",
            re.I,
        ),
    ),
    (
        "segunda_lectura",
        re.compile(
            r"(?<![A-ZÁÉÍÓÚÑ])(?P<numero>\d{1,3}(?:\s*[,.)|!]){0,3}\s*)?"
            r"(?P<titulo>SE{1,2}[GC]UN[DO]A\s+LECTURA)",
            re.I,
        ),
    ),
    (
        "aclamacion",
        re.compile(
            r"(?<![A-ZÁÉÍÓÚÑ])(?P<numero>\d{1,3}(?:\s*[,.)|!]){0,3}\s*)?"
            r"(?P<titulo>AC[CLT]AMACI[ÓO]N(?:\s+ANTES\s+DEL\s+EVANGELIO)?|ALELUYA)\b",
            re.I,
        ),
    ),
    (
        "evangelio",
        re.compile(
            r"(?<![A-ZÁÉÍÓÚÑ])(?P<numero>\d{1,3}(?:\s*[,.)|!]){0,3}\s*)?"
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
    Recupera el texto digital respetando columnas y bandas transversales.
    Cada zona entre "Liturgia de la Palabra" y "Liturgia Eucarística" se lee
    primero por la columna izquierda y después por la derecha.
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
            todos = []

            def normalizar_bloque(valor):
                return (
                    unicodedata.normalize("NFD", valor or "")
                    .encode("ascii", "ignore")
                    .decode("ascii")
                    .upper()
                )

            patron_banda = re.compile(
                r"LITURGIA\s+(?:DE\s+LA\s+PALAB|EUCAR)",
                re.I,
            )
            for bloque in pagina.get_text("blocks"):
                if len(bloque) < 5:
                    continue
                x0, y0, x1, y1, contenido = bloque[:5]
                contenido = (contenido or "").strip()
                if not contenido:
                    continue
                todos.append({
                    "x0": float(x0),
                    "y0": float(y0),
                    "x1": float(x1),
                    "y1": float(y1),
                    "texto": contenido,
                })

            if not todos:
                texto = pagina.get_text("text", sort=True) or ""
                if texto.strip():
                    paginas.append(texto.strip())
                continue

            izquierda = []
            derecha = []
            centro = []
            for item in todos:
                item["banda"] = bool(
                    patron_banda.search(normalizar_bloque(item["texto"]))
                )
            bandas = [item for item in todos if item["banda"]]
            for item in todos:
                if item["banda"]:
                    continue
                if re.fullmatch(r"\\s*ISTICA\\s*", item["texto"], re.I):
                    if any(abs(item["y0"] - banda["y0"]) < 18 for banda in bandas):
                        continue
                centro_x = (item["x0"] + item["x1"]) / 2
                if item["x0"] < mitad - 8 and item["x1"] > mitad + 8:
                    centro.append(item)
                elif centro_x < mitad:
                    izquierda.append(item)
                else:
                    derecha.append(item)

            if len(izquierda) < 2 or len(derecha) < 2:
                texto = pagina.get_text("text", sort=True) or ""
                if texto.strip():
                    paginas.append(texto.strip())
                continue

            def ordenar(items):
                return sorted(items, key=lambda x: (x["y0"], x["x0"]))

            bandas_ordenadas = sorted(bandas, key=lambda x: (x["y0"], x["x0"]))
            bandas_combinadas = []
            for banda in bandas_ordenadas:
                if bandas_combinadas and banda["y0"] <= bandas_combinadas[-1]["y1"] + 18:
                    bandas_combinadas[-1]["y1"] = max(
                        bandas_combinadas[-1]["y1"],
                        banda["y1"],
                    )
                else:
                    bandas_combinadas.append({
                        "y0": banda["y0"],
                        "y1": banda["y1"],
                    })

            salida = []
            limite_superior = float("-inf")
            for banda in bandas_combinadas:
                y_inicio = banda["y0"]
                zona_izquierda = [
                    x for x in izquierda
                    if limite_superior <= x["y0"] < y_inicio
                ]
                zona_derecha = [
                    x for x in derecha
                    if limite_superior <= x["y0"] < y_inicio
                ]
                zona_centro = [
                    x for x in centro
                    if limite_superior <= x["y0"] < y_inicio
                ]
                salida.extend(x["texto"] for x in ordenar(zona_izquierda))
                salida.extend(x["texto"] for x in ordenar(zona_derecha))
                salida.extend(x["texto"] for x in ordenar(zona_centro))
                limite_superior = max(limite_superior, banda["y1"])

            if not bandas_combinadas:
                restantes_izquierda = izquierda
                restantes_derecha = derecha
                restantes_centro = centro
            else:
                restantes_izquierda = [
                    x for x in izquierda if x["y0"] >= limite_superior
                ]
                restantes_derecha = [
                    x for x in derecha if x["y0"] >= limite_superior
                ]
                restantes_centro = [
                    x for x in centro if x["y0"] >= limite_superior
                ]

            salida.extend(x["texto"] for x in ordenar(restantes_izquierda))
            salida.extend(x["texto"] for x in ordenar(restantes_derecha))
            salida.extend(x["texto"] for x in ordenar(restantes_centro))

            texto_pagina = "\n".join(salida).strip()
            texto_original = pagina.get_text("text", sort=True) or ""
            if len(texto_pagina) < len(texto_original) * 0.75:
                texto_pagina = texto_original
            if texto_pagina.strip():
                paginas.append(texto_pagina.strip())
    except Exception:
        return ""
    finally:
        documento.close()

    return "\n".join(paginas).strip()


def _texto_para_catalogo(base, fila, texto_respaldo):
    """
    Usa como fuente principal el TXT creado por extraer_documentos_liturgicos.
    Ese TXT ya aplica el orden geométrico de columnas por página y mezcla
    correctamente texto digital con OCR selectivo. El PDF solo se usa como
    respaldo cuando falta el TXT.
    """
    texto_respaldo = (texto_respaldo or "").strip()
    if texto_respaldo:
        return texto_respaldo

    archivo_pdf = (fila.get("archivo_pdf") or "").strip()
    if archivo_pdf:
        ruta_relativa = Path(archivo_pdf.replace("\\", "/"))
        if not ruta_relativa.is_absolute():
            ruta_pdf = base / ruta_relativa
            if ruta_pdf.is_file():
                return _texto_pdf_por_columnas(ruta_pdf)
    return ""



def _recortar_fin_lectura(texto):
    """
    Recorta solo la fórmula final "Palabra de Dios" cuando aparece como
    marcador litúrgico independiente, no cuando la frase forma parte de una
    oración de la lectura (por ejemplo, "aceptaron la palabra del Señor").
    """
    coincidencia = re.search(
        r"(?im)(?:^|[.!?]\s+|[”’]\s+)PALABRA\s+DE\s+DIOS\b",
        texto or "",
    )
    if coincidencia:
        inicio = coincidencia.start()
        fragmento = coincidencia.group(0)
        inicio += len(fragmento) - len(fragmento.lstrip())
        return texto[:inicio].strip(), True
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


def _recortar_inicio_seccion(nombre, texto):
    """
    El OCR y la lectura de columnas pueden dejar al inicio de una sección
    texto de otro bloque. Recorta hasta el ancla propia de cada lectura.
    Si no encuentra un ancla fiable, conserva el texto original para revisión.
    """
    anclas = {
        "primera_lectura": re.compile(
            r"\bLECTURA\s+(?:DEL|DE\s+LA|DE\s+LOS|DE\s+LAS)\b",
            re.I,
        ),
        "salmo_responsorial": re.compile(r"\bSALMISTA\s*:", re.I),
        "segunda_lectura": re.compile(
            r"\bLECTURA\s+(?:DEL|DE\s+LA|DE\s+LOS|DE\s+LAS)\b",
            re.I,
        ),
        "aclamacion": re.compile(
            r"\b(?:ASAMBLEA\s*:\s*(?:R\.?\s*)?ALELUYA|"
            r"R\.?\s*ALELUYA|CANTOR\s*:)",
            re.I,
        ),
        "evangelio": re.compile(
            r"\b(?:LECTURA\s+DEL\s+(?:SANTO\s+)?EVANGELIO|"
            r"DEL\s+SANTO\s+EVANGELIO|SEG[ÚU]N\s+SAN\s+"
            r"(?:MATEO|MARCOS|LUCAS|JUAN))\b",
            re.I,
        ),
    }
    patron = anclas.get(nombre)
    if not patron:
        return texto, False

    coincidencia = patron.search(texto or "")
    if not coincidencia:
        return texto, False

    inicio = coincidencia.start()

    # Conserva la referencia del salmo que suele aparecer entre el título
    # y "Salmista:", sin conservar el material anterior de otra columna.
    if nombre == "salmo_responsorial":
        prefijo = (texto or "")[:inicio].strip()
        referencia = re.search(r"\(?\s*SALMO\s+\d{1,3}\s*\)?", prefijo, re.I)
        if referencia:
            inicio = referencia.start()

    # En la aclamación puede haber una cita breve antes de "Asamblea: Aleluya".
    if nombre == "aclamacion":
        prefijo = (texto or "")[:inicio].strip()
        if len(prefijo) <= 45 and re.search(
            r"\b(?:JN|MT|MC|LC|FLP|CF[RC]?\.?)\s*\d",
            prefijo,
            re.I,
        ):
            inicio = max(0, (texto or "").rfind(prefijo))

    return (texto or "")[inicio:].strip(), True


def _recortar_fin_seccion(nombre, texto):
    """
    Recorta el texto al marcador final o al inicio de la siguiente parte de
    la celebración. No sustituye ni completa el contenido de las fuentes.
    """
    patrones = []
    if nombre in {"primera_lectura", "segunda_lectura"}:
        patrones = [
            re.compile(
                r"(?im)(?:^|[.!?]\s+|[”’]\s+)PALABRA\s+DE\s+DIOS\b"
            ),
        ]
    elif nombre == "salmo_responsorial":
        patrones = [
            re.compile(
                r"\b(?:LECTURA\s+(?:DEL|DE\s+LA)|ACLAMACI[ÓO]N|"
                r"LECTURA\s+DEL\s+(?:SANTO\s+)?EVANGELIO|"
                r"PROFESI[ÓO]N\s+DE\s+FE|ORACI[ÓO]N\s+UNIVERSAL)\b",
                re.I,
            ),
        ]
    elif nombre == "aclamacion":
        patrones = [
            re.compile(
                r"(?im)^\s*(?:\([OD0]\)\s*)?(?:EVANGELIO|EVANCE(?:LIO|LO|IO))\b"
            ),
            re.compile(
                r"\b(?:LECTURA\s+DEL\s+(?:SANTO\s+)?EVANGELIO|"
                r"DEL\s+SANTO\s+EVANGELIO|SEG[ÚU]N\s+SAN\s+"
                r"(?:MATEO|MARCOS|LUCAS|JUAN)|"
                r"PROFESI[ÓO]N\s+DE\s+FE|ORACI[ÓO]N\s+UNIVERSAL|"
                r"\d{1,2}\s*[.)]\s*POR\s+(?:EL\s+PAPA|LA\s+IGLESIA|LOS\s+GOBERNANTES))\b",
                re.I,
            ),
        ]
    elif nombre == "evangelio":
        patrones = [
            re.compile(
                r"(?im)(?:^|[.!?]\s+|[”’]\s+)PALABRA\s+DEL\s+SE[ÑN]OR\b"
            ),
            re.compile(
                r"\b(?:PROFESI[ÓO]N\s+DE\s+FE|ORACI[ÓO]N\s+UNIVERSAL|"
                r"ORACI[ÓO]N\s+SOBRE\s+LAS\s+OFRENDAS|"
                r"LITURGIA\s+EUCAR[ÍI]STICA)\b",
                re.I,
            ),
        ]

    posiciones = []
    for patron in patrones:
        coincidencia = patron.search(texto or "")
        if coincidencia:
            posiciones.append(coincidencia.start())
    if not posiciones:
        return texto
    return (texto or "")[:min(posiciones)].strip()


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
        # Cuando OCR pega la primera palabra al final del título (por ejemplo,
        # "LECTURASobre"), suele ser texto de la columna vecina; se descarta
        # ese resto de línea y se continúa con las líneas siguientes.
        resto_encabezado = lineas[linea_inicio][fin_encabezado:]
        if resto_encabezado and resto_encabezado[0].isalnum():
            resto_encabezado = ""

        if linea_inicio == linea_fin:
            partes.append(resto_encabezado[:max(0, inicio_siguiente - fin_encabezado)])
        else:
            partes.append(resto_encabezado)
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

        texto_seccion = "\n".join(bloque).strip()
        texto_seccion, _ancla_encontrada = _recortar_inicio_seccion(
            nombre,
            texto_seccion,
        )
        texto_seccion = _recortar_fin_seccion(nombre, texto_seccion)
        secciones[nombre] = texto_seccion

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
