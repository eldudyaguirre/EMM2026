from django.shortcuts import redirect
from django.urls import resolve


class ForceFirstPasswordChangeMiddleware:
    """Impide que los servidores naveguen hasta actualizar su contraseña inicial."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not (user.is_staff or user.is_superuser):
            try:
                perfil = user.perfil
            except Exception:
                perfil = None

            if perfil and perfil.debe_cambiar_password:
                try:
                    url_name = resolve(request.path_info).url_name
                except Exception:
                    url_name = None
                permitidas = {'primer_cambio_password', 'logout'}
                if url_name not in permitidas and not request.path_info.startswith('/static/'):
                    return redirect('primer_cambio_password')

        return self.get_response(request)
