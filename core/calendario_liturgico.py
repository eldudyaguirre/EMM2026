"""Motor de estructura del calendario litúrgico romano, perfil Ecuador.

Calcula fechas móviles, tiempos, semanas y ciclos. No determina por sí solo
las lecturas bíblicas ni el santoral completo: eso requiere el Leccionario y
el calendario particular aprobado para Ecuador.
"""
from datetime import date, timedelta

DIAS_SEMANA_ES = ('lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo')

NOMBRES_TIEMPOS = {
    'NAVIDAD': 'Tiempo de Navidad',
    'ORDINARIO': 'Tiempo Ordinario',
    'CUARESMA': 'Cuaresma',
    'SEMANA_SANTA': 'Semana Santa',
    'TRIDUO': 'Triduo Pascual',
    'PASCUA': 'Tiempo Pascual',
    'ADVIENTO': 'Adviento',
}


def domingo_pascua(anio):
    """Fecha del Domingo de Pascua usando el algoritmo gregoriano de Meeus."""
    a = anio % 19
    b, c = divmod(anio, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(anio, mes, dia)


def primer_domingo_adviento(anio):
    fecha = date(anio, 11, 27)
    return fecha + timedelta(days=(6 - fecha.weekday()) % 7)


def epifania_del_senor(anio):
    """Epifanía celebrada en domingo entre el 2 y el 8 de enero (Ecuador)."""
    fecha = date(anio, 1, 2)
    return fecha + timedelta(days=(6 - fecha.weekday()) % 7)


def bautismo_del_senor(anio):
    """Bautismo tras la Epifanía, con la excepción del 7/8 de enero."""
    epifania = epifania_del_senor(anio)
    if epifania.day in (7, 8):
        return epifania + timedelta(days=1)
    return epifania + timedelta(days=7)


def fechas_moviles(anio):
    pascua = domingo_pascua(anio)
    pentecostes = pascua + timedelta(days=49)
    return {
        'epifania': epifania_del_senor(anio),
        'bautismo_senor': bautismo_del_senor(anio),
        'miercoles_ceniza': pascua - timedelta(days=46),
        'domingo_ramos': pascua - timedelta(days=7),
        'jueves_santo': pascua - timedelta(days=3),
        'viernes_santo': pascua - timedelta(days=2),
        'sabado_santo': pascua - timedelta(days=1),
        'pascua': pascua,
        # En Ecuador la Ascensión se celebra el domingo (Pascua + 42 días).
        'ascension_ecuador': pascua + timedelta(days=42),
        'pentecostes': pentecostes,
        'santisima_trinidad': pascua + timedelta(days=56),
        # En Ecuador Corpus Christi se celebra el domingo (Pascua + 63 días).
        'corpus_christi_ecuador': pascua + timedelta(days=63),
        'sagrado_corazon': pascua + timedelta(days=68),
        'primer_domingo_adviento': primer_domingo_adviento(anio),
    }


def anio_liturgico(fecha):
    """Año en que comienza el año litúrgico vigente (primer domingo de Adviento)."""
    return fecha.year if fecha >= primer_domingo_adviento(fecha.year) else fecha.year - 1


def ciclo_dominical(fecha):
    """Ciclo A/B/C; el año litúrgico 2025-2026 corresponde al ciclo A."""
    base = anio_liturgico(fecha)
    return ('A', 'B', 'C')[(base - 2025) % 3]


def ciclo_ferial(fecha):
    """Ciclo ferial I/II del Tiempo Ordinario; None en los tiempos propios."""
    return 'I' if fecha.year % 2 else 'II'


def _lunes_inicio_ordinario(anio):
    return bautismo_del_senor(anio) + timedelta(days=1)


def _semanas_ordinarias_antes_cuaresma(anio):
    inicio = _lunes_inicio_ordinario(anio)
    ceniza = fechas_moviles(anio)['miercoles_ceniza']
    return ((ceniza - inicio).days // 7) + 1


def datos_dia(fecha):
    """Devuelve estructura litúrgica calculada para una fecha, sin lecturas."""
    if not isinstance(fecha, date):
        raise TypeError('fecha debe ser datetime.date')

    moviles = fechas_moviles(fecha.year)
    pascua = moviles['pascua']
    ceniza = moviles['miercoles_ceniza']
    ramos = moviles['domingo_ramos']
    jueves_santo = moviles['jueves_santo']
    pentecostes = moviles['pentecostes']
    adviento = moviles['primer_domingo_adviento']
    bautismo = moviles['bautismo_senor']

    celebraciones = {
        date(fecha.year, 1, 1): 'Santa María, Madre de Dios',
        moviles['epifania']: 'Epifanía del Señor',
        date(fecha.year, 2, 2): 'Presentación del Señor',
        date(fecha.year, 3, 19): 'San José, esposo de la Virgen María',
        date(fecha.year, 3, 25): 'Anunciación del Señor',
        date(fecha.year, 5, 26): 'Santa Mariana de Jesús de Paredes (Ecuador)',
        date(fecha.year, 6, 24): 'Nacimiento de San Juan Bautista',
        date(fecha.year, 6, 29): 'Santos Pedro y Pablo, apóstoles',
        date(fecha.year, 8, 15): 'Asunción de la Bienaventurada Virgen María',
        date(fecha.year, 11, 1): 'Todos los Santos',
        date(fecha.year, 11, 2): 'Conmemoración de todos los fieles difuntos',
        date(fecha.year, 11, 9): 'Dedicación de la Basílica de Letrán',
        date(fecha.year, 12, 8): 'Inmaculada Concepción de la Virgen María',
        date(fecha.year, 12, 25): 'Natividad del Señor',
        moviles['miercoles_ceniza']: 'Miércoles de Ceniza',
        ramos: 'Domingo de Ramos de la Pasión del Señor',
        jueves_santo: 'Jueves Santo en la Cena del Señor',
        moviles['viernes_santo']: 'Viernes Santo de la Pasión del Señor',
        moviles['sabado_santo']: 'Sábado Santo',
        pascua: 'Domingo de Pascua de la Resurrección del Señor',
        moviles['ascension_ecuador']: 'Ascensión del Señor (celebración en domingo, Ecuador)',
        pentecostes: 'Domingo de Pentecostés',
        moviles['santisima_trinidad']: 'Santísima Trinidad',
        moviles['corpus_christi_ecuador']: 'Santísimo Cuerpo y Sangre de Cristo (Ecuador)',
        moviles['sagrado_corazon']: 'Sagrado Corazón de Jesús',
        adviento: 'I Domingo de Adviento',
        bautismo: 'Bautismo del Señor',
    }

    if fecha.month == 12 and fecha.day >= 25:
        tiempo, semana = NOMBRES_TIEMPOS['NAVIDAD'], None
    elif fecha.month == 1 and fecha <= bautismo:
        tiempo, semana = NOMBRES_TIEMPOS['NAVIDAD'], None
    elif fecha >= adviento:
        tiempo = NOMBRES_TIEMPOS['ADVIENTO']
        semana = ((fecha - adviento).days // 7) + 1
    elif pascua <= fecha <= pentecostes:
        tiempo = NOMBRES_TIEMPOS['PASCUA']
        semana = ((fecha - pascua).days // 7) + 1
    elif jueves_santo <= fecha < pascua:
        tiempo, semana = NOMBRES_TIEMPOS['TRIDUO'], None
    elif ramos <= fecha < jueves_santo:
        tiempo, semana = NOMBRES_TIEMPOS['SEMANA_SANTA'], None
    elif ceniza <= fecha < ramos:
        tiempo = NOMBRES_TIEMPOS['CUARESMA']
        primer_domingo_cuaresma = ceniza + timedelta(days=(6 - ceniza.weekday()) % 7)
        semana = 0 if fecha < primer_domingo_cuaresma else ((fecha - primer_domingo_cuaresma).days // 7) + 1
    else:
        tiempo = NOMBRES_TIEMPOS['ORDINARIO']
        if fecha < ceniza:
            inicio = _lunes_inicio_ordinario(fecha.year)
            semana = ((fecha - inicio).days // 7) + 1
        else:
            inicio = pentecostes + timedelta(days=1)
            semana_inicial = _semanas_ordinarias_antes_cuaresma(fecha.year) + 2
            semana = semana_inicial + ((fecha - inicio).days // 7)
        # El domingo inaugura la semana litúrgica siguiente a la semana ferial
        # que comenzó el lunes anterior: lunes I, domingo II.
        if fecha.weekday() == 6:
            semana += 1

    ciclo_ferial_aplicable = (
        ciclo_ferial(fecha)
        if tiempo == NOMBRES_TIEMPOS['ORDINARIO'] and fecha.weekday() != 6
        else None
    )
    return {
        'fecha': fecha,
        'dia_semana': DIAS_SEMANA_ES[fecha.weekday()],
        'anio_liturgico': anio_liturgico(fecha),
        'tiempo_liturgico': tiempo,
        'semana_liturgica': semana,
        'ciclo_dominical': ciclo_dominical(fecha),
        'ciclo_ferial': ciclo_ferial_aplicable,
        'celebracion_calculada': celebraciones.get(fecha, ''),
        'es_domingo': fecha.weekday() == 6,
    }


def generar_calendario_anual(anio):
    """Genera una fila por fecha del año civil solicitado."""
    inicio = date(anio, 1, 1)
    fin = date(anio, 12, 31)
    filas = []
    actual = inicio
    while actual <= fin:
        filas.append(datos_dia(actual))
        actual += timedelta(days=1)
    return filas
