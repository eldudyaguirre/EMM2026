from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import transaction
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from io import BytesIO
from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted, KeepTogether
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
        entrada, creada = RepertorioServicio.objects.get_or_create(
            servicio=servicio,
            cancion=cancion,
            defaults={
                'numero_snapshot': cancion.numero,
                'titulo_snapshot': cancion.titulo,
                'letra_snapshot': cancion.letra,
                'usa_capodastro': cancion.usa_capodastro,
                'traste_capodastro': cancion.traste_capodastro,
                'orden': servicio.repertorio.count() + 1,
                'agregado_por': request.user,
            },
        )
        if creada:
            messages.success(request, f'«{cancion.titulo}» se agregó al repertorio.')
        else:
            messages.info(request, f'«{cancion.titulo}» ya estaba en este repertorio.')
    elif accion == 'editar':
        entrada = get_object_or_404(RepertorioServicio, pk=request.POST.get('repertorio_id'), servicio=servicio)
        titulo = request.POST.get('titulo_snapshot', '').strip()
        letra = request.POST.get('letra_snapshot', '')
        if not titulo or not letra.strip():
            messages.error(request, 'El título y la letra con acordes no pueden quedar vacíos.')
        else:
            entrada.titulo_snapshot = titulo[:200]
            entrada.letra_snapshot = letra
            entrada.save(update_fields=['titulo_snapshot', 'letra_snapshot'])
            messages.success(request, f'La versión de «{entrada.titulo_snapshot}» para este servicio fue guardada.')
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
    })

@login_required(login_url='home')
def exportar_repertorio_servicio_pdf(request, servicio_id):
    """Genera un PDF descargable con todas las canciones del repertorio del servicio."""
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
        topMargin=1.7 * cm, bottomMargin=1.7 * cm,
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
        fontSize=12, leading=15, textColor=colors.HexColor('#bd0026'),
        spaceBefore=10, spaceAfter=4, keepWithNext=True,
    )
    info_style = ParagraphStyle(
        'SongInfo', parent=base['Normal'], fontSize=8, leading=10,
        textColor=colors.HexColor('#555555'), spaceAfter=6, keepWithNext=True,
    )
    lyrics_style = ParagraphStyle(
        'SongLyrics', parent=base['Code'], fontName='Courier',
        fontSize=8.5, leading=12, textColor=colors.HexColor('#161616'),
        leftIndent=4, rightIndent=4, spaceAfter=10, splitLongWords=1,
    )

    story = [
        Paragraph("MINISTERIO DE MÚSICA · EMAÚS", meta_style),
        Paragraph(servicio.titulo, title_style),
        Paragraph(
            f"{servicio.fecha.strftime('%d/%m/%Y')} · "
            f"{servicio.hora_inicio.strftime('%H:%M')}"
            f"{' – ' + servicio.hora_fin.strftime('%H:%M') if servicio.hora_fin else ''}"
            f" · {servicio.grupo.nombre}"
            f"{' · ' + servicio.lugar if servicio.lugar else ''}",
            meta_style,
        ),
        Spacer(1, 5),
    ]

    if not canciones:
        story.append(Paragraph("Este servicio todavía no tiene canciones en su repertorio.", base['Normal']))
    else:
        for numero, item in enumerate(canciones, start=1):
            info = []
            if item.usa_capodastro and item.traste_capodastro:
                info.append(f"Capodastro: traste {item.traste_capodastro}")
            if item.semitonos_transpuestos:
                info.append(f"Transposición: {item.semitonos_transpuestos:+d} semitono(s)")
            notacion = item.get_notacion_acordes_display()
            if notacion:
                info.append(f"Notación: {notacion}")
            bloque = [
                Paragraph(f"{numero}. {item.titulo_snapshot}", song_style),
            ]
            if info:
                bloque.append(Paragraph(" · ".join(info), info_style))
            letra = item.letra_snapshot or ""
            bloque.append(Preformatted(letra, lyrics_style, maxLineLength=100))
            story.append(KeepTogether(bloque[:2]) if len(bloque) > 1 else bloque[0])
            if len(bloque) > 2:
                story.append(bloque[2])
            story.append(Spacer(1, 5))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#777777'))
        canvas.drawString(1.7 * cm, 0.9 * cm, "Ministerio de Música · Emaús")
        canvas.drawRightString(A4[0] - 1.7 * cm, 0.9 * cm, f"Página {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf = buffer.getvalue()
    buffer.close()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="repertorio_servicio_{servicio.pk}.pdf"'
    return response
