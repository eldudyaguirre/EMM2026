from datetime import date, timedelta

from django.db.models import Case, IntegerField, Value, When

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


def referencias_ordenadas():
    """Ordena fuentes: validadas primero; luego manual, Cuenca, Misal.mx y comparativas."""
    return ReferenciaLecturaLiturgica.objects.annotate(
        prioridad_fuente=Case(
            When(fuente='manual', then=Value(0)),
            When(fuente='arquidiocesis_cuenca', then=Value(1)),
            When(fuente='misal_mx', then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )
    ).order_by('fecha', '-validada', 'prioridad_fuente', '-consultada')


def referencia_para_fecha(fecha):
    """Devuelve la fuente preferida para la fecha exacta del servicio."""
    return referencias_ordenadas().filter(fecha=fecha).first()
