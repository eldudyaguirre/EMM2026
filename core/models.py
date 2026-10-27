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
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['fecha', 'hora_inicio', 'titulo']
        verbose_name = 'Servicio'
        verbose_name_plural = 'Servicios'

    def __str__(self):
        return f"{self.titulo} - {self.grupo.nombre} ({self.fecha:%d/%m/%Y})"


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
