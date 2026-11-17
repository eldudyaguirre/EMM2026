from html.parser import HTMLParser
from datetime import date
import re
import unicodedata

SECTIONS = {
    "PRIMERA LECTURA": "primera_lectura",
    "SALMO": "salmo",
    "SALMO RESPONSORIAL": "salmo",
    "SEGUNDA LECTURA": "segunda_lectura",
    "ACLAMACION": "aclamacion",
    "ACLAMACION ANTES DEL EVANGELIO": "aclamacion",
    "EVANGELIO": "evangelio",
}


def _normalizar(texto):
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"\s+", " ", texto).strip().upper()
    return texto.rstrip(":")


class _MisalParser(HTMLParser):
    """Extrae párrafos del bloque .entry-content del artículo de Misal.mx."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.entry_depth = 0
        self.current_p = None
        self.paragraphs = []
        self.source_date = None
        self.current_time_parts = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            prop = (attrs.get("property") or attrs.get("name") or "").lower()
            if prop in {"article:published_time", "date", "publishdate"}:
                self._set_date(attrs.get("content", ""))

        if tag == "time":
            self._set_date(attrs.get("datetime", ""))
            self.current_time_parts = []

        if tag == "div":
            classes = (attrs.get("class") or "").split()
            if self.entry_depth == 0 and "entry-content" in classes:
                self.entry_depth = 1
            elif self.entry_depth > 0:
                self.entry_depth += 1

        if self.entry_depth > 0 and tag == "p":
            self.current_p = {
                "classes": (attrs.get("class") or "").split(),
                "parts": [],
            }

        if self.current_p is not None and tag in {"br", "hr"}:
            self.current_p["parts"].append("\n")

    def handle_endtag(self, tag):
        if tag == "p" and self.current_p is not None:
            texto = "".join(self.current_p["parts"])
            texto = re.sub(r"[ \t\xa0]+", " ", texto)
            texto = re.sub(r" *\n *", "\n", texto).strip()
            self.paragraphs.append((texto, self.current_p["classes"]))
            self.current_p = None

        if tag == "time" and self.current_time_parts is not None:
            if not self.source_date:
                self._set_date("".join(self.current_time_parts))
            self.current_time_parts = None

        if tag == "div" and self.entry_depth > 0:
            self.entry_depth -= 1

    def handle_data(self, data):
        if self.current_p is not None:
            self.current_p["parts"].append(data)
        if self.current_time_parts is not None:
            self.current_time_parts.append(data)

    def _set_date(self, value):
        if self.source_date or not value:
            return
        match = re.search(r"(20\d{2}-\d{2}-\d{2})", value)
        if match:
            try:
                self.source_date = date.fromisoformat(match.group(1))
                return
            except ValueError:
                pass
        match = re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})", value)
        if match:
            try:
                self.source_date = date(
                    int(match.group(3)), int(match.group(2)), int(match.group(1))
                )
            except ValueError:
                pass


def extraer_secciones(html):
    """Devuelve los cinco apartados de lecturas y la fecha de publicación detectada.

    La segunda lectura se permite vacía porque no aparece en todas las celebraciones.
    No completa, corrige ni inventa texto que no exista en la página.
    """
    parser = _MisalParser()
    parser.feed(html)
    parser.close()

    secciones = {
        "primera_lectura": [],
        "salmo": [],
        "segunda_lectura": [],
        "aclamacion": [],
        "evangelio": [],
    }
    actual = None
    encabezados_de_cierre = (
        "ANTIFONA DE ENTRADA",
        "ORACION COLECTA",
        "ORACION SOBRE LAS OFRENDAS",
        "ANTIFONA DE LA COMUNION",
        "ORACION DESPUES DE LA COMUNION",
    )

    for texto, clases in parser.paragraphs:
        if not texto:
            continue

        normalizado = _normalizar(texto)
        tiene_estilo_titulo = "has-medium-font-size" in clases

        if actual == "evangelio" and normalizado.startswith("EVANGELIO (PASION"):
            secciones[actual].append(texto)
            continue

        if normalizado in SECTIONS:
            actual = SECTIONS[normalizado]
            continue

        if any(normalizado.startswith(x) for x in encabezados_de_cierre):
            actual = None
            continue

        if tiene_estilo_titulo:
            actual = None
            continue

        if actual:
            if texto.startswith("Ayúdanos para seguir manteniendo este sitio"):
                continue
            if set(texto.replace(" ", "")) <= {"—", "-", "–"}:
                continue
            secciones[actual].append(texto)

    resultado = {campo: "\n".join(parrafos).strip() for campo, parrafos in secciones.items()}
    return resultado, parser.source_date
