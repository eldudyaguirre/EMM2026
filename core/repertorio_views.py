from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from .models import Servicio, RepertorioServicio


@login_required(login_url='home')
def repertorio_servicio(request, servicio_id):
    """Abre el repertorio completo de un servicio desde el calendario."""
    servicio = get_object_or_404(
        Servicio.objects.select_related('grupo').prefetch_related('repertorio'),
        pk=servicio_id,
        activo=True,
        grupo__activo=True,
    )
    canciones = list(
        servicio.repertorio.select_related('cancion').order_by('orden', 'id')
    )
    return render(request, 'repertorio_servicio.html', {
        'servicio': servicio,
        'canciones': canciones,
        'total_canciones': len(canciones),
    })
