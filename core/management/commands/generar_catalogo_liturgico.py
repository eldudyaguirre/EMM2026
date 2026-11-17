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
        re.compile(r"^\s*(?:\d{1,2}\s*[\.\)]\s*)?PRIMERA\s+LECTURA\b", re.I),
    ),
    (
        "salmo_responsorial",
        re.compile(r"^\s*(?:\d{1,2}\s*[\.\)]\s*)?SALMO\s+RESPONSORIAL\b", re.I),
    ),
    (
        "segunda_lectura",
        re.compile(r"^\s*(?:\d{1,2}\s*[\.\)]\s*)?SEGUNDA\s+LECTURA\b", re.I),
    ),
    (
        "aclamacion",
        re.compile(
            r"^\s*(?:\d{1,2}\s*[\.\)]\s*)?"
            r"(?:ACLAMACI[ÓO]N(?:\s+ANTES\s+DEL\s+EVANGELIO)?|ALELUYA)\b",
            re.I,
        ),
    ),
    (
        "evangelio",
        re.compile(
            r"^\s*(?:\d{1,2}\s*[\.\)]\s*)?"
            r"(?:EVANGELIO\b|LECTURA\s+DEL\s+(?:SANTO\s+)?EVANGELIO\b)",
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


def _extraer_secciones(texto):
    """
    Extrae bloques de lectura a partir de sus encabezados explícitos.
    Conserva el texto fuente; no inventa referencias bíblicas ni completa
    secciones que no estén presentes en el documento.
    """
    lineas = _lineas_documento(texto)
    detecciones = []

    for indice, linea in enumerate(lineas):
        for nombre, patron in PATRONES_SECCION:
            coincidencia = patron.search(_normalizar(linea))
            if coincidencia:
                # Exigir encabezado breve para no confundir menciones dentro
                # del cuerpo de una reflexión con un título de sección.
                if len(linea) <= 110:
                    detecciones.append((indice, nombre))
                break

    # Conservar únicamente la primera aparición de cada sección. Evita que
    # una segunda versión/opción de una lectura desplace accidentalmente
    # el inicio de la sección principal.
    primeras = {}
    for indice, nombre in detecciones:
        primeras.setdefault(nombre, indice)

    posiciones = sorted((indice, nombre) for nombre, indice in primeras.items())
    secciones = {
        "primera_lectura": "",
        "salmo_responsorial": "",
        "segunda_lectura": "",
        "aclamacion": "",
        "evangelio": "",
    }

    for posicion, (inicio, nombre) in enumerate(posiciones):
        fin = len(lineas)
        if posicion + 1 < len(posiciones):
            fin = posiciones[posicion + 1][0]

        # La primera lectura, el salmo, la segunda y la aclamación terminan
        # al comenzar otra sección reconocida. El Evangelio se corta además
        # en "Palabra del Señor" cuando aparece.
        bloque = []
        for linea in lineas[inicio + 1:fin]:
            bloque.append(linea)
            if nombre == "evangelio" and FIN_LECTURA.match(_normalizar(linea)):
                break
            if nombre != "evangelio" and MARCADORES_OTRAS_SECCIONES.match(
                _normalizar(linea)
            ):
                bloque.pop()
                break

        secciones[nombre] = "\n".join(bloque).strip()

    return secciones


def _clasificar(fila, texto_disponible):
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
    if titulo or ciclo:
        return (
            CATEGORIA_LECTURAS,
            "El inventario identifica celebración o ciclo litúrgico.",
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

            categoria, motivo = _clasificar(fila, texto_disponible)
            secciones = _extraer_secciones(texto) if texto else {}

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
            if (fila.get("metodo_extraccion") or "") == "OCR_TESSERACT":
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
