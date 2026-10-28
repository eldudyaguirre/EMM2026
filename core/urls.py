from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('contact/',views.contact, name='contact'),
    path('loginin/',views.loginin, name='loginin'),
    path('trazabilidad-preloader/', views.trazabilidad_preloader, name='trazabilidad_preloader'),
    path('cambiar-password/', views.cambiar_password, name='cambiar_password'),
    path('calendario/', views.calendario, name='calendario'),
    path('servicios/cancion/<int:cancion_id>/programados/', views.servicios_programados_para_cancion, name='servicios_programados_para_cancion'),
    path('servicios/cancion/<int:cancion_id>/agregar/', views.agregar_cancion_a_servicio, name='agregar_cancion_a_servicio'),
    path('servicios/', views.gestion_servicios, name='servicios'),
    path('servicios/exportar-pdf/', views.exportar_servicios_pdf, name='exportar_servicios_pdf'),
    path('grupos-servidores/', views.grupos_servidores, name='grupos_servidores'),
    path('grupos-servidores/exportar-pdf/', views.exportar_grupos_pdf, name='exportar_grupos_pdf'),
    path('servidores/', views.servidores, name='servidores'),
    path('servidores/exportar-pdf/', views.exportar_servidores_pdf, name='exportar_servidores_pdf'),
    path('exportar-pdf/<int:id>/', views.exportar_pdf, name='exportar_pdf'),
    path('buscar-canciones/', views.buscar_canciones, name='buscar_canciones'),
    path('cancion/<int:id>/detalle/', views.detalle_cancion, name='detalle_cancion'),
    path('categoria/<int:id>/crear-cancion/', views.crear_cancion, name='crear_cancion'),
    path('categoria/<int:id>/',views.categoria,name='categoria'),
    path('logout/',views.cerrar_sesion,name='logout'),
    path('guardar-cancion/<int:id>/',views.guardar_cancion),
]