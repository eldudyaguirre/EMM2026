from datetime import date, timedelta

from .models import LecturaLiturgica


def domingo_advento(anio):
    fecha = date(anio, 11, 27)
    return fecha + timedelta(days=(6 - fecha.weekday()) % 7)


def ciclo_lectura(fecha):
    """Devuelve el ciclo dominical A/B/C o ferial I/II correspondiente."""
    if fecha.weekday() == 6:
        anio_liturgico = fecha.year if fecha >= domingo_advento(fecha.year) else fecha.year - 1
        return ('A', 'B', 'C')[(anio_liturgico - 2025) % 3]
    return 'I' if fecha.year % 2 else 'II'


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
