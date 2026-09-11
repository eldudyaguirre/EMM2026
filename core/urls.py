from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('contact/',views.contact, name='contact'),
    path('loginin/',views.loginin, name='loginin'),
    path('categoria/<int:id>/',views.categoria,name='categoria'),
    path('logout/',views.cerrar_sesion,name='logout'),
    path('guardar-cancion/<int:id>/',views.guardar_cancion),
]