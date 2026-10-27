from django.db import migrations


def agregar_ninguno(apps, schema_editor):
    Instrumento = apps.get_model('core', 'Instrumento')
    Instrumento.objects.get_or_create(nombre='Ninguno', defaults={'activo': True})


def quitar_ninguno(apps, schema_editor):
    Instrumento = apps.get_model('core', 'Instrumento')
    Instrumento.objects.filter(nombre='Ninguno').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0003_instrumentos_y_perfil_musical'),
    ]

    operations = [
        migrations.RunPython(agregar_ninguno, quitar_ninguno),
    ]
