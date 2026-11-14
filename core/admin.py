from django.contrib import admin
from .models import (
    Categoria, Cancion, Perfil, Grupo, Servicio, Instrumento,
    LecturaLiturgica, ReferenciaLecturaLiturgica,
)


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


@admin.register(Instrumento)
class InstrumentoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo')
    list_filter = ('activo',)
    search_fields = ('nombre',)
    ordering = ('nombre',)


@admin.register(LecturaLiturgica)
class LecturaLiturgicaAdmin(admin.ModelAdmin):
    list_display = ('dia', 'mes', 'ciclo', 'nombre_celebracion', 'fecha_especifica')
    list_filter = ('ciclo', 'mes')
    search_fields = ('nombre_celebracion', 'primera_lectura', 'salmo', 'evangelio')
    ordering = ('mes', 'dia', 'ciclo')


@admin.register(ReferenciaLecturaLiturgica)
class ReferenciaLecturaLiturgicaAdmin(admin.ModelAdmin):
    list_display = (
        'fecha', 'tiempo_liturgico', 'ciclo_dominical', 'ciclo_ferial',
        'fuente', 'validada',
    )
    list_filter = ('tiempo_liturgico', 'ciclo_dominical', 'ciclo_ferial', 'fuente', 'validada')
    search_fields = (
        'celebracion', 'primera_lectura_ref', 'salmo_ref',
        'segunda_lectura_ref', 'evangelio_ref',
    )
    date_hierarchy = 'fecha'
    readonly_fields = ('consultada',)
    ordering = ('fecha',)
