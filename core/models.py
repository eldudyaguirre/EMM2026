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

    grupo = models.IntegerField(
        choices=GRUPOS
    )

    fecha_nacimiento = models.DateField()

    def __str__(self):

        return self.nombres    