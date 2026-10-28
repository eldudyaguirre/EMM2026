from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from .models import Servicio, RepertorioServicio


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
