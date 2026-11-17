import csv
import hashlib
import json
import re
import os
import shutil
import subprocess
import tempfile
import time
from datetime import date, timedelta
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError


URL_LISTADO = "https://www.arquidiocesisdecuenca.com/domingo-dia-del-senor/"
MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

CAMPOS_CSV = (
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
    "url_pdf",
    "archivo_pdf",
    "paginas",
    "caracteres_extraidos",
    "metodo_extraccion",
    "sha256",
    "estado_descarga",
    "estado_extraccion",
    "observacion",
    "observacion_fecha",
)


class _ListadoPDFParser(HTMLParser):
    """Obtiene títulos de publicaciones y enlaces PDF desde cada página."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.documentos = []
        self.encabezado = None
        self.enlace = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() in {"h2", "h3", "h4"} and self.encabezado is None:
            self.encabezado = {"partes": [], "href": ""}
        if tag.lower() == "a":
            self.enlace = {
                "href": attrs.get("href", ""),
                "partes": [],
                "dentro_encabezado": self.encabezado is not None,
            }

    def handle_data(self, data):
        if self.encabezado is not None:
            self.encabezado["partes"].append(data)
        if self.enlace is not None:
            self.enlace["partes"].append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "a" and self.enlace is not None:
            href = self.enlace["href"]
            if _es_pdf(href):
                if self.enlace["dentro_encabezado"] and self.encabezado is not None:
                    self.encabezado["href"] = href
                elif self.documentos and not self.documentos[-1]["href"]:
                    self.documentos[-1]["href"] = href
                elif not self.documentos:
                    texto = " ".join(self.enlace["partes"]).strip()
                    self.documentos.append({"titulo": texto, "href": href})
            self.enlace = None

        if tag in {"h2", "h3", "h4"} and self.encabezado is not None:
            titulo = re.sub(
                r"\s+", " ", " ".join(self.encabezado["partes"])
            ).strip()
            href = self.encabezado["href"]
            if titulo:
                self.documentos.append({"titulo": titulo, "href": href})
            self.encabezado = None


def _es_pdf(href):
    if not href:
        return False
    ruta = urlparse(href).path.lower()
    return ruta.endswith(".pdf")


def _fecha_desde_titulo(titulo):
    texto = (titulo or "").lower()
    patron = (
        r"\b(\d{1,2})\s+de\s+"
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
        r"septiembre|setiembre|octubre|noviembre|diciembre)"
        r"\s+de\s+(20\d{2})\b"
    )
    coincidencia = re.search(patron, texto, flags=re.IGNORECASE)
    if not coincidencia:
        return None
    try:
        return date(
            int(coincidencia.group(3)),
            MESES[coincidencia.group(2).lower()],
            int(coincidencia.group(1)),
        )
    except ValueError:
        return None


def _nombre_seguro(valor):
    valor = unquote(valor or "")
    valor = re.sub(r"[^A-Za-z0-9._-]+", "_", valor).strip("._")
    return valor[:140] or "documento.pdf"


def _solicitar(url, timeout, reintentos):
    ultimo_error = None
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "application/pdf,*/*;q=0.8"
        ),
        "Accept-Language": "es-EC,es;q=0.9,en;q=0.7",
    }
    for intento in range(reintentos + 1):
        try:
            solicitud = Request(url, headers=headers)
            with urlopen(solicitud, timeout=timeout) as respuesta:
                return respuesta.read(), respuesta.geturl(), respuesta.status
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            ultimo_error = exc
            if isinstance(exc, HTTPError) and exc.code not in (408, 429, 500, 502, 503, 504):
                break
            if intento < reintentos:
                time.sleep(min(2 ** intento, 10))
    raise ultimo_error


def _leer_listado(url, timeout, reintentos):
    raw, url_final, status = _solicitar(url, timeout, reintentos)
    html = raw.decode("utf-8", errors="replace")
    parser = _ListadoPDFParser()
    parser.feed(html)
    parser.close()

    encontrados = []
    vistos = set()
    for documento in parser.documentos:
        href = documento.get("href", "").strip()
        titulo = documento.get("titulo", "").strip()
        if not _es_pdf(href):
            continue
        pdf_url = urljoin(url_final, href)
        if pdf_url in vistos:
            continue
        vistos.add(pdf_url)
        encontrados.append(
            {
                "titulo": titulo,
                "url_pdf": pdf_url,
                "fecha": _fecha_desde_titulo(titulo),
            }
        )
    return encontrados, status


def _extraer_pdf(ruta_pdf):
    """Extrae texto digital por página y metadatos del PDF."""
    try:
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf

        with pymupdf.open(str(ruta_pdf)) as documento:
            paginas = [
                pagina.get_text("text", sort=True) or ""
                for pagina in documento
            ]
            metadatos = documento.metadata or {}
            total = len(documento)
        return paginas, total, metadatos, "PyMuPDF"
    except ImportError:
        pass

    try:
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader

        lector = PdfReader(str(ruta_pdf), strict=False)
        if lector.is_encrypted:
            try:
                lector.decrypt("")
            except Exception:
                pass
        paginas = []
        for pagina in lector.pages:
            try:
                paginas.append(pagina.extract_text() or "")
            except Exception:
                paginas.append("")
        return paginas, len(lector.pages), lector.metadata or {}, "pypdf/PyPDF2"
    except ImportError as exc:
        raise CommandError(
            "No está instalado PyMuPDF ni pypdf/PyPDF2. "
            "Instala PyMuPDF con: .\\venv\\Scripts\\python.exe -m pip install pymupdf"
        ) from exc



def _detectar_motor_pdf():
    """Verifica antes de descargar que exista un motor de lectura PDF."""
    try:
        import pymupdf  # noqa: F401
        return "PyMuPDF"
    except ImportError:
        try:
            import fitz  # noqa: F401
            return "PyMuPDF"
        except ImportError:
            pass

    try:
        from pypdf import PdfReader  # noqa: F401
        return "pypdf"
    except ImportError:
        pass

    try:
        from PyPDF2 import PdfReader  # noqa: F401
        return "PyPDF2"
    except ImportError:
        pass

    raise CommandError(
        "No hay un motor PDF instalado. "
        "Ejecuta: .\\venv\\Scripts\\python.exe -m pip install PyMuPDF"
    )


def _resolver_tesseract():
    """Busca Tesseract en PATH, variable de entorno y rutas habituales de Windows."""
    encontrado = shutil.which("tesseract")
    if encontrado:
        return encontrado

    configurado = os.environ.get("TESSERACT_CMD")
    candidatos = []
    if configurado:
        candidatos.append(Path(configurado))

    programas = os.environ.get("ProgramFiles", r"C:\Program Files")
    programas_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    candidatos.extend([
        Path(programas) / "Tesseract-OCR" / "tesseract.exe",
        Path(programas_x86) / "Tesseract-OCR" / "tesseract.exe",
    ])

    for candidato in candidatos:
        if candidato.is_file():
            return str(candidato)
    return None


def _validar_tesseract(ejecutable, idioma):
    """Comprueba que Tesseract y los modelos de idioma solicitados estén disponibles."""
    try:
        resultado = subprocess.run(
            [ejecutable, "--list-langs"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CommandError(
            f"No se pudo ejecutar Tesseract ({ejecutable}): {exc}"
        ) from exc

    if resultado.returncode != 0:
        detalle = (resultado.stderr or resultado.stdout or "sin detalle").strip()
        raise CommandError(f"Tesseract no pudo listar idiomas: {detalle}")

    disponibles = set(
        re.findall(r"(?m)^\s*([A-Za-z0-9_]+)\s*$", resultado.stdout)
    )
    solicitados = [codigo.strip() for codigo in idioma.split("+") if codigo.strip()]
    faltantes = [codigo for codigo in solicitados if codigo not in disponibles]
    if faltantes:
        raise CommandError(
            "Faltan modelos de idioma en Tesseract: "
            + ", ".join(faltantes)
            + ". Instala los archivos .traineddata en la carpeta tessdata "
              "y comprueba nuevamente con 'tesseract --list-langs'."
        )
    return sorted(disponibles)


def _ocr_pdf(ruta_pdf, ejecutable, idioma="spa", dpi=300):
    """
    Reconoce texto de un PDF escaneado página por página.

    Renderiza cada página temporalmente con PyMuPDF y ejecuta Tesseract.
    El PDF original nunca se modifica.
    """
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf

    escala = dpi / 72.0
    textos = []

    with tempfile.TemporaryDirectory(prefix="emaus_ocr_") as temporal:
        carpeta_temporal = Path(temporal)
        with pymupdf.open(str(ruta_pdf)) as documento:
            for indice, pagina in enumerate(documento, start=1):
                pixmap = pagina.get_pixmap(
                    matrix=pymupdf.Matrix(escala, escala),
                    colorspace=pymupdf.csRGB,
                    alpha=False,
                )
                imagen = carpeta_temporal / f"pagina_{indice:04d}.png"
                pixmap.save(str(imagen))

                comando = [
                    ejecutable,
                    str(imagen),
                    "stdout",
                    "-l",
                    idioma,
                    "--oem",
                    "1",
                    "--psm",
                    "3",
                ]
                resultado = subprocess.run(
                    comando,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=300,
                    check=False,
                )
                if resultado.returncode != 0:
                    detalle = (resultado.stderr or resultado.stdout or "").strip()
                    raise RuntimeError(
                        f"Tesseract falló en la página {indice}: {detalle[:500]}"
                    )
                textos.append((resultado.stdout or "").strip())

    return textos

def _texto_metadato(valor):
    if valor is None:
        return ""
    return str(valor).strip()


def _normalizar_busqueda(texto):
    texto = unicodedata.normalize("NFD", texto or "")
    texto = "".join(
        caracter for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )
    return re.sub(r"\s+", " ", texto).strip()


def _fecha_desde_texto_pdf(texto):
    """
    Reconoce fechas del encabezado litúrgico, incluso cuando proceden de OCR.
    Descarta fechas de citas, colectas y mensajes que no sean la celebración.
    """
    meses = (
        "enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
        "septiembre|setiembre|octubre|noviembre|diciembre"
    )
    patrones = (
        rf"\b(\d{{1,2}})\s+de\s+({meses})\s+(?:(?:de|del)\s*)?(20\d{{2}})\b",
        rf"\b(\d{{1,2}})\s+({meses})\s+(20\d{{2}})\b",
        r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b",
    )
    pistas_liturgicas = (
        r"\bDOMINGO\b|\bSOLEMNIDAD\b|\bFIESTA\b|\bPASCUA\b|"
        r"\bADVIENTO\b|\bCUARESMA\b|\bNAVIDAD\b|\bCICLO\s+[ABC]\b|"
        r"\bCRISTO REY\b|\bBAUTISMO DEL SENOR\b|\bPENTECOSTES\b|"
        r"\bASCENSION\b|\bCORPUS CHRISTI\b|\bSAGRADA FAMILIA\b|"
        r"\bEPIFANIA\b"
    )
    referencias_no_validas = (
        r"\bCOLECTA\b|\bPAPA FRANCISCO\b|\bSANTO PADRE\b|"
        r"\bHOMILIA\b|\bAUDIENCIA\b|\bDISCURSO\b"
    )

    lineas = [
        _normalizar_busqueda(linea).upper()
        for linea in (texto or "").splitlines()
        if linea.strip()
    ]
    primeras = lineas[:45]
    hay_contexto_liturgico = bool(
        re.search(pistas_liturgicas, " ".join(primeras), flags=re.IGNORECASE)
    )

    for indice, linea in enumerate(primeras):
        if re.search(referencias_no_validas, linea, flags=re.IGNORECASE):
            continue

        coincidencia = None
        formato = None
        for numero, patron in enumerate(patrones):
            coincidencia = re.search(patron, linea, flags=re.IGNORECASE)
            if coincidencia:
                formato = numero
                break

        if not coincidencia:
            continue

        contexto_cercano = " ".join(
            primeras[max(0, indice - 3):min(len(primeras), indice + 3)]
        )
        fecha_en_encabezado = (
            indice < 15
            and hay_contexto_liturgico
            and not re.search(
                referencias_no_validas, contexto_cercano, flags=re.IGNORECASE
            )
        )
        if not fecha_en_encabezado:
            continue

        try:
            if formato in (0, 1):
                return date(
                    int(coincidencia.group(3)),
                    MESES[coincidencia.group(2).lower()],
                    int(coincidencia.group(1)),
                )
            return date(
                int(coincidencia.group(3)),
                int(coincidencia.group(2)),
                int(coincidencia.group(1)),
            )
        except (ValueError, KeyError):
            continue

    return None



def _ciclo_por_fecha(fecha_documento):
    """Calcula el ciclo dominical usando el inicio del año litúrgico."""
    if not fecha_documento:
        return "", ""

    tres_diciembre = date(fecha_documento.year, 12, 3)
    primer_domingo_adviento = tres_diciembre - timedelta(
        days=(tres_diciembre.weekday() + 1) % 7
    )

    anio_liturgico = fecha_documento.year
    if fecha_documento >= primer_domingo_adviento:
        anio_liturgico += 1

    ciclos = {0: "C", 1: "A", 2: "B"}
    return ciclos[anio_liturgico % 3], str(anio_liturgico)


def _extraer_datos_liturgicos(texto, fecha_listado=None):
    """Extrae datos del encabezado y completa ciclos con reglas de calendario."""
    primeras_lineas = [
        linea.strip() for linea in (texto or "").splitlines() if linea.strip()
    ]
    primeras_normalizadas = [
        _normalizar_busqueda(linea).upper() for linea in primeras_lineas
    ]
    encabezado = " ".join(primeras_normalizadas[:45])

    fecha_pdf = _fecha_desde_texto_pdf(texto)
    fecha_efectiva = fecha_pdf or fecha_listado
    origen_fecha = "PDF" if fecha_pdf else ("LISTADO_WEB" if fecha_listado else "")

    ciclo = ""
    ciclo_origen = ""
    coincidencia = re.search(
        r"\bCiclo(?:\s+dominical)?\s*[:\-]?\s*([ABC])\b",
        encabezado,
        flags=re.IGNORECASE,
    )
    if coincidencia:
        ciclo = coincidencia.group(1).upper()
        ciclo_origen = "PDF_EXPLICITO"

    liturgia_horas = ""
    coincidencia = re.search(
        r"Liturgia de las Horas\s*:\s*([^–\-\n]+)",
        encabezado,
        flags=re.IGNORECASE,
    )
    if coincidencia:
        liturgia_horas = coincidencia.group(1).strip()

    anio_lh = ""
    coincidencia = re.search(
        r"\bAño\s+([IVXLCDM]+|\d+)\b",
        encabezado,
        flags=re.IGNORECASE,
    )
    if coincidencia:
        anio_lh = coincidencia.group(1).upper()

    # Buscar encabezados litúrgicos completos antes de aceptar palabras
    # genéricas como "Bautismo" que pueden aparecer en el cuerpo del mensaje.
    patrones_titulo = (
        r"\b(?:EL\s+)?BAUTISMO\s+DEL\s+SENOR\b",
        r"\bDOMINGO\b.{0,100}\b(?:CICLO\s+[ABC]|TIEMPO|ORDINARIO|ADVIENTO|CUARESMA|PASCUA)\b",
        r"\bSOLEMNIDAD\b.{0,100}",
        r"\b(?:EPIFANIA|PENTECOSTES|ASCENSION|CORPUS CHRISTI|SAGRADA FAMILIA)\b.{0,100}",
        r"\bNATIVIDAD\b.{0,80}",
    )
    celebracion = ""
    for patron in patrones_titulo:
        for indice, normalizada in enumerate(primeras_normalizadas[:45]):
            coincidencia = re.search(patron, normalizada, flags=re.IGNORECASE)
            if coincidencia:
                celebracion = primeras_lineas[indice]
                break
        if celebracion:
            break

    # No convertir avisos o mensajes pastorales en celebraciones por una
    # palabra suelta del cuerpo del documento.
    contiene_lecturas = bool(
        re.search(
            r"\bPRIMERA LECTURA\b|\bSEGUNDA LECTURA\b|"
            r"\bSALMO RESPONSORIAL\b|\bEVANGELIO\b|"
            r"\bACLAMACION ANTES DEL EVANGELIO\b",
            encabezado,
            flags=re.IGNORECASE,
        )
    )
    es_documento_liturgico = bool(ciclo or celebracion or contiene_lecturas)

    anio_liturgico = ""
    if fecha_efectiva and es_documento_liturgico:
        ciclo_calculado, anio_liturgico = _ciclo_por_fecha(fecha_efectiva)
        if not ciclo:
            ciclo = ciclo_calculado
            if ciclo:
                ciclo_origen = "CALCULADO_POR_FECHA"

    observaciones = []
    if fecha_pdf and fecha_listado and fecha_pdf != fecha_listado:
        observaciones.append(
            "La fecha del encabezado litúrgico PDF difiere de la fecha del listado web."
        )
    elif not fecha_pdf and fecha_listado:
        observaciones.append(
            "No se identificó una fecha válida en el encabezado; se conserva la fecha del listado web."
        )
    if not es_documento_liturgico:
        observaciones.append(
            "El PDF no presenta encabezado litúrgico ni lecturas reconocibles; no se asigna ciclo."
        )

    return {
        "fecha_documento": fecha_efectiva.isoformat() if fecha_efectiva else "",
        "origen_fecha": origen_fecha,
        "titulo_celebracion": celebracion,
        "ciclo": ciclo,
        "ciclo_origen": ciclo_origen,
        "anio_liturgico": anio_liturgico,
        "liturgia_horas": liturgia_horas,
        "anio_liturgia_horas": anio_lh,
        "observacion_fecha": " ".join(observaciones),
    }



class Command(BaseCommand):
    help = (
        "Descarga e inventaría los PDF de 'Domingo día del Señor' "
        "y extrae todo el texto, página por página. No modifica PostgreSQL."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--salida",
            default="documentos_liturgicos_arquidiocesis",
            help="Carpeta destino para PDF, TXT, CSV y JSONL.",
        )
        parser.add_argument(
            "--solo-inventario",
            action="store_true",
            help="Recorre los listados y genera el CSV, sin descargar los PDF.",
        )
        parser.add_argument(
            "--desde",
            help="Fecha inicial YYYY-MM-DD; filtra publicaciones por fecha.",
        )
        parser.add_argument(
            "--hasta",
            help="Fecha final YYYY-MM-DD; filtra publicaciones por fecha.",
        )
        parser.add_argument(
            "--max-paginas",
            type=int,
            default=100,
            help="Máximo de páginas del archivo que se recorrerán (por defecto 100).",
        )
        parser.add_argument(
            "--pausa",
            type=float,
            default=0.5,
            help="Pausa entre solicitudes para no sobrecargar el sitio.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=40,
            help="Tiempo máximo de espera por solicitud en segundos.",
        )
        parser.add_argument(
            "--reintentos",
            type=int,
            default=3,
            help="Reintentos por descarga fallida.",
        )
        parser.add_argument(
            "--redescargar",
            action="store_true",
            help="Vuelve a descargar los PDF aunque ya existan localmente.",
        )
        parser.add_argument(
            "--sin-ocr",
            action="store_true",
            help="Desactiva el OCR automático de los PDF escaneados.",
        )
        parser.add_argument(
            "--ocr-idioma",
            default="spa",
            help="Idioma de Tesseract (por defecto: spa; admite spa+eng).",
        )
        parser.add_argument(
            "--ocr-dpi",
            type=int,
            default=300,
            help="Resolución de renderizado para OCR (150 a 600 DPI; por defecto 300).",
        )

    def handle(self, *args, **options):
        salida = Path(options["salida"]).expanduser().resolve()
        carpeta_pdf = salida / "pdf"
        carpeta_txt = salida / "texto_por_documento"
        carpeta_pdf.mkdir(parents=True, exist_ok=True)
        carpeta_txt.mkdir(parents=True, exist_ok=True)

        try:
            desde = date.fromisoformat(options["desde"]) if options["desde"] else None
            hasta = date.fromisoformat(options["hasta"]) if options["hasta"] else None
        except ValueError as exc:
            raise CommandError("Las fechas deben tener formato YYYY-MM-DD.") from exc

        if desde and hasta and desde > hasta:
            raise CommandError("--desde no puede ser posterior a --hasta.")
        if options["max_paginas"] < 1:
            raise CommandError("--max-paginas debe ser mayor que cero.")
        if options["pausa"] < 0 or options["reintentos"] < 0:
            raise CommandError("--pausa y --reintentos no pueden ser negativos.")
        if not 150 <= options["ocr_dpi"] <= 600:
            raise CommandError("--ocr-dpi debe estar entre 150 y 600.")

        tesseract = None
        if not options["sin_ocr"]:
            tesseract = _resolver_tesseract()
            if not tesseract:
                raise CommandError(
                    "No se encontró Tesseract OCR. Instálalo en Windows y "
                    "comprueba que 'tesseract --list-langs' muestre spa. "
                    "Para ejecutar sin OCR utiliza --sin-ocr."
                )
            idiomas_disponibles = _validar_tesseract(
                tesseract, options["ocr_idioma"]
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"OCR disponible: {tesseract}; idioma={options['ocr_idioma']}; "
                    f"DPI={options['ocr_dpi']}"
                )
            )
            self.stdout.write(
                f"Idiomas Tesseract instalados: {', '.join(idiomas_disponibles)}"
            )

        motor_pdf = None
        if not options["solo_inventario"]:
            motor_pdf = _detectar_motor_pdf()
            self.stdout.write(
                self.style.SUCCESS(f"Motor de extracción PDF disponible: {motor_pdf}")
            )

        self.stdout.write(self.style.NOTICE("Consultando el archivo de la Arquidiócesis..."))
        documentos = []
        urls_vistas = set()
        paginas_consultadas = 0

        for numero_pagina in range(1, options["max_paginas"] + 1):
            url_pagina = (
                URL_LISTADO
                if numero_pagina == 1
                else f"{URL_LISTADO}?pagina={numero_pagina}"
            )
            try:
                encontrados, _ = _leer_listado(
                    url_pagina, options["timeout"], options["reintentos"]
                )
            except Exception as exc:
                self.stderr.write(
                    self.style.WARNING(
                        f"No se pudo leer la página {numero_pagina}: {exc}"
                    )
                )
                break

            paginas_consultadas += 1
            nuevos = []
            for item in encontrados:
                if item["url_pdf"] not in urls_vistas:
                    urls_vistas.add(item["url_pdf"])
                    nuevos.append(item)

            self.stdout.write(
                f"Página {numero_pagina}: {len(encontrados)} publicaciones "
                f"({len(nuevos)} nuevas)"
            )
            if not nuevos:
                break

            documentos.extend(nuevos)
            if options["pausa"]:
                time.sleep(options["pausa"])

        if desde:
            documentos = [
                d for d in documentos if d["fecha"] and d["fecha"] >= desde
            ]
        if hasta:
            documentos = [
                d for d in documentos if d["fecha"] and d["fecha"] <= hasta
            ]

        if not documentos:
            raise CommandError(
                "No se encontraron publicaciones PDF. Revisa la conexión o el formato del listado."
            )

        inventario = []
        descargados = extraidos = extraidos_ocr = errores = paginas_total = 0
        ruta_csv = salida / "inventario_documentos.csv"
        ruta_jsonl = salida / "documentos_texto_completo.jsonl"

        def guardar_inventario():
            with ruta_csv.open("w", newline="", encoding="utf-8-sig") as archivo:
                escritor = csv.DictWriter(archivo, fieldnames=CAMPOS_CSV)
                escritor.writeheader()
                escritor.writerows(inventario)

        if not options["solo_inventario"]:
            # Cada documento procesado se agrega al JSONL de forma incremental.
            ruta_jsonl.write_text("", encoding="utf-8")

        self.stdout.write(
            self.style.NOTICE(
                f"Publicaciones detectadas: {len(documentos)}; "
                f"páginas del listado consultadas: {paginas_consultadas}."
            )
        )

        for indice, item in enumerate(documentos, start=1):
            url_pdf = item["url_pdf"]
            fecha_txt = item["fecha"].isoformat() if item["fecha"] else ""
            nombre_origen = Path(urlparse(url_pdf).path).name
            nombre_origen = _nombre_seguro(nombre_origen)
            prefijo_fecha = fecha_txt or "fecha-no-identificada"
            nombre_pdf = f"{prefijo_fecha}_{nombre_origen}"
            ruta_pdf = carpeta_pdf / nombre_pdf

            fila = {
                "fecha_publicacion": fecha_txt,
                "fecha_documento": fecha_txt,
                "origen_fecha": "LISTADO_WEB" if fecha_txt else "",
                "titulo_publicacion": item["titulo"],
                "titulo_celebracion": "",
                "ciclo": "",
                "ciclo_origen": "",
                "anio_liturgico": "",
                "liturgia_horas": "",
                "anio_liturgia_horas": "",
                "url_pdf": url_pdf,
                "archivo_pdf": str(ruta_pdf.relative_to(salida)),
                "paginas": 0,
                "caracteres_extraidos": 0,
                "metodo_extraccion": "",
                "sha256": "",
                "estado_descarga": "PENDIENTE",
                "estado_extraccion": "PENDIENTE",
                "observacion": "",
            }

            if options["solo_inventario"]:
                fila["estado_descarga"] = "NO_DESCARGADO_MODO_INVENTARIO"
                fila["estado_extraccion"] = "NO_EJECUTADA"
                inventario.append(fila)
                continue

            try:
                if ruta_pdf.is_file() and not options["redescargar"]:
                    fila["estado_descarga"] = "REUTILIZADO"
                else:
                    contenido, url_final, _ = _solicitar(
                        url_pdf, options["timeout"], options["reintentos"]
                    )
                    if not contenido.startswith(b"%PDF"):
                        raise ValueError(
                            "La respuesta no parece ser un PDF válido."
                        )
                    ruta_pdf.write_bytes(contenido)
                    fila["url_pdf"] = url_final
                    fila["estado_descarga"] = "DESCARGADO"
                    descargados += 1

                datos_hash = hashlib.sha256(ruta_pdf.read_bytes()).hexdigest()
                fila["sha256"] = datos_hash

                paginas, total_paginas, metadatos_pdf, motor = _extraer_pdf(ruta_pdf)
                metodo_extraccion = "TEXTO_PDF"
                observaciones_documento = []

                # Si el PDF tiene páginas-imagen y no posee capa de texto,
                # aplicamos OCR en español sin alterar el archivo original.
                caracteres_digitales = sum(len(texto.strip()) for texto in paginas)
                if (
                    caracteres_digitales < 120
                    and total_paginas > 0
                    and tesseract
                ):
                    try:
                        paginas_ocr = _ocr_pdf(
                            ruta_pdf,
                            tesseract,
                            idioma=options["ocr_idioma"],
                            dpi=options["ocr_dpi"],
                        )
                        if any(texto.strip() for texto in paginas_ocr):
                            paginas = paginas_ocr
                            metodo_extraccion = "OCR_TESSERACT"
                            motor = (
                                f"PyMuPDF + Tesseract "
                                f"({options['ocr_idioma']}, {options['ocr_dpi']} DPI)"
                            )
                            observaciones_documento.append(
                                "Texto recuperado mediante OCR automático; "
                                "revisar nombres, signos y referencias bíblicas."
                            )
                        else:
                            observaciones_documento.append(
                                "Se ejecutó OCR, pero no se reconoció texto."
                            )
                    except Exception as exc:
                        observaciones_documento.append(
                            f"Falló OCR: {type(exc).__name__}: {str(exc)[:300]}"
                        )

                texto_completo = "\n\n".join(
                    f"========== PÁGINA {numero} ==========\n{texto.strip()}"
                    for numero, texto in enumerate(paginas, start=1)
                ).strip()
                caracteres = sum(len(texto) for texto in paginas)
                fila["paginas"] = total_paginas
                fila["caracteres_extraidos"] = caracteres
                fila["metodo_extraccion"] = metodo_extraccion
                paginas_total += total_paginas

                texto_encabezado = "\n".join(paginas[:2])
                datos = _extraer_datos_liturgicos(
                    texto_encabezado,
                    fecha_listado=item["fecha"],
                )
                fila.update(datos)

                if datos.get("observacion_fecha"):
                    observaciones_documento.append(datos["observacion_fecha"])

                if caracteres:
                    if metodo_extraccion == "OCR_TESSERACT":
                        fila["estado_extraccion"] = "EXTRAIDO_OCR"
                        extraidos_ocr += 1
                    else:
                        fila["estado_extraccion"] = "EXTRAIDO"
                    extraidos += 1
                else:
                    fila["estado_extraccion"] = "SIN_TEXTO"
                    if total_paginas == 0:
                        observaciones_documento.append(
                            "PDF sin páginas válidas; requiere recuperar o reparar el archivo original."
                        )
                    elif options["sin_ocr"]:
                        observaciones_documento.append(
                            "PDF sin capa de texto; OCR desactivado."
                        )
                    if not observaciones_documento:
                        observaciones_documento.append(
                            "No se pudo extraer ni reconocer texto del PDF."
                        )

                fila["observacion"] = " ".join(observaciones_documento)

                nombre_txt = ruta_pdf.stem + ".txt"
                ruta_txt = carpeta_txt / nombre_txt
                ruta_txt.write_text(texto_completo, encoding="utf-8")

                registro_json = {
                    "fecha_publicacion": fecha_txt or None,
                    "titulo_publicacion": item["titulo"],
                    "url_pdf": fila["url_pdf"],
                    "archivo_pdf": fila["archivo_pdf"],
                    "sha256": datos_hash,
                    "paginas": [
                        {"pagina": n, "texto": texto}
                        for n, texto in enumerate(paginas, start=1)
                    ],
                    "texto_completo": texto_completo,
                    "datos_encabezado": datos,
                    "metadatos_pdf": {
                        str(k): _texto_metadato(v)
                        for k, v in dict(metadatos_pdf or {}).items()
                    },
                    "motor_extraccion": motor,
                    "metodo_extraccion": metodo_extraccion,
                    "estado_extraccion": fila["estado_extraccion"],
                }
                with ruta_jsonl.open("a", encoding="utf-8") as archivo_jsonl:
                    archivo_jsonl.write(
                        json.dumps(registro_json, ensure_ascii=False) + "\n"
                    )

            except Exception as exc:
                fila["estado_descarga"] = (
                    fila["estado_descarga"]
                    if fila["estado_descarga"] != "PENDIENTE"
                    else "ERROR"
                )
                fila["estado_extraccion"] = "ERROR"
                fila["observacion"] = f"{type(exc).__name__}: {str(exc)[:400]}"
                errores += 1

            inventario.append(fila)
            if not options["solo_inventario"]:
                detalle_error = (
                    f" | {fila['observacion']}" if fila["estado_extraccion"] == "ERROR"
                    and fila["observacion"] else ""
                )
                self.stdout.write(
                    f"[{indice}/{len(documentos)}] {fecha_txt or 'SIN FECHA'} "
                    f"{fila['estado_descarga']} / {fila['estado_extraccion']} "
                    f"({fila['paginas']} páginas, {fila['caracteres_extraidos']} caracteres)"
                    f"{detalle_error}"
                )
                # Guarda el avance en disco tras cada documento; Ctrl+C no
                # elimina el inventario de los anteriores.
                guardar_inventario()
                if indice < len(documentos) and options["pausa"]:
                    time.sleep(options["pausa"])

        guardar_inventario()

        ruta_resumen = salida / "LEEME.txt"
        lineas = [
            "EXTRACCIÓN DOCUMENTAL - DOMINGO DÍA DEL SEÑOR",
            f"Fuente: {URL_LISTADO}",
            f"Páginas del listado consultadas: {paginas_consultadas}",
            f"Publicaciones inventariadas: {len(inventario)}",
            f"PDF descargados en esta ejecución: {descargados}",
            f"Documentos con texto extraído en esta ejecución: {extraidos}",
            f"Documentos recuperados mediante OCR: {extraidos_ocr}",
            f"Errores: {errores}",
            f"Páginas PDF procesadas: {paginas_total}",
            "",
            "Archivos:",
            "- inventario_documentos.csv: fechas, títulos, URLs, ciclo y estado.",
            "- pdf/: archivos PDF originales descargados.",
            "- texto_por_documento/: texto completo separado por documento y página.",
            "- documentos_texto_completo.jsonl: corpus completo en formato JSON Lines.",
            "",
            "Los documentos EXTRAIDO_OCR contienen reconocimiento automático y requieren revisión.",
            "Los documentos SIN_TEXTO requieren revisar integridad del PDF o aplicar OCR manual.",
            "Este proceso no escribe ni modifica datos de PostgreSQL.",
        ]
        ruta_resumen.write_text("\n".join(lineas), encoding="utf-8")

        self.stdout.write("\n" + self.style.SUCCESS("Proceso terminado."))
        self.stdout.write(f"Carpeta de resultados: {salida}")
        self.stdout.write(f"Inventario: {ruta_csv}")
        if options["solo_inventario"]:
            self.stdout.write(
                "Modo inventario: no se descargaron PDF ni se extrajo su contenido."
            )
        else:
            self.stdout.write(
                f"Resumen: inventariados={len(inventario)}, descargados={descargados}, "
                f"extraídos={extraidos}, OCR={extraidos_ocr}, "
                f"errores={errores}, páginas_pdf={paginas_total}"
            )
        self.stdout.write(
            self.style.WARNING(
                "No se modificó PostgreSQL ni el calendario litúrgico existente."
            )
        )
