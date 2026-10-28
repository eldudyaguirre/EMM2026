from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_lider_grupo'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicio',
            name='estado',
            field=models.CharField(
                choices=[
                    ('programado', 'Programado'),
                    ('en_ejecucion', 'En ejecución'),
                    ('terminado', 'Terminado'),
                ],
                default='programado',
                max_length=20,
            ),
        ),
    ]
