# Generated for the musical profile fields and instrument catalog.
from django.db import migrations, models
import django.db.models.deletion


INSTRUMENTOS_INICIALES = [
    'Batería',
    'Bajo',
    'Flauta',
    'Guitarra',
    'Percusión',
    'Piano',
    'Saxofón',
    'Teclado',
    'Trompeta',
    'Ukelele',
    'Violín',
    'Otro',
]


def cargar_instrumentos(apps, schema_editor):
    Instrumento = apps.get_model('core', 'Instrumento')
    for nombre in INSTRUMENTOS_INICIALES:
        Instrumento.objects.get_or_create(nombre=nombre, defaults={'activo': True})


def revertir_instrumentos(apps, schema_editor):
    Instrumento = apps.get_model('core', 'Instrumento')
    Instrumento.objects.filter(nombre__in=INSTRUMENTOS_INICIALES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_alter_cancion_categoria'),
    ]

    operations = [
        migrations.CreateModel(
            name='Instrumento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, unique=True)),
                ('activo', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Instrumento',
                'verbose_name_plural': 'Instrumentos',
                'ordering': ['nombre'],
            },
        ),
        migrations.AddField(
            model_name='perfil',
            name='es_cantante',
            field=models.BooleanField(default=False, verbose_name='Es cantante'),
        ),
        migrations.AddField(
            model_name='perfil',
            name='instrumentos',
            field=models.ManyToManyField(blank=True, related_name='servidores', to='core.instrumento'),
        ),
        migrations.RunPython(cargar_instrumentos, revertir_instrumentos),
    ]
