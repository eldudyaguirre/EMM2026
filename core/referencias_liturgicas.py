"""Extracción de referencias bíblicas (sin texto bíblico) desde Misal.mx."""
import re
import unicodedata
from datetime import date
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.request import Request, urlopen


SECCIONES = (
    ('primera_lectura_ref', 'PRIMERA LECTURA'),
    ('salmo_ref', 'SALMO'),
    ('segunda_lectura_ref', 'SEGUNDA LECTURA'),
    ('aclamacion_ref', 'ACLAMACIÓN'),
    ('evangelio_ref', 'EVANGELIO'),
)
FINES = [titulo for _, titulo in SECCIONES] + [
    'ORACIÓN SOBRE LAS OFRENDAS',
    'ANTÍFONA DE LA COMUNIÓN',
    'ORACIÓN DESPUÉS DE LA COMUNIÓN',
    'ORACIÓN DESPÚES DE LA COMUNIÓN',
]

# Se buscan primero las expresiones más específicas para evitar confundir
# "segunda carta" con una carta sin numeración.
ALIAS_LIBROS = (
    ('segunda carta del apostol san pablo a los corintios', '2 Corintios'),
    ('primera carta del apostol san pablo a los corintios', '1 Corintios'),
    ('segunda carta del apostol san pablo a los tesalonicenses', '2 Tesalonicenses'),
    ('primera carta del apostol san pablo a los tesalonicenses', '1 Tesalonicenses'),
    ('segunda carta del apostol san pablo a timoteo', '2 Timoteo'),
    ('primera carta del apostol san pablo a timoteo', '1 Timoteo'),
    ('segunda carta del apostol san pedro', '2 Pedro'),
    ('primera carta del apostol san pedro', '1 Pedro'),
    ('segunda carta del apostol san juan', '2 Juan'),
    ('primera carta del apostol san juan', '1 Juan'),
    ('tercera carta del apostol san juan', '3 Juan'),
    ('carta del apostol san pablo a los romanos', 'Romanos'),
    ('carta del apostol san pablo a los galatas', 'Gálatas'),
    ('carta del apostol san pablo a los efesios', 'Efesios'),
    ('carta del apostol san pablo a los filipenses', 'Filipenses'),
    ('carta del apostol san pablo a los colosenses', 'Colosenses'),
    ('carta del apostol san pablo a filemon', 'Filemón'),
    ('carta del apostol san pablo a los hebreos', 'Hebreos'),
    ('carta a los hebreos', 'Hebreos'),
    ('carta del apostol santiago', 'Santiago'),
    ('carta de santiago', 'Santiago'),
    ('carta del apostol san judas', 'Judas'),
    ('carta de san judas', 'Judas'),
    ('libro de los hechos de los apostoles', 'Hechos'),
    ('hechos de los apostoles', 'Hechos'),
    ('libro del apocalipsis', 'Apocalipsis'),
    ('apocalipsis', 'Apocalipsis'),
    ('evangelio segun san mateo', 'Mateo'),
    ('segun san mateo', 'Mateo'),
    ('san mateo', 'Mateo'),
    ('evangelio segun san marcos', 'Marcos'),
    ('segun san marcos', 'Marcos'),
    ('san marcos', 'Marcos'),
    ('evangelio segun san lucas', 'Lucas'),
    ('segun san lucas', 'Lucas'),
    ('san lucas', 'Lucas'),
    ('evangelio segun san juan', 'Juan'),
    ('segun san juan', 'Juan'),
    ('san juan', 'Juan'),
    ('profeta isaias', 'Isaías'),
    ('profeta jeremias', 'Jeremías'),
    ('profeta ezequiel', 'Ezequiel'),
    ('profeta daniel', 'Daniel'),
    ('profeta oseas', 'Oseas'),
    ('profeta joel', 'Joel'),
    ('profeta amos', 'Amós'),
    ('profeta abdias', 'Abdías'),
    ('profeta jonas', 'Jonás'),
    ('profeta miqueas', 'Miqueas'),
    ('profeta nahum', 'Nahúm'),
    ('profeta habacuc', 'Habacuc'),
    ('profeta sofonias', 'Sofonías'),
    ('profeta ageo', 'Ageo'),
    ('profeta zacarias', 'Zacarías'),
    ('profeta malaquias', 'Malaquías'),
    ('libro del genesis', 'Génesis'),
    ('libro del exodo', 'Éxodo'),
    ('libro del levitico', 'Levítico'),
    ('libro de los numeros', 'Números'),
    ('libro del deuteronomio', 'Deuteronomio'),
    ('libro de josue', 'Josué'),
    ('libro de los jueces', 'Jueces'),
    ('libro de rut', 'Rut'),
    ('segundo libro de samuel', '2 Samuel'),
    ('primer libro de samuel', '1 Samuel'),
    ('libro de samuel', '1 Samuel'),
    ('primer libro de los reyes', '1 Reyes'),
    ('segundo libro de los reyes', '2 Reyes'),
    ('libro de los reyes', '1 Reyes'),
    ('segundo libro de las cronicas', '2 Crónicas'),
    ('primer libro de las cronicas', '1 Crónicas'),
    ('libro de las cronicas', '1 Crónicas'),
    ('primer libro de los macabeos', '1 Macabeos'),
    ('segundo libro de los macabeos', '2 Macabeos'),
    ('libro de esdras', 'Esdras'),
    ('libro de nehemias', 'Nehemías'),
    ('libro de tobias', 'Tobías'),
    ('libro de judit', 'Judit'),
    ('libro de ester', 'Ester'),
    ('libro de job', 'Job'),
    ('libro de los proverbios', 'Proverbios'),
    ('libro del eclesiastes', 'Eclesiastés'),
    ('cantar de los cantares', 'Cantar de los Cantares'),
    ('libro de la sabiduria', 'Sabiduría'),
    ('libro del eclesiastico', 'Eclesiástico'),
    ('libro de los salmos', 'Salmos'),
    ('salmo', 'Salmo'),
)

LIBROS_UN_CAPITULO = {
    'Abdías', 'Filemón', '2 Juan', '3 Juan', 'Judas',
}


def _sin_acentos(texto):
    normalizado = unicodedata.normalize('NFD', texto.casefold())
    return ''.join(c for c in normalizado if unicodedata.category(c) != 'Mn')


class TextoHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.partes = []

    def handle_data(self, data):
        texto = ' '.join(data.split())
        if texto:
            self.partes.append(texto)


def extraer_seccion(texto, titulo):
    patron = re.compile(r'^\s*' + re.escape(titulo) + r'\s*$', re.I | re.M)
    coincidencia = patron.search(texto)
    if not coincidencia:
        return ''
    inicio = coincidencia.end()
    finales = []
    for siguiente in FINES:
        match = re.search(
            r'^\s*' + re.escape(siguiente) + r'\s*$',
            texto[inicio:],
            re.I | re.M,
        )
        if match:
            finales.append(inicio + match.start())
    fin = min(finales) if finales else len(texto)
    return texto[inicio:fin].strip(' :-–—\n\r')


def _detectar_libro(linea):
    texto = _sin_acentos(linea)
    for alias, canonico in ALIAS_LIBROS:
        if alias in texto:
            return canonico
    # Respaldo para menciones directas "del libro de Isaías".
    candidatos = (
        ('isaias', 'Isaías'), ('jeremias', 'Jeremías'),
        ('ezequiel', 'Ezequiel'), ('daniel', 'Daniel'),
        ('genesis', 'Génesis'), ('exodo', 'Éxodo'),
        ('deuteronomio', 'Deuteronomio'), ('proverbios', 'Proverbios'),
        ('sabiduria', 'Sabiduría'), ('eclesiastico', 'Eclesiástico'),
        ('malaquias', 'Malaquías'), ('zacarias', 'Zacarías'),
        ('oseas', 'Oseas'), ('amos', 'Amós'),
    )
    for alias, canonico in candidatos:
        if alias in texto:
            return canonico
    return ''


def _normalizar_rango(texto):
    return re.sub(r'\s+', ' ', texto.strip()).replace(' ,', ',').replace(' ;', ';')


def extraer_referencia(seccion, tipo):
    """Obtiene una cita bíblica de las líneas introductorias, nunca del cuerpo."""
    lineas = [linea.strip() for linea in seccion.splitlines() if linea.strip()]
    candidatas = []
    primeras = lineas[:8]
    for indice, linea in enumerate(primeras):
        candidatas.append(linea)
        if indice + 1 < len(primeras):
            candidatas.append(f'{linea} {primeras[indice + 1]}')

    if tipo == 'salmo':
        for linea in candidatas:
            limpio = _sin_acentos(linea)
            match = re.search(r'\bsalmo\s+(\d{1,3}[a-z]?)\b', limpio)
            if match:
                return f"Salmo {match.group(1)}"
        return ''

    if tipo == 'aclamacion':
        for linea in candidatas:
            match = re.search(
                r'\b(?:cfr\.?\s*)?([1-3]?\s?[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ ]{1,35}\s+\d{1,3}\s*[,.:]\s*[\d.,; -]+)',
                linea,
                re.I,
            )
            if match:
                return _normalizar_rango(match.group(1))
        return ''

    for linea in candidatas:
        if ':' not in linea:
            continue
        antes, despues = linea.rsplit(':', 1)
        libro = _detectar_libro(antes)
        if not libro:
            continue
        rango = _normalizar_rango(despues)
        match = re.match(r'^(\d{1,3})\s*[,.:]\s*(.+)$', rango)
        if match:
            capitulo, versiculos = match.groups()
            return f'{libro} {capitulo}, {versiculos}'
        if libro in LIBROS_UN_CAPITULO and re.match(r'^\d+[a-z]?(?:\s*[-–]\s*\d+[a-z]?)?$', rango):
            return f'{libro} {rango}'
    return ''

def analizar_html_misal(html):
    parser = TextoHTML()
    parser.feed(html)
    texto = '\n'.join(parser.partes)
    datos = {}
    for campo, titulo in SECCIONES:
        tipo = campo.removesuffix('_ref')
        seccion = extraer_seccion(texto, titulo)
        datos[campo] = extraer_referencia(seccion, tipo)
    return datos


def obtener_referencias_misal(fecha, timeout=25):
    url = f'https://misal.mx/{fecha.isoformat()}'
    request = Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept-Language': 'es-ES,es;q=0.9',
        },
    )
    with urlopen(request, timeout=timeout) as respuesta:
        html = respuesta.read().decode(
            respuesta.headers.get_content_charset() or 'utf-8',
            errors='replace',
        )
    return url, analizar_html_misal(html)
