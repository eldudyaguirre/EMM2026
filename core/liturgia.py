from datetime import date, timedelta

from .models import LecturaLiturgica, ReferenciaLecturaLiturgica
from .calendario_liturgico import datos_dia


def domingo_advento(anio):
    fecha = date(anio, 11, 27)
    return fecha + timedelta(days=(6 - fecha.weekday()) % 7)


def ciclo_lectura(fecha):
    """Devuelve el ciclo aplicable: A/B/C, I/II o F para tiempos propios."""
    datos = datos_dia(fecha)
    if datos['es_domingo']:
        return datos['ciclo_dominical']
    return datos['ciclo_ferial'] or 'F'


def lectura_para_fecha(fecha):
    """Busca primero una excepción de fecha y luego el día/mes en su ciclo."""
    exacta = LecturaLiturgica.objects.filter(fecha_especifica=fecha).order_by('-id').first()
    if exacta:
        return exacta
    lectura = LecturaLiturgica.objects.filter(
        dia=fecha.day,
        mes=fecha.month,
        ciclo=ciclo_lectura(fecha),
        fecha_especifica__isnull=True,
    ).first()
    if lectura:
        return lectura
    return LecturaLiturgica.objects.filter(
        dia=fecha.day,
        mes=fecha.month,
        ciclo='F',
        fecha_especifica__isnull=True,
    ).first()


def referencia_para_fecha(fecha):
    """Busca metadatos de citas bíblicas para la fecha exacta del servicio."""
    return ReferenciaLecturaLiturgica.objects.filter(fecha=fecha).first()
