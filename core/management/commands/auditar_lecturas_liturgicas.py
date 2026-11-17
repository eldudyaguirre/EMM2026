import csv
import time
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError

from core.liturgia import extraer_secciones


CAMPOS_OBLIGATORIOS = (
    "primera_lectura",
    "salmo",
    "aclamacion",
    "evangelio",
)

CAMPOS_REPORTE = (
    "fecha_calendario",
    "fecha_publicacion_fuente",
    "url_solicitada",
    "url_final",
    "http_status",
    "estado",
    "primera_lectura_caracteres",
    "salmo_caracteres",
    "segunda_lectura_caracteres",
    "aclamacion_caracteres",
    "evangelio_caracteres",
    "campos_obligatorios_faltantes",
    "observacion",
)


def descargar_html(url, timeout):
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; EmausLiturgicalAudit/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace"), response.status, response.geturl()


class Command(BaseCommand):
    help = (
        "Audita la disponibilidad y completitud de las lecturas en Misal.mx. "
        "Solo consulta la fuente y genera un CSV; no modifica PostgreSQL."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--calendario",
            default="calendario_liturgico_2026.csv",
            help="Ruta al calendario CSV existente. No se modifica.",
        )
        parser.add_argument(
            "--salida",
            default="auditoria_lecturas_liturgicas.csv",
            help="Ruta del CSV de auditoría que se generará.",
        )
        parser.add_argument("--desde", help="Fecha inicial YYYY-MM-DD, inclusive.")
        parser.add_argument("--hasta", help="Fecha final YYYY-MM-DD, inclusive.")
        parser.add_argument(
            "--limite",
            type=int,
            help="Limita la auditoría a las primeras N fechas.",
        )
        parser.add_argument(
            "--pausa",
            type=float,
            default=0.8,
            help="Segundos entre solicitudes (por defecto 0.8).",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=25,
            help="Tiempo máximo por página en segundos.",
        )

    def handle(self, *args, **options):
        ruta_calendario = Path(options["calendario"]).expanduser()
        ruta_salida = Path(options["salida"]).expanduser()

        if not ruta_calendario.is_file():
            raise CommandError(
                f"No existe el calendario: {ruta_calendario}. "
                "Indica la ruta correcta con --calendario."
            )

        try:
            desde = date.fromisoformat(options["desde"]) if options["desde"] else None
            hasta = date.fromisoformat(options["hasta"]) if options["hasta"] else None
        except ValueError as exc:
            raise CommandError(
                "Las fechas --desde y --hasta deben tener formato YYYY-MM-DD."
            ) from exc

        if desde and hasta and desde > hasta:
            raise CommandError("--desde no puede ser posterior a --hasta.")
        if options["limite"] is not None and options["limite"] < 1:
            raise CommandError("--limite debe ser mayor que cero.")
        if options["pausa"] < 0:
            raise CommandError("--pausa no puede ser negativa.")

        fechas = self._leer_fechas(ruta_calendario, desde, hasta)
        if options["limite"]:
            fechas = fechas[: options["limite"]]
        if not fechas:
            raise CommandError("El filtro no dejó fechas para auditar.")

        resultados = []
        estados = ("OK", "INCOMPLETA", "NO_ENCONTRADA", "ERROR", "REVISAR_FECHA")
        totales = {estado: 0 for estado in estados}

        self.stdout.write(self.style.NOTICE(f"Fechas a revisar: {len(fechas)}"))
        self.stdout.write(
            "Modo de solo lectura: no se insertará ni actualizará ningún registro.\n"
        )

        for indice, fecha_obj in enumerate(fechas, start=1):
            url = f"https://misal.mx/{fecha_obj.isoformat()}"
            fila = {
                "fecha_calendario": fecha_obj.isoformat(),
                "fecha_publicacion_fuente": "",
                "url_solicitada": url,
                "url_final": "",
                "http_status": "",
                "estado": "ERROR",
                "primera_lectura_caracteres": 0,
                "salmo_caracteres": 0,
                "segunda_lectura_caracteres": 0,
                "aclamacion_caracteres": 0,
                "evangelio_caracteres": 0,
                "campos_obligatorios_faltantes": "",
                "observacion": "",
            }

            try:
                html, status, url_final = descargar_html(url, options["timeout"])
                secciones, fecha_publicacion = extraer_secciones(html)
                fila["http_status"] = status
                fila["url_final"] = url_final

                if fecha_publicacion:
                    fila["fecha_publicacion_fuente"] = fecha_publicacion.isoformat()

                for campo, texto in secciones.items():
                    fila[f"{campo}_caracteres"] = len(texto)

                campos_requeridos = list(CAMPOS_OBLIGATORIOS)
                # En domingos también se espera la segunda lectura.
                if fecha_obj.weekday() == 6:
                    campos_requeridos.append("segunda_lectura")

                faltantes = [
                    campo for campo in campos_requeridos if not secciones.get(campo)
                ]
                fila["campos_obligatorios_faltantes"] = ";".join(faltantes)

                if faltantes:
                    fila["estado"] = "INCOMPLETA"
                    fila["observacion"] = (
                        "No se localizaron todas las secciones esperadas para esta fecha."
                    )
                elif (
                    fecha_publicacion
                    and abs((fecha_publicacion - fecha_obj).days) > 1
                ):
                    fila["estado"] = "REVISAR_FECHA"
                    fila["observacion"] = (
                        "La fecha de publicación difiere más de un día de la fecha "
                        "del calendario; se conserva la fecha de la URL como fecha "
                        "litúrgica objetivo."
                    )
                else:
                    fila["estado"] = "OK"

            except HTTPError as exc:
                fila["http_status"] = exc.code
                fila["estado"] = "NO_ENCONTRADA" if exc.code == 404 else "ERROR"
                fila["observacion"] = f"HTTP {exc.code}: {exc.reason}"
            except (URLError, TimeoutError, OSError) as exc:
                fila["estado"] = "ERROR"
                fila["observacion"] = str(exc)[:300]
            except Exception as exc:
                fila["estado"] = "ERROR"
                fila["observacion"] = (
                    f"{type(exc).__name__}: {str(exc)[:250]}"
                )

            resultados.append(fila)
            totales[fila["estado"]] = totales.get(fila["estado"], 0) + 1

            self.stdout.write(
                f"[{indice}/{len(fechas)}] {fila['fecha_calendario']} "
                f"{fila['estado']} "
                f"(1.ª={fila['primera_lectura_caracteres']}, "
                f"salmo={fila['salmo_caracteres']}, "
                f"2.ª={fila['segunda_lectura_caracteres']}, "
                f"aclamación={fila['aclamacion_caracteres']}, "
                f"Evangelio={fila['evangelio_caracteres']})"
            )

            if indice < len(fechas) and options["pausa"]:
                time.sleep(options["pausa"])

        ruta_salida.parent.mkdir(parents=True, exist_ok=True)
        with ruta_salida.open("w", newline="", encoding="utf-8-sig") as archivo:
            writer = csv.DictWriter(archivo, fieldnames=CAMPOS_REPORTE)
            writer.writeheader()
            writer.writerows(resultados)

        self.stdout.write("\n" + self.style.SUCCESS("Auditoría terminada."))
        self.stdout.write(f"Reporte: {ruta_salida.resolve()}")
        self.stdout.write(
            "Resumen: " + ", ".join(f"{k}={v}" for k, v in totales.items())
        )
        self.stdout.write(
            self.style.WARNING(
                "Este comando no guarda textos en PostgreSQL. "
                "Primero revisa el reporte y las fechas marcadas."
            )
        )

    @staticmethod
    def _leer_fechas(ruta, desde, hasta):
        fechas = []
        with ruta.open("r", newline="", encoding="utf-8-sig") as archivo:
            reader = csv.DictReader(archivo)
            if not reader.fieldnames or "fecha" not in reader.fieldnames:
                raise CommandError(
                    "El CSV debe contener una columna llamada 'fecha'."
                )
            for numero_fila, fila in enumerate(reader, start=2):
                valor = (fila.get("fecha") or "").strip()
                if not valor:
                    continue
                try:
                    fecha_obj = date.fromisoformat(valor)
                except ValueError as exc:
                    raise CommandError(
                        f"Fecha no válida en la fila {numero_fila}: {valor}"
                    ) from exc
                if desde and fecha_obj < desde:
                    continue
                if hasta and fecha_obj > hasta:
                    continue
                fechas.append(fecha_obj)
        return sorted(set(fechas))
