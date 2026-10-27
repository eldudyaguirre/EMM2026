from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('contact/',views.contact, name='contact'),
    path('loginin/',views.loginin, name='loginin'),
    path('cambiar-password/', views.cambiar_password, name='cambiar_password'),
    path('calendario/', views.calendario, name='calendario'),
    path('grupos-servidores/', views.grupos_servidores, name='grupos_servidores'),
    path('grupos-servidores/exportar-pdf/', views.exportar_grupos_pdf, name='exportar_grupos_pdf'),
    path('servidores/', views.servidores, name='servidores'),
    path('categoria/<int:id>/',views.categoria,name='categoria'),
    path('logout/',views.cerrar_sesion,name='logout'),
    path('guardar-cancion/<int:id>/',views.guardar_cancion),
]