from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import transaction
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
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
