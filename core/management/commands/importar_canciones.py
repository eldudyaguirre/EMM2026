from django.core.management.base import BaseCommand
from core.models import Cancion, Categoria
from docx import Document
import os
import re


class Command(BaseCommand):

    help = "Importar canciones desde Word"

    def handle(self, *args, **kwargs):

        # Ruta donde pondrás los Word
        carpeta = r"C:\CancionesWord"

        # Crear categoría automáticamente si no existe
        categoria, created = Categoria.objects.get_or_create(
            nombre="08 - Cantos de la Comunión"
        )

        archivos = os.listdir(carpeta)

        for archivo in archivos:

            if not archivo.endswith(".docx"):
                continue

            try:

                ruta = os.path.join(
                    carpeta,
                    archivo
                )

                doc = Document(ruta)

                lineas = []

                # Leer todo el Word
                for p in doc.paragraphs:

                    texto = p.text.strip()

                    if texto:
                        lineas.append(texto)

                contenido = "\n".join(lineas[2:])

                numero = None
                titulo = ""

                usa_capodastro = False
                traste_capodastro = None

                # Obtener número y nombre
                # Ejemplo:
                # 1.- Acercate.docx

                # Obtener número REAL desde el Word
                numero = None
                titulo = ""

                # Primera línea = número real
                if len(lineas) > 0:

                    primera = lineas[0].strip()

                    if primera.isdigit():

                        numero = int(primera)

                # Segunda línea = título
                if len(lineas) > 1:

                    titulo = lineas[1].strip().title()

                # Si no encontró número
                if numero is None:

                    self.stdout.write(
                        self.style.WARNING(
                            f"No se encontró número en {archivo}"
                        )
                    )

                    continue
                else:

                    # Si no tiene número
                    titulo = archivo.replace(
                        ".docx",
                        ""
                    )

                # Detectar CAPO / CAP.
                # Ej:
                # CAPO 1
                # CAP.1
                # (CAP. 3)

                capo_match = re.search(
                    r"CAP(?:O|\.)?\s*([0-9]+)",
                    contenido,
                    re.IGNORECASE
                )

                if capo_match:

                    usa_capodastro = True

                    traste_capodastro = int(
                        capo_match.group(1)
                    )

                # Guardar o actualizar
                Cancion.objects.update_or_create(

                    numero=numero,

                    defaults={

                        "titulo": titulo,
                        "categoria": categoria,
                        "letra": contenido,
                        "usa_capodastro": usa_capodastro,
                        "traste_capodastro": traste_capodastro

                    }

                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Importada: {numero} - {titulo}"
                    )
                )

            except Exception as e:

                self.stdout.write(
                    self.style.ERROR(
                        f"✗ Error {archivo}: {str(e)}"
                    )
                )