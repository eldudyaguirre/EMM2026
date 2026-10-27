from django.contrib import admin
from .models import Categoria, Cancion, Perfil, Grupo, Servicio


admin.site.register(Categoria)
admin.site.register(Cancion)


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ('nombres', 'correo', 'grupo')
    list_filter = ('grupo',)
    search_fields = ('nombres', 'correo')


@admin.register(Grupo)
class GrupoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'activo', 'fecha_creacion')
    list_filter = ('tipo', 'activo')
    search_fields = ('nombre', 'descripcion', 'integrantes__nombres')
    filter_horizontal = ('integrantes',)
    ordering = ('nombre',)


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'grupo', 'fecha', 'hora_inicio', 'hora_fin', 'activo')
    list_filter = ('activo', 'fecha', 'grupo__tipo', 'grupo')
    search_fields = ('titulo', 'grupo__nombre', 'lugar', 'observaciones')
    date_hierarchy = 'fecha'
    ordering = ('fecha', 'hora_inicio')
