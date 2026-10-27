from django.contrib import admin
from .models import Categoria, Cancion, Perfil, Grupo

admin.site.register(Categoria)
admin.site.register(Cancion)

@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):

    list_display = (
        'nombres',
        'correo',
        'grupo'
    )

@admin.register(Grupo)
class GrupoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'fecha_creacion')
    list_filter = ('activo',)
    search_fields = ('nombre', 'descripcion')
    ordering = ('nombre',)
