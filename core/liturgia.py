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


class _NodoHTML:
    """Nodo sencillo para recorrer la estructura de lecturas de MISAL Mx."""

    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []
        self.parent = None

    def texto(self):
        partes = []
        for hijo in self.children:
            partes.append(hijo.texto() if isinstance(hijo, _NodoHTML) else hijo)
        return re.sub(r"\s+", " ", " ".join(partes)).strip()


class _ArbolMisalParser(HTMLParser):
    """Construye un árbol HTML mínimo sin dependencias externas."""

    VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _NodoHTML("document", [])
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        nodo = _NodoHTML(tag, attrs)
        nodo.parent = self.stack[-1]
        self.stack[-1].children.append(nodo)
        if tag not in self.VOID_TAGS:
            self.stack.append(nodo)

    def handle_startendtag(self, tag, attrs):
        nodo = _NodoHTML(tag, attrs)
        nodo.parent = self.stack[-1]
        self.stack[-1].children.append(nodo)

    def handle_endtag(self, tag):
        for indice in range(len(self.stack) - 1, 0, -1):
            if self.stack[indice].tag == tag:
                self.stack = self.stack[:indice]
                break

    def handle_data(self, data):
        if data:
            self.stack[-1].children.append(data)


def _buscar_nodo(nodo, condicion):
    if not isinstance(nodo, _NodoHTML):
        return None
    if condicion(nodo):
        return nodo
    for hijo in nodo.children:
        encontrado = _buscar_nodo(hijo, condicion)
        if encontrado is not None:
            return encontrado
    return None


def _descendientes(nodo):
    for hijo in nodo.children:
        if isinstance(hijo, _NodoHTML):
            yield hijo
            yield from _descendientes(hijo)


def _clases(nodo):
    return set((nodo.attrs.get("class") or "").split())


def _extraer_contenido_lectura(bloque):
    """Extrae encabezado/referencia, bloques de lectura y respuesta litúrgica.

    Se detiene antes de los apartados editoriales posteriores, como Homilía.
    """
    contenido = _buscar_nodo(
        bloque,
        lambda n: n.tag == "div" and "font-serif" in _clases(n),
    )
    if contenido is None:
        return ""

    partes = []
    for hijo in contenido.children:
        if not isinstance(hijo, _NodoHTML):
            continue

        clases = _clases(hijo)

        # La sección editorial posterior a la lectura comienza normalmente
        # en un bloque pt-3 (por ejemplo, "Homilía").
        if "pt-3" in clases:
            break

        # Título propio de la lectura y referencia bíblica.
        if "space-y-1.5" in clases:
            texto = hijo.texto()
            if texto:
                partes.append(texto)
            continue

        # Párrafos o versículos de la lectura. Cada botón representa
        # un fragmento independiente del texto bíblico.
        if hijo.tag == "button" and "missal-read-block" in clases:
            texto = hijo.texto()
            if texto:
                partes.append(texto)
            continue

        # Cierre litúrgico: "Palabra del Señor" y respuesta.
        if "space-y-2" in clases:
            texto = hijo.texto()
            if texto:
                partes.append(texto)
            break

    # Fallback conservador para pequeñas variaciones de marcado:
    # nunca incluir contenido posterior a la etiqueta "Homilía".
    if not partes:
        texto = contenido.texto()
        corte = re.search(r"\bHomil[ií]a\b", texto, flags=re.IGNORECASE)
        if corte:
            texto = texto[:corte.start()].strip()
        return texto

    return "\n".join(partes).strip()


def _extraer_secciones_misalmx(html):
    """Parser del sitio nuevo misalmx.com, cuya estructura usa details#lecturas."""
    parser = _ArbolMisalParser()
    parser.feed(html)
    parser.close()

    lecturas = _buscar_nodo(
        parser.root,
        lambda n: n.tag == "details" and n.attrs.get("id") == "lecturas",
    )
    if lecturas is None:
        return None

    # El contenedor .space-y-4 cuyas ramas directas contienen los h3
    # identificados como lectura-N es el listado de lecturas del día.
    contenedor = _buscar_nodo(
        lecturas,
        lambda n: (
            n.tag == "div"
            and "space-y-4" in _clases(n)
            and any(
                _buscar_nodo(
                    hijo,
                    lambda x: x.tag == "h3"
                    and (x.attrs.get("id") or "").startswith("lectura-"),
                )
                for hijo in n.children
                if isinstance(hijo, _NodoHTML)
            )
        ),
    )
    if contenedor is None:
        return None

    secciones = {
        "primera_lectura": [],
        "salmo": [],
        "segunda_lectura": [],
        "aclamacion": [],
        "evangelio": [],
    }

    for bloque in contenedor.children:
        if not isinstance(bloque, _NodoHTML):
            continue

        encabezado = _buscar_nodo(
            bloque,
            lambda n: n.tag == "h3"
            and (n.attrs.get("id") or "").startswith("lectura-"),
        )
        if encabezado is None:
            continue

        titulo = _normalizar(encabezado.texto())
        campo = SECTIONS.get(titulo)
        if not campo:
            # Los esquemas especiales (por ejemplo, lecturas numeradas de
            # la Vigilia Pascual) no se asignan a un campo ordinario a ciegas.
            continue

        texto = _extraer_contenido_lectura(bloque)
        if texto:
            secciones[campo].append(texto)

    resultado = {
        campo: "\n\n".join(fragmentos).strip()
        for campo, fragmentos in secciones.items()
    }
    return resultado, None


def extraer_secciones(html):
    """Devuelve los cinco apartados y la fecha de publicación detectada.

    Reconoce tanto la estructura antigua de Misal.mx como la nueva de
    misalmx.com. No completa ni inventa textos ausentes.
    """
    resultado_nuevo = _extraer_secciones_misalmx(html)
    if resultado_nuevo is not None:
        return resultado_nuevo

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

    resultado = {
        campo: "\n".join(parrafos).strip()
        for campo, parrafos in secciones.items()
    }
    return resultado, parser.source_date
