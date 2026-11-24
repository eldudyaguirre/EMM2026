import csv
import hashlib
import io
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


def _texto_pagina_por_columnas(pagina):
    """
    Extrae texto por bloques y respeta el orden de lectura de páginas a dos
    columnas. Los bloques que cruzan el centro (por ejemplo, bandas como
    'Liturgia de la Palabra') dividen la página en zonas; dentro de cada zona
    se lee primero la columna izquierda y después la derecha.
    """
    bloques = []
    try:
        bloques_pdf = pagina.get_text("blocks")
    except Exception:
        bloques_pdf = []

    ancho = float(pagina.rect.width)
    mitad = ancho / 2.0

    for bloque in bloques_pdf:
        if len(bloque) < 5:
            continue
        x0, y0, x1, y1, texto = bloque[:5]
        texto = (texto or "").strip()
        if not texto:
            continue
        item = {
            "x0": float(x0),
            "y0": float(y0),
            "x1": float(x1),
            "y1": float(y1),
            "texto": texto,
        }
        bloques.append(item)

    if not bloques:
        return pagina.get_text("text", sort=True) or ""

    izquierda = [
        b for b in bloques
        if (b["x0"] + b["x1"]) / 2 < mitad
        and not (b["x0"] < mitad - 8 and b["x1"] > mitad + 8)
    ]
    derecha = [
        b for b in bloques
        if (b["x0"] + b["x1"]) / 2 >= mitad
        and not (b["x0"] < mitad - 8 and b["x1"] > mitad + 8)
    ]
    transversales = [
        b for b in bloques
        if b["x0"] < mitad - 8 and b["x1"] > mitad + 8
    ]

    # En varios misales la página está organizada por bandas: los ritos
    # iniciales aparecen arriba a la derecha, mientras que las lecturas
    # comienzan después de la banda "Liturgia de la Palabra". Al concatenar
    # toda la columna derecha se mezclaban los ritos con el salmo.
    marcador_palabra = re.compile(
        r"LITURGIA\s+DE\s+LA\s+PALAB",
        re.IGNORECASE,
    )
    bandas_palabra = [
        b["y1"] for b in bloques
        if marcador_palabra.search(
            unicodedata.normalize("NFD", b["texto"])
            .encode("ascii", "ignore")
            .decode("ascii")
            .upper()
        )
    ]
    if bandas_palabra:
        limite_lecturas = max(bandas_palabra)
        derecha = [
            b for b in derecha
            if b["y0"] >= limite_lecturas - 2
        ]
        transversales = [
            b for b in transversales
            if b["y0"] >= limite_lecturas - 2
            or marcador_palabra.search(
                unicodedata.normalize("NFD", b["texto"])
                .encode("ascii", "ignore")
                .decode("ascii")
                .upper()
            )
        ]

    caracteres_izquierda = sum(len(b["texto"]) for b in izquierda)
    caracteres_derecha = sum(len(b["texto"]) for b in derecha)

    # No forzar dos columnas en páginas de una sola columna o con texto centrado.
    if (
        len(izquierda) < 2
        or len(derecha) < 2
        or caracteres_izquierda < 100
        or caracteres_derecha < 100
    ):
        return pagina.get_text("text", sort=True) or ""

    def ordenar_columna(items):
        return sorted(items, key=lambda b: (b["y0"], b["x0"]))

    salida = []
    limite_superior = float("-inf")
    for transversal in sorted(transversales, key=lambda b: (b["y0"], b["x0"])):
        zona_izquierda = [
            b for b in izquierda
            if limite_superior <= b["y0"] < transversal["y0"]
        ]
        zona_derecha = [
            b for b in derecha
            if limite_superior <= b["y0"] < transversal["y0"]
        ]
        salida.extend(b["texto"] for b in ordenar_columna(zona_izquierda))
        salida.extend(b["texto"] for b in ordenar_columna(zona_derecha))
        salida.append(transversal["texto"])
        limite_superior = max(limite_superior, transversal["y1"])

    restantes_izquierda = [
        b for b in izquierda if b["y0"] >= limite_superior
    ]
    restantes_derecha = [
        b for b in derecha if b["y0"] >= limite_superior
    ]
    salida.extend(b["texto"] for b in ordenar_columna(restantes_izquierda))
    salida.extend(b["texto"] for b in ordenar_columna(restantes_derecha))

    texto_ordenado = "\n".join(salida).strip()
    texto_original = pagina.get_text("text", sort=True) or ""
    # Si una peculiaridad de la geometría descartara demasiada información,
    # conservar la extracción estándar.
    if len(texto_ordenado) < len(texto_original) * 0.75:
        return texto_original
    return texto_ordenado


def _extraer_pdf(ruta_pdf):
    """Extrae texto digital por página y metadatos del PDF."""
    try:
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf

        with pymupdf.open(str(ruta_pdf)) as documento:
            paginas = [
                _texto_pagina_por_columnas(pagina)
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


def _densidad_tinta(imagen, caja):
    """
    Calcula la proporción de píxeles oscuros en una zona de la página.
    Se usa solo para distinguir páginas escaneadas a dos columnas.
    """
    try:
        from PIL import Image
        zona = imagen.crop(caja).convert("L")
        histograma = zona.histogram()
        pixeles_oscuros = sum(histograma[:220])
        total = max(1, zona.width * zona.height)
        return pixeles_oscuros / total
    except Exception:
        return 0.0


def _es_dos_columnas(imagen):
    """
    Detecta dos columnas con un canal central relativamente despejado.
    No depende de que el PDF tenga capa de texto digital.
    """
    ancho, alto = imagen.size
    y0, y1 = int(alto * 0.20), int(alto * 0.92)
    zonas = {
        "izquierda": (int(ancho * 0.08), y0, int(ancho * 0.45), y1),
        "canal": (int(ancho * 0.47), y0, int(ancho * 0.53), y1),
        "derecha": (int(ancho * 0.55), y0, int(ancho * 0.92), y1),
    }
    densidad_izquierda = _densidad_tinta(imagen, zonas["izquierda"])
    densidad_canal = _densidad_tinta(imagen, zonas["canal"])
    densidad_derecha = _densidad_tinta(imagen, zonas["derecha"])

    if min(densidad_izquierda, densidad_derecha) < 0.08:
        return False
    return densidad_canal / max(
        0.001,
        min(densidad_izquierda, densidad_derecha),
    ) < 0.72


def _tesseract(imagen, ejecutable, idioma="spa", psm="4", salida="text"):
    comando = [
        ejecutable,
        str(imagen),
        "stdout",
        "-l",
        idioma,
        "--oem",
        "1",
        "--psm",
        str(psm),
    ]
    if salida == "tsv":
        comando.append("tsv")
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
        raise RuntimeError(f"Tesseract falló: {detalle[:500]}")
    return resultado.stdout or ""


def _limite_banda_liturgia(archivo_imagen, ejecutable, idioma):
    """
    Localiza con TSV la banda "Liturgia de la Palabra" en la columna izquierda.
    Devuelve la coordenada inferior en píxeles o None si no se reconoce.
    """
    try:
        resultado = _tesseract(
            archivo_imagen,
            ejecutable,
            idioma=idioma,
            psm="4",
            salida="tsv",
        )
        lector = csv.DictReader(io.StringIO(resultado), delimiter="\t")
        lineas = {}
        for fila in lector:
            if fila.get("level") != "5":
                continue
            texto = (fila.get("text") or "").strip()
            if not texto:
                continue
            clave = (
                fila.get("block_num"),
                fila.get("par_num"),
                fila.get("line_num"),
            )
            lineas.setdefault(clave, []).append(fila)

        for palabras in lineas.values():
            texto_linea = " ".join(
                palabra.get("text", "") for palabra in palabras
            )
            normalizado = (
                unicodedata.normalize("NFD", texto_linea)
                .encode("ascii", "ignore")
                .decode("ascii")
                .upper()
            )
            if re.search(r"LITURGIA\s+DE\s+LA\s+PALAB", normalizado):
                return max(
                    int(palabra.get("top", 0))
                    + int(palabra.get("height", 0))
                    for palabra in palabras
                )
    except Exception:
        return None
    return None


def _ocr_pdf(
    ruta_pdf,
    ejecutable,
    idioma="spa",
    dpi=300,
    indices_paginas=None,
):
    """
    Reconoce todas las páginas o solo las páginas indicadas (índice base cero).

    Si la página escaneada tiene dos columnas, las procesa por separado. En
    páginas con el rótulo "Liturgia de la Palabra", recorta el inicio superior
    de la columna derecha para no mezclar los ritos iniciales con las lecturas.
    El PDF original nunca se modifica.

    Devuelve (textos_por_pagina, numeros_de_pagina_ocr_por_columnas).
    """
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf

    try:
        from PIL import Image
    except ImportError:
        Image = None

    escala = dpi / 72.0
    textos = []
    paginas_dos_columnas = []
    textos_encabezado_completo = {}
    seleccion = (
        None
        if indices_paginas is None
        else {int(indice) for indice in indices_paginas}
    )

    with tempfile.TemporaryDirectory(prefix="emaus_ocr_") as temporal:
        carpeta_temporal = Path(temporal)
        with pymupdf.open(str(ruta_pdf)) as documento:
            for indice, pagina in enumerate(documento):
                if seleccion is not None and indice not in seleccion:
                    continue

                numero_pagina = indice + 1
                pixmap = pagina.get_pixmap(
                    matrix=pymupdf.Matrix(escala, escala),
                    colorspace=pymupdf.csRGB,
                    alpha=False,
                )
                imagen = carpeta_temporal / f"pagina_{numero_pagina:04d}.png"
                pixmap.save(str(imagen))

                if Image is None:
                    texto = _tesseract(
                        imagen,
                        ejecutable,
                        idioma=idioma,
                        psm="3",
                    ).strip()
                    textos.append(texto)
                    continue

                with Image.open(imagen) as imagen_pagina:
                    imagen_pagina = imagen_pagina.convert("RGB")
                    if not _es_dos_columnas(imagen_pagina):
                        texto = _tesseract(
                            imagen,
                            ejecutable,
                            idioma=idioma,
                            psm="3",
                        ).strip()
                        textos.append(texto)
                        continue

                    ancho, alto = imagen_pagina.size
                    corte_izquierdo = int(ancho * 0.505)
                    inicio_derecho = int(ancho * 0.495)

                    imagen_izquierda = carpeta_temporal / (
                        f"pagina_{numero_pagina:04d}_izquierda.png"
                    )
                    imagen_derecha = carpeta_temporal / (
                        f"pagina_{numero_pagina:04d}_derecha.png"
                    )

                    imagen_pagina.crop(
                        (0, 0, corte_izquierdo, alto)
                    ).save(imagen_izquierda)

                    limite_banda = _limite_banda_liturgia(
                        imagen_izquierda,
                        ejecutable,
                        idioma,
                    )

                    inicio_vertical_derecha = 0
                    if limite_banda is not None:
                        # Deja un pequeño solapamiento bajo la banda para no
                        # cortar la primera línea del salmo o de la lectura.
                        inicio_vertical_derecha = max(
                            0,
                            limite_banda - int(alto * 0.004),
                        )

                    imagen_pagina.crop(
                        (
                            inicio_derecho,
                            inicio_vertical_derecha,
                            ancho,
                            alto,
                        )
                    ).save(imagen_derecha)

                    # Mantener una lectura de página completa solo para
                    # reconocer el encabezado, la celebración y la fecha.
                    # El texto usado para las secciones sigue siendo el OCR por
                    # columnas, que evita mezclar Ritos Iniciales y lecturas.
                    textos_encabezado_completo[numero_pagina] = _tesseract(
                        imagen,
                        ejecutable,
                        idioma=idioma,
                        psm="3",
                    ).strip()

                    texto_izquierda = _tesseract(
                        imagen_izquierda,
                        ejecutable,
                        idioma=idioma,
                        psm="4",
                    ).strip()
                    texto_derecha = _tesseract(
                        imagen_derecha,
                        ejecutable,
                        idioma=idioma,
                        psm="4",
                    ).strip()

                    texto = "\n\n".join(
                        parte for parte in (texto_izquierda, texto_derecha)
                        if parte
                    )
                    textos.append(texto)
                    paginas_dos_columnas.append(numero_pagina)

    return textos, paginas_dos_columnas, textos_encabezado_completo


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
    Detecta únicamente fechas impresas en el encabezado litúrgico.
    No acepta fechas citadas en mensajes, colectas o artículos editoriales.
    Cuando la fecha no es inequívoca devuelve None y se conserva el listado web.
    """
    meses = (
        "enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
        "septiembre|setiembre|octubre|noviembre|diciembre"
    )
    patron_mes = re.compile(
        rf"\b(\d{{1,2}})\s+de\s+({meses})\s+(?:(?:de|del)\s*)?(20\d{{2}})\b",
        re.IGNORECASE,
    )
    patron_mes_sin_de = re.compile(
        rf"\b(\d{{1,2}})\s+({meses})\s+(20\d{{2}})\b",
        re.IGNORECASE,
    )
    patron_numerico = re.compile(
        r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b"
    )
    pista_liturgica = re.compile(
        r"\bDOMINGO\b|\bSOLEMNIDAD\b|\bFIESTA\b|\bPASCUA\b|"
        r"\bADVIENTO\b|\bCUARESMA\b|\bNAVIDAD\b|\bCICLO\s+[ABC]\b|"
        r"\bCRISTO\s+REY\b|\bBAUTISMO\s+DEL\s+SEÑOR\b|"
        r"\bBAUTISMO\s+DEL\s+SENOR\b|\bPENTECOST[EÉ]S\b|"
        r"\bASCENSI[ÓO]N\b|\bCORPUS\s+CHRISTI\b|\bSAGRADA\s+FAMILIA\b|"
        r"\bEPIFAN[IÍ]A\b",
        re.IGNORECASE,
    )
    pistas_editoriales = re.compile(
        r"\bCOLECTA\b|\bMENSAJE\b|\bPAPA\b|\bFRANCISCO\b|"
        r"\bS\.?\s*S\.?\b|\bCITA\b|\bHOMIL[IÍ]A\b|"
        r"\bVOZ\s+DEL\s+PASTOR\b",
        re.IGNORECASE,
    )

    lineas = [
        _normalizar_busqueda(linea).upper()
        for linea in (texto or "").splitlines()
        if linea.strip()
    ][:24]

    if not lineas:
        return None

    # Primero se buscan fechas con nombre de mes. El contexto está limitado
    # a dos líneas antes/después; nunca se concatena toda la página, para no
    # asociar una fecha de una cita editorial con el título litúrgico.
    for indice, linea in enumerate(lineas):
        if pistas_editoriales.search(linea):
            continue

        contexto = " ".join(
            lineas[max(0, indice - 2):min(len(lineas), indice + 3)]
        )
        if not pista_liturgica.search(contexto):
            continue

        for patron in (patron_mes, patron_mes_sin_de):
            coincidencia = patron.search(linea)
            if not coincidencia:
                continue
            try:
                fecha = date(
                    int(coincidencia.group(3)),
                    MESES[coincidencia.group(2).lower()],
                    int(coincidencia.group(1)),
                )
            except (ValueError, KeyError):
                continue

            # El día y mes deben aparecer literalmente en una línea del
            # encabezado; solo se usa el contexto adyacente para confirmar
            # que esa línea corresponde a una celebración litúrgica.
            return fecha

    # Fechas numéricas: solo se aceptan si la propia línea contiene también
    # un marcador de celebración. Así no se confunden citas como 24-11-2013
    # con la fecha del misal.
    for linea in lineas[:12]:
        if pistas_editoriales.search(linea) or not pista_liturgica.search(linea):
            continue
        coincidencia = patron_numerico.search(linea)
        if not coincidencia:
            continue
        try:
            return date(
                int(coincidencia.group(3)),
                int(coincidencia.group(2)),
                int(coincidencia.group(1)),
            )
        except ValueError:
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
                paginas_ocr_encabezado = {}

                # OCR por página: algunos PDF mezclan páginas editoriales con
                # texto digital y páginas de celebración que son solo imágenes.
                # Se aplica OCR únicamente a las páginas con menos de 120
                # caracteres, conservando la capa digital de las demás.
                paginas_texto_digital = list(paginas)
                indices_paginas_ocr = [
                    indice
                    for indice, texto_pagina in enumerate(paginas_texto_digital)
                    if len((texto_pagina or "").strip()) < 120
                ]
                if indices_paginas_ocr and total_paginas > 0 and tesseract:
                    try:
                        (
                            paginas_ocr,
                            paginas_ocr_columnas,
                            paginas_ocr_encabezado,
                        ) = _ocr_pdf(
                            ruta_pdf,
                            tesseract,
                            idioma=options["ocr_idioma"],
                            dpi=options["ocr_dpi"],
                            indices_paginas=indices_paginas_ocr,
                        )
                        paginas_recuperadas = []
                        for indice_pagina, texto_ocr in zip(
                            indices_paginas_ocr, paginas_ocr
                        ):
                            texto_ocr = (texto_ocr or "").strip()
                            texto_digital = (paginas[indice_pagina] or "").strip()

                            # Sustituir el texto escaso solo cuando el OCR aporta
                            # una recuperación claramente más completa.
                            if len(texto_ocr) > max(40, len(texto_digital) + 20):
                                paginas[indice_pagina] = texto_ocr
                                paginas_recuperadas.append(indice_pagina + 1)

                        if paginas_recuperadas:
                            hay_texto_digital = any(
                                len((texto_pagina or "").strip()) >= 120
                                for texto_pagina in paginas_texto_digital
                            )
                            metodo_extraccion = (
                                "TEXTO_PDF+OCR_TESSERACT"
                                if hay_texto_digital
                                else "OCR_TESSERACT"
                            )
                            motor = (
                                f"PyMuPDF + Tesseract "
                                f"({options['ocr_idioma']}, {options['ocr_dpi']} DPI)"
                            )
                            observaciones_documento.append(
                                "OCR aplicado a las páginas: "
                                + ", ".join(str(n) for n in paginas_recuperadas)
                                + ". Revisar nombres, signos y referencias bíblicas."
                            )
                            columnas_recuperadas = [
                                n for n in paginas_dos_columnas
                                if n in paginas_recuperadas
                            ]
                            if columnas_recuperadas:
                                observaciones_documento.append(
                                    "OCR por columnas separadas en las páginas: "
                                    + ", ".join(str(n) for n in columnas_recuperadas)
                                    + ". Se separaron las bandas de Ritos Iniciales y Liturgia de la Palabra cuando fue posible."
                                )
                        else:
                            observaciones_documento.append(
                                "Se ejecutó OCR en páginas con poco texto digital, "
                                "pero no se obtuvo una recuperación suficiente."
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

                paginas_para_encabezado = list(paginas)
                if "paginas_ocr_encabezado" in locals():
                    for numero_pagina, texto_pagina in paginas_ocr_encabezado.items():
                        if 1 <= numero_pagina <= 2:
                            paginas_para_encabezado[numero_pagina - 1] = texto_pagina
                texto_encabezado = "\n".join(paginas_para_encabezado[:2])
                datos = _extraer_datos_liturgicos(
                    texto_encabezado,
                    fecha_listado=item["fecha"],
                )
                fila.update(datos)

                if datos.get("observacion_fecha"):
                    observaciones_documento.append(datos["observacion_fecha"])

                if caracteres:
                    if "OCR_TESSERACT" in metodo_extraccion:
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
