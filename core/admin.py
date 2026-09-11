from django.contrib import admin
from .models import Categoria,Cancion,Perfil

admin.site.register(Categoria)
admin.site.register(Cancion)

@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):

    list_display = (
        'nombres',
        'correo',
        'grupo'
    )