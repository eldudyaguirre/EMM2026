from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import transaction, IntegrityError
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from io import BytesIO
from django.http import HttpResponse
from django.contrib.staticfiles import finders
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted, KeepTogether, PageBreakIfNotEmpty
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg
from .models import Servicio, RepertorioServicio, Cancion


@login_required(login_url='home')
@require_POST
def gestionar_cancion_repertorio(request, servicio_id):
    """Añade, edita la copia del servicio o retira una canción del repertorio."""
    servicio = get_object_or_404(Servicio, pk=servicio_id, activo=True, grupo__activo=True)
    accion = request.POST.get('accion', '').strip()

    if servicio.estado == Servicio.ESTADO_TERMINADO:
        messages.error(request, 'El servicio está terminado y ya no se puede modificar.')
        return redirect('repertorio_servicio', servicio_id=servicio.pk)

    if accion == 'agregar':
        cancion = get_object_or_404(Cancion, pk=request.POST.get('cancion_id'))

        # Por omisión se conserva la configuración original de la canción.
        # Si el formulario envía una elección para esta fecha, esa elección
        # tiene prioridad y solo se guarda en RepertorioServicio.
        usa_capodastro = bool(cancion.usa_capodastro)
        traste_capodastro = (
            cancion.traste_capodastro if usa_capodastro else None
        )
        if 'usa_capodastro' in request.POST:
            usa_capodastro = request.POST.get('usa_capodastro', '').strip().lower() in {
                '1', 'on', 'true', 'si', 'sí'
            }
            traste_capodastro = None
            if usa_capodastro:
                try:
                    traste_capodastro = int(
                        request.POST.get('traste_capodastro', '')
                    )
                except (TypeError, ValueError):
                    traste_capodastro = None

                if traste_capodastro is None or not 1 <= traste_capodastro <= 12:
                    messages.error(
                        request,
                        'Selecciona un traste válido del 1 al 12 para el capodastro.',
                    )
                    return redirect('repertorio_servicio', servicio_id=servicio.pk)

        entrada, creada = RepertorioServicio.objects.get_or_create(
            servicio=servicio,
            cancion=cancion,
            defaults={
                'numero_snapshot': cancion.numero,
                'titulo_snapshot': cancion.titulo,
                'letra_snapshot': cancion.letra,
                'usa_capodastro': usa_capodastro,
                'traste_capodastro': traste_capodastro,
                'orden': servicio.repertorio.count() + 1,
                'agregado_por': request.user,
            },
        )
        if creada:
            messages.success(request, f'«{cancion.titulo}» se agregó al repertorio.')
        else:
            if 'usa_capodastro' in request.POST:
                entrada.usa_capodastro = usa_capodastro
                entrada.traste_capodastro = traste_capodastro
                entrada.save(update_fields=[
                    'usa_capodastro',
                    'traste_capodastro',
                ])
                messages.success(
                    request,
                    f'Se actualizó la configuración de capodastro de «{cancion.titulo}» para este servicio.',
                )
            else:
                messages.info(request, f'«{cancion.titulo}» ya estaba en este repertorio.')
    elif accion == 'mover':
        entrada = get_object_or_404(
            RepertorioServicio,
            pk=request.POST.get('repertorio_id'),
            servicio=servicio,
        )
        direccion = request.POST.get('direccion', '').strip()
        if direccion not in {'arriba', 'abajo'}:
            messages.error(request, 'La dirección solicitada no es válida.')
        else:
            with transaction.atomic():
                ordenadas = list(
                    servicio.repertorio.select_for_update().order_by('orden', 'id')
                )
                posicion = next(
                    (i for i, item in enumerate(ordenadas) if item.pk == entrada.pk),
                    None,
                )
                desplazamiento = -1 if direccion == 'arriba' else 1
                destino = posicion + desplazamiento if posicion is not None else None

                if destino is None or destino < 0 or destino >= len(ordenadas):
                    messages.info(request, 'La canción ya está en ese extremo del repertorio.')
                else:
                    ordenadas[posicion], ordenadas[destino] = (
                        ordenadas[destino],
                        ordenadas[posicion],
                    )
                    for nuevo_orden, item in enumerate(ordenadas, start=1):
                        if item.orden != nuevo_orden:
                            item.orden = nuevo_orden
                            item.save(update_fields=['orden'])
                    messages.success(request, 'El orden del repertorio fue actualizado.')

    elif accion == 'reemplazar':
        entrada = get_object_or_404(
            RepertorioServicio,
            pk=request.POST.get('repertorio_id'),
            servicio=servicio,
        )
        cancion_nueva = get_object_or_404(
            Cancion,
            pk=request.POST.get('cancion_id'),
        )

        if entrada.cancion_id == cancion_nueva.pk:
            messages.info(request, 'Esta canción ya está asignada a esta posición.')
        else:
            try:
                with transaction.atomic():
                    duplicada = servicio.repertorio.select_for_update().filter(
                        cancion_id=cancion_nueva.pk
                    ).exclude(pk=entrada.pk).exists()

                    if duplicada:
                        messages.error(
                            request,
                            f'«{cancion_nueva.titulo}» ya está en este repertorio. No se puede repetir.',
                        )
                    else:
                        # Se sustituye solo esta entrada: conserva su orden y
                        # los ajustes de transposición y notación del servicio.
                        # La letra, acordes y capodastro vienen del cancionero.
                        entrada.cancion = cancion_nueva
                        entrada.numero_snapshot = cancion_nueva.numero
                        entrada.titulo_snapshot = cancion_nueva.titulo
                        entrada.letra_snapshot = cancion_nueva.letra
                        entrada.usa_capodastro = cancion_nueva.usa_capodastro
                        entrada.traste_capodastro = cancion_nueva.traste_capodastro
                        entrada.save(update_fields=[
                            'cancion',
                            'numero_snapshot',
                            'titulo_snapshot',
                            'letra_snapshot',
                            'usa_capodastro',
                            'traste_capodastro',
                        ])
                        messages.success(
                            request,
                            f'La canción fue reemplazada por «{cancion_nueva.titulo}».',
                        )
            except IntegrityError:
                messages.error(
                    request,
                    'No se pudo reemplazar la canción porque ya está incluida en este repertorio.',
                )

    elif accion == 'editar':
        entrada = get_object_or_404(
            RepertorioServicio,
            pk=request.POST.get('repertorio_id'),
            servicio=servicio,
        )
        titulo = request.POST.get('titulo_snapshot', '').strip()
        letra = request.POST.get('letra_snapshot', '')
        usa_capodastro = request.POST.get('usa_capodastro') in {'1', 'on', 'true'}
        traste_capodastro = None

        if usa_capodastro:
            try:
                traste_capodastro = int(request.POST.get('traste_capodastro', ''))
            except (TypeError, ValueError):
                traste_capodastro = None

            if traste_capodastro is None or not 1 <= traste_capodastro <= 12:
                messages.error(
                    request,
                    'Selecciona un traste válido del 1 al 12 para el capodastro.',
                )
                return redirect('repertorio_servicio', servicio_id=servicio.pk)

        if not titulo or not letra.strip():
            messages.error(request, 'El título y la letra con acordes no pueden quedar vacíos.')
        else:
            # Estos valores pertenecen a la copia de esta canción dentro del
            # servicio; nunca modifican la canción original del cancionero.
            entrada.titulo_snapshot = titulo[:200]
            entrada.letra_snapshot = letra
            entrada.usa_capodastro = usa_capodastro
            entrada.traste_capodastro = traste_capodastro
            entrada.save(update_fields=[
                'titulo_snapshot',
                'letra_snapshot',
                'usa_capodastro',
                'traste_capodastro',
            ])
            messages.success(
                request,
                f'La versión de «{entrada.titulo_snapshot}» para este servicio fue guardada.',
            )
    elif accion == 'quitar':
        entrada = get_object_or_404(RepertorioServicio, pk=request.POST.get('repertorio_id'), servicio=servicio)
        titulo = entrada.titulo_snapshot
        entrada.delete()
        for orden, restante in enumerate(servicio.repertorio.order_by('orden', 'id'), start=1):
            if restante.orden != orden:
                restante.orden = orden
                restante.save(update_fields=['orden'])
        messages.success(request, f'«{titulo}» se quitó de este servicio. La canción original sigue en el cancionero.')
    else:
        messages.error(request, 'La acción solicitada no es válida.')

    return redirect('repertorio_servicio', servicio_id=servicio.pk)


@login_required(login_url='home')
def repertorio_servicio(request, servicio_id):
    """Muestra el repertorio y permite controlar el estado del servicio."""
    servicio = get_object_or_404(
        Servicio.objects.select_related('grupo').prefetch_related('repertorio'),
        pk=servicio_id,
        activo=True,
        grupo__activo=True,
    )
    if request.method == 'POST':
        accion = request.POST.get('accion', '')
        if accion == 'iniciar' and servicio.estado == Servicio.ESTADO_PROGRAMADO:
            servicio.estado = Servicio.ESTADO_EN_EJECUCION
            servicio.save(update_fields=['estado'])
            messages.success(request, 'El servicio está ahora en ejecución.')
        elif accion == 'terminar' and servicio.estado == Servicio.ESTADO_EN_EJECUCION:
            servicio.estado = Servicio.ESTADO_TERMINADO
            servicio.save(update_fields=['estado'])
            messages.success(request, 'El servicio ha sido marcado como terminado.')
        else:
            messages.warning(request, 'No se pudo cambiar el estado. Verifica el estado actual del servicio.')
        return redirect('repertorio_servicio', servicio_id=servicio.pk)

    canciones = list(
        servicio.repertorio.select_related('cancion').order_by('orden', 'id')
    )
    return render(request, 'repertorio_servicio.html', {
        'servicio': servicio,
        'canciones': canciones,
        'total_canciones': len(canciones),
        'trastes_capodastro': range(1, 13),
    })

@login_required(login_url='home')
def exportar_repertorio_servicio_pdf(request, servicio_id):
    """Exporta el repertorio en PDF, con una canción por página y franja roja."""
    servicio = get_object_or_404(
        Servicio.objects.select_related('grupo').prefetch_related('repertorio'),
        pk=servicio_id,
        activo=True,
        grupo__activo=True,
    )
    canciones = list(servicio.repertorio.order_by('orden', 'id'))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=1.7 * cm, leftMargin=1.7 * cm,
        topMargin=2.0 * cm, bottomMargin=1.7 * cm,
        title=f"Repertorio - {servicio.titulo}",
        author="Ministerio de Música Emaús",
    )
    base = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'RepertorioTitle', parent=base['Title'], fontName='Helvetica-Bold',
        fontSize=18, leading=22, textColor=colors.HexColor('#bd0026'),
        alignment=TA_CENTER, spaceAfter=8,
    )
    meta_style = ParagraphStyle(
        'RepertorioMeta', parent=base['Normal'], fontSize=9, leading=13,
        textColor=colors.HexColor('#444444'), alignment=TA_CENTER, spaceAfter=12,
    )
    song_style = ParagraphStyle(
        'SongTitle', parent=base['Heading2'], fontName='Helvetica-Bold',
        fontSize=15, leading=19, textColor=colors.HexColor('#bd0026'),
        spaceBefore=8, spaceAfter=8, keepWithNext=True,
    )
    info_style = ParagraphStyle(
        'SongInfo', parent=base['Normal'], fontSize=9, leading=12,
        textColor=colors.HexColor('#555555'), spaceAfter=10, keepWithNext=True,
    )
    lyrics_style = ParagraphStyle(
        'SongLyrics', parent=base['Code'], fontName='Courier',
        fontSize=9.5, leading=14, textColor=colors.HexColor('#161616'),
        leftIndent=4, rightIndent=4, spaceAfter=10, splitLongWords=1,
    )

    story = []
    for numero, item in enumerate(canciones, start=1):
        if numero > 1:
            story.append(PageBreakIfNotEmpty())
        story.extend([
            Paragraph(servicio.titulo, title_style),
            Paragraph(
                f"{servicio.fecha.strftime('%d/%m/%Y')} · "
                f"{servicio.hora_inicio.strftime('%H:%M')}"
                f"{' – ' + servicio.hora_fin.strftime('%H:%M') if servicio.hora_fin else ''}"
                f" · {servicio.grupo.nombre}"
                f"{' · ' + servicio.lugar if servicio.lugar else ''}",
                meta_style,
            ),
            Spacer(1, 4),
            Paragraph(f"{numero}. {item.titulo_snapshot}", song_style),
        ])
        info = []
        if item.usa_capodastro and item.traste_capodastro:
            info.append(f"Capodastro: traste {item.traste_capodastro}")
        if item.semitonos_transpuestos:
            info.append(f"Transposición: {item.semitonos_transpuestos:+d} semitono(s)")
        notacion = item.get_notacion_acordes_display()
        if notacion:
            info.append(f"Notación: {notacion}")
        if info:
            story.append(Paragraph(" · ".join(info), info_style))
        # Normalizar saltos de línea Windows/Mac antes de dibujar el texto.
        # Los \r que quedan dentro de Preformatted se imprimen como cuadros negros.
        letra_pdf = (item.letra_snapshot or "").replace("\r\n", "\n").replace("\r", "\n")
        story.append(Preformatted(letra_pdf, lyrics_style, maxLineLength=100))

    if not canciones:
        story.append(Paragraph(servicio.titulo, title_style))
        story.append(Paragraph("Este servicio todavía no tiene canciones en su repertorio.", base['Normal']))

    def dibujar_encabezado_pie(canvas, document):
        canvas.saveState()
        # Franja roja en todas las páginas.
        canvas.setFillColor(colors.HexColor('#bd0026'))
        canvas.rect(0, A4[1] - 0.28 * cm, A4[0], 0.28 * cm, fill=1, stroke=0)

        # Logo institucional solo en la primera página, debajo de la franja.
        if document.page == 1:
            logo_path = finders.find('images/logomio_negro.svg')
            if not logo_path:
                logo_path = finders.find('images/logomio.svg')
            if logo_path:
                try:
                    dibujo = svg2rlg(logo_path)
                    if dibujo and dibujo.width and dibujo.height:
                        ancho_max, alto_max = 5.0 * cm, 1.45 * cm
                        escala = min(ancho_max / dibujo.width, alto_max / dibujo.height)
                        dibujo.width *= escala
                        dibujo.height *= escala
                        dibujo.scale(escala, escala)
                        renderPDF.draw(dibujo, canvas, (A4[0] - dibujo.width) / 2, A4[1] - 0.55 * cm - dibujo.height)
                except Exception:
                    pass

        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#777777'))
        canvas.drawString(1.7 * cm, 0.9 * cm, "Ministerio de Música · Emaús")
        canvas.drawRightString(A4[0] - 1.7 * cm, 0.9 * cm, f"Página {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage= dibujar_encabezado_pie, onLaterPages=dibujar_encabezado_pie)
    pdf = buffer.getvalue()
    buffer.close()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="repertorio_servicio_{servicio.pk}.pdf"'
    return response
