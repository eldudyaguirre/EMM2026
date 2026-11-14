"""Motor de estructura del calendario litúrgico romano, perfil Ecuador.

Calcula fechas móviles, tiempos, semanas y algunas celebraciones principales.
No determina por sí solo todas las precedencias ni el santoral completo: eso
requiere el calendario particular aprobado para Ecuador y validación eclesial.
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
    """Epifanía celebrada en domingo entre el 2 y el 8 de enero (perfil Ecuador)."""
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
    adviento = primer_domingo_adviento(anio)
    return {
        'epifania': epifania_del_senor(anio),
        'bautismo_senor': bautismo_del_senor(anio),
        'miercoles_ceniza': pascua - timedelta(days=46),
        'domingo_ramos': pascua - timedelta(days=7),
        'jueves_santo': pascua - timedelta(days=3),
        'viernes_santo': pascua - timedelta(days=2),
        'sabado_santo': pascua - timedelta(days=1),
        'pascua': pascua,
        # En Ecuador la Ascensión y Corpus Christi se trasladan al domingo.
        'ascension_ecuador': pascua + timedelta(days=42),
        'pentecostes': pentecostes,
        'santisima_trinidad': pascua + timedelta(days=56),
        'corpus_christi_ecuador': pascua + timedelta(days=63),
        'sagrado_corazon': pascua + timedelta(days=68),
        'inmaculado_corazon': pascua + timedelta(days=69),
        'maria_madre_iglesia': pentecostes + timedelta(days=1),
        'cristo_sumo_eterno_sacerdote': pentecostes + timedelta(days=4),
        'cristo_rey': adviento - timedelta(days=7),
        'primer_domingo_adviento': adviento,
    }


def anio_liturgico(fecha):
    """Año inicial del periodo litúrgico (p. ej. 2025 para 2025-2026)."""
    return fecha.year if fecha >= primer_domingo_adviento(fecha.year) else fecha.year - 1


def ciclo_dominical(fecha):
    """Ciclo A/B/C; el año litúrgico 2025-2026 corresponde al ciclo A."""
    base = anio_liturgico(fecha)
    return ('A', 'B', 'C')[(base - 2025) % 3]


def ciclo_ferial(fecha):
    """Ciclo ferial I/II del año litúrgico vigente.

    El ciclo cambia con el primer domingo de Adviento, no el 1 de enero.
    Por ejemplo, el año litúrgico 2026-2027 utiliza el ciclo ferial I,
    incluido Adviento 2026.
    """
    anio_ciclo = anio_liturgico(fecha) + 1
    return 'I' if anio_ciclo % 2 else 'II'


def _lunes_inicio_ordinario(anio):
    return bautismo_del_senor(anio) + timedelta(days=1)


def _semanas_ordinarias_antes_cuaresma(anio):
    inicio = _lunes_inicio_ordinario(anio)
    ceniza = fechas_moviles(anio)['miercoles_ceniza']
    return ((ceniza - inicio).days // 7) + 1


def _sagrada_familia(anio):
    """Domingo dentro de la octava de Navidad; 30 de diciembre si no hay domingo."""
    navidad = date(anio, 12, 25)
    fin_octava = date(anio, 12, 31)
    dias_hasta_domingo = (6 - navidad.weekday()) % 7 or 7
    domingo = navidad + timedelta(days=dias_hasta_domingo)
    if navidad <= domingo <= fin_octava:
        return domingo
    return date(anio, 12, 30)


def _celebraciones_principales(anio, moviles):
    """Hitos y celebraciones principales; catálogo deliberadamente no exhaustivo."""
    celebraciones = {
        date(anio, 1, 1): 'Santa María, Madre de Dios',
        moviles['epifania']: 'Epifanía del Señor',
        date(anio, 2, 2): 'Presentación del Señor',
        date(anio, 3, 19): 'San José, esposo de la Virgen María',
        date(anio, 3, 25): 'Anunciación del Señor',
        date(anio, 4, 20): 'Santísima Virgen Dolorosa del Colegio (Ecuador; verificar rango)',
        moviles['maria_madre_iglesia']: 'Bienaventurada Virgen María, Madre de la Iglesia',
        date(anio, 5, 26): 'Santa Mariana de Jesús de Paredes (Ecuador)',
        moviles['cristo_sumo_eterno_sacerdote']: 'Jesucristo, Sumo y Eterno Sacerdote (Ecuador)',
        date(anio, 6, 24): 'Nacimiento de San Juan Bautista',
        date(anio, 6, 29): 'Santos Pedro y Pablo, apóstoles',
        date(anio, 8, 15): 'Asunción de la Bienaventurada Virgen María',
        date(anio, 9, 24): 'Nuestra Señora de la Merced (calendario Ecuador; verificar rango)',
        date(anio, 11, 1): 'Todos los Santos',
        date(anio, 11, 2): 'Conmemoración de todos los fieles difuntos',
        date(anio, 11, 9): 'Dedicación de la Basílica de Letrán',
        date(anio, 11, 30): 'San Andrés, apóstol',
        moviles['cristo_rey']: 'Nuestro Señor Jesucristo, Rey del Universo',
        date(anio, 12, 8): 'Inmaculada Concepción de la Virgen María',
        date(anio, 12, 25): 'Natividad del Señor',
        date(anio, 12, 26): 'San Esteban, protomártir',
        _sagrada_familia(anio): 'La Sagrada Familia de Jesús, María y José',
        date(anio, 12, 28): 'Santos Inocentes, mártires',
        moviles['miercoles_ceniza']: 'Miércoles de Ceniza',
        moviles['domingo_ramos']: 'Domingo de Ramos de la Pasión del Señor',
        # Los tres días de Semana Santa anteriores al Triduo se muestran por nombre.
        moviles['domingo_ramos'] + timedelta(days=1): 'Lunes Santo',
        moviles['domingo_ramos'] + timedelta(days=2): 'Martes Santo',
        moviles['domingo_ramos'] + timedelta(days=3): 'Miércoles Santo',
        moviles['jueves_santo']: 'Jueves Santo en la Cena del Señor',
        moviles['viernes_santo']: 'Viernes Santo de la Pasión del Señor',
        moviles['sabado_santo']: 'Sábado Santo',
        moviles['pascua']: 'Domingo de Pascua de la Resurrección del Señor',
        moviles['ascension_ecuador']: 'Ascensión del Señor (celebración en domingo, Ecuador)',
        moviles['pentecostes']: 'Domingo de Pentecostés',
        moviles['santisima_trinidad']: 'Santísima Trinidad',
        moviles['corpus_christi_ecuador']: 'Santísimo Cuerpo y Sangre de Cristo (Ecuador)',
        moviles['sagrado_corazon']: 'Sagrado Corazón de Jesús',
        moviles['inmaculado_corazon']: 'Inmaculado Corazón de María',
        moviles['primer_domingo_adviento']: 'I Domingo de Adviento',
    }
    return celebraciones


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
        # Miércoles de Ceniza a sábado se identifican por su nombre, no como semana 0.
        semana = None if fecha < primer_domingo_cuaresma else (
            (fecha - primer_domingo_cuaresma).days // 7
        ) + 1
    else:
        tiempo = NOMBRES_TIEMPOS['ORDINARIO']
        if fecha < ceniza:
            inicio = _lunes_inicio_ordinario(fecha.year)
            semana = ((fecha - inicio).days // 7) + 1
        else:
            inicio = pentecostes + timedelta(days=1)
            semana_inicial = _semanas_ordinarias_antes_cuaresma(fecha.year) + 2
            semana = semana_inicial + ((fecha - inicio).days // 7)
        # Los domingos inauguran la semana siguiente a la ferial precedente.
        if fecha.weekday() == 6:
            semana += 1

    ciclo_ferial_aplicable = (
        ciclo_ferial(fecha)
        if tiempo == NOMBRES_TIEMPOS['ORDINARIO'] and fecha.weekday() != 6
        else None
    )
    inicio_anio = anio_liturgico(fecha)
    return {
        'fecha': fecha,
        'dia_semana': DIAS_SEMANA_ES[fecha.weekday()],
        'anio_liturgico': f'{inicio_anio}-{inicio_anio + 1}',
        'anio_liturgico_inicio': inicio_anio,
        'tiempo_liturgico': tiempo,
        'semana_liturgica': semana,
        'ciclo_dominical': ciclo_dominical(fecha),
        'ciclo_ferial': ciclo_ferial_aplicable,
        'celebracion_calculada': _celebraciones_principales(fecha.year, moviles).get(fecha, ''),
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
