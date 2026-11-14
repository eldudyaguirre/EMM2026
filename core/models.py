from django.db import models
from django.contrib.auth.models import User

# models.py

class Categoria(models.Model):
    nombre = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre


# models.py

class Cancion(models.Model):

    numero = models.IntegerField(
        unique=True,
        null=True,
        blank=True
    )

    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.CASCADE,
        related_name='canciones'
    )

    titulo = models.CharField(
        max_length=200
    )

    letra = models.TextField()

    usa_capodastro = models.BooleanField(
        default=False
    )

    traste_capodastro = models.IntegerField(
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['numero']

    def __str__(self):
        return f"{self.numero} - {self.titulo}"
    
    
class Perfil(models.Model):

    GRUPOS = (

        (1,'Grupo 1'),
        (2,'Grupo 2'),
        (3,'Grupo 3'),
        (4,'Grupo 4'),
        (5,'Grupo 5'),
        (6,'Grupo 6'),
        (7,'Grupo 7'),
        (8,'Grupo 8'),
        (9,'Grupo 9')

    )

    usuario = models.OneToOneField(
        User,
        on_delete=models.CASCADE
    )

    nombres = models.CharField(
        max_length=200
    )

    correo = models.EmailField()

    telefono = models.CharField(max_length=20, blank=True, default='')

    grupo = models.IntegerField(
        choices=GRUPOS
    )

    fecha_nacimiento = models.DateField()

    debe_cambiar_password = models.BooleanField(default=True, verbose_name='Debe cambiar contraseña al ingresar')

    es_cantante = models.BooleanField(default=False, verbose_name='Es cantante')
    instrumentos = models.ManyToManyField('Instrumento', blank=True, related_name='servidores')

    def __str__(self):

        return self.nombres

class Grupo(models.Model):
    """Grupo permanente o temporal del Ministerio de Música de Emaús."""
    TIPO_PERMANENTE = 'permanente'
    TIPO_TEMPORAL = 'temporal'
    TIPOS = (
        (TIPO_PERMANENTE, 'Permanente'),
        (TIPO_TEMPORAL, 'Temporal'),
    )

    nombre = models.CharField(max_length=100, unique=True)
    tipo = models.CharField(max_length=12, choices=TIPOS, default=TIPO_PERMANENTE)
    descripcion = models.TextField(blank=True)
    integrantes = models.ManyToManyField(
        'Perfil',
        blank=True,
        related_name='grupos_asignados',
        help_text='Integrantes seleccionados para este grupo o evento.'
    )
    lider = models.ForeignKey('Perfil', on_delete=models.SET_NULL, null=True, blank=True, related_name='grupos_liderados', verbose_name='Líder del grupo')
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Grupo'
        verbose_name_plural = 'Grupos'

    def __str__(self):
        return self.nombre


class Servicio(models.Model):
    """Servicio programado en el calendario para un grupo."""
    ESTADO_PROGRAMADO = 'programado'
    ESTADO_EN_EJECUCION = 'en_ejecucion'
    ESTADO_TERMINADO = 'terminado'
    ESTADOS = (
        (ESTADO_PROGRAMADO, 'Programado'),
        (ESTADO_EN_EJECUCION, 'En ejecución'),
        (ESTADO_TERMINADO, 'Terminado'),
    )

    titulo = models.CharField(max_length=150, help_text='Ej.: Servicio de Navidad')
    grupo = models.ForeignKey(
        Grupo,
        on_delete=models.PROTECT,
        related_name='servicios'
    )
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField(null=True, blank=True)
    lugar = models.CharField(max_length=200, blank=True)
    observaciones = models.TextField(blank=True)
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default=ESTADO_PROGRAMADO,
    )
    # Campo heredado para compatibilidad con el calendario y registros anteriores.
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['fecha', 'hora_inicio', 'titulo']
        verbose_name = 'Servicio'
        verbose_name_plural = 'Servicios'

    def __str__(self):
        return f"{self.titulo} - {self.grupo.nombre} ({self.fecha:%d/%m/%Y})"


class RepertorioServicio(models.Model):
    """Versión de una canción asignada a un servicio, independiente de la canción original."""
    NOTACION_ORIGINAL = 'original'
    NOTACION_LATINA = 'latina'
    NOTACION_INGLESA = 'inglesa'
    NOTACIONES = (
        (NOTACION_ORIGINAL, 'Original'),
        (NOTACION_LATINA, 'DO–RE–MI'),
        (NOTACION_INGLESA, 'C–D–E'),
    )

    servicio = models.ForeignKey(
        Servicio,
        on_delete=models.CASCADE,
        related_name='repertorio',
    )
    cancion = models.ForeignKey(
        Cancion,
        on_delete=models.PROTECT,
        related_name='repertorios_servicio',
    )
    numero_snapshot = models.IntegerField(null=True, blank=True)
    titulo_snapshot = models.CharField(max_length=200)
    letra_snapshot = models.TextField(
        help_text='Copia de la letra y acordes como se prepararon para este servicio.'
    )
    usa_capodastro = models.BooleanField(
        default=False,
        help_text='Indica si esta versión del repertorio usa capodastro.'
    )
    traste_capodastro = models.IntegerField(
        null=True,
        blank=True,
        help_text='Traste del capodastro para este servicio, independiente de la canción original.'
    )
    semitonos_transpuestos = models.IntegerField(default=0)
    notacion_acordes = models.CharField(
        max_length=10,
        choices=NOTACIONES,
        default=NOTACION_ORIGINAL,
    )
    orden = models.PositiveIntegerField(default=0)
    agregado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='canciones_repertorio_agregadas',
    )
    fecha_agregado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['orden', 'id']
        verbose_name = 'Canción del repertorio del servicio'
        verbose_name_plural = 'Canciones del repertorio de los servicios'
        constraints = [
            models.UniqueConstraint(
                fields=['servicio', 'cancion'],
                name='uniq_cancion_por_servicio',
            ),
        ]

    def __str__(self):
        return f'{self.servicio} · {self.titulo_snapshot}'


class Instrumento(models.Model):
    """Catálogo de instrumentos musicales que pueden tocar los servidores."""
    nombre = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Instrumento'
        verbose_name_plural = 'Instrumentos'

    def __str__(self):
        return self.nombre


class LecturaLiturgica(models.Model):
    """Lecturas por día/mes y ciclo litúrgico, con excepciones para fechas móviles."""
    CICLOS = (('F', 'Celebración fija'), ('I', 'Ferial I'), ('II', 'Ferial II'), ('A', 'Dominical A'), ('B', 'Dominical B'), ('C', 'Dominical C'))
    dia = models.PositiveSmallIntegerField()
    mes = models.PositiveSmallIntegerField()
    ciclo = models.CharField(max_length=2, choices=CICLOS, default='F')
    fecha_especifica = models.DateField(null=True, blank=True, help_text='Para solemnidades móviles u otras excepciones.')
    nombre_celebracion = models.CharField(max_length=200, blank=True)
    primera_lectura = models.TextField(blank=True)
    salmo = models.TextField(blank=True)
    segunda_lectura = models.TextField(blank=True)
    aclamacion = models.TextField(blank=True)
    evangelio = models.TextField(blank=True)
    fecha_fuente = models.DateField(null=True, blank=True)
    url_fuente = models.URLField(max_length=500, blank=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['mes', 'dia', 'ciclo']
        verbose_name = 'Lectura litúrgica'
        verbose_name_plural = 'Lecturas litúrgicas'
        constraints = [models.UniqueConstraint(fields=['dia', 'mes', 'ciclo'], condition=models.Q(fecha_especifica__isnull=True), name='uniq_lectura_dia_mes_ciclo')]
        indexes = [models.Index(fields=['fecha_especifica'], name='core_lectur_fecha_e5b6e2_idx'), models.Index(fields=['mes', 'dia'], name='core_lectur_mes_6b5b8f_idx')]

    def __str__(self):
        return f'{self.dia:02d}/{self.mes:02d} · {self.get_ciclo_display()}'
