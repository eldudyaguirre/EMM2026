import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_servicio_estado'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RepertorioServicio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_snapshot', models.IntegerField(blank=True, null=True)),
                ('titulo_snapshot', models.CharField(max_length=200)),
                ('letra_snapshot', models.TextField(help_text='Copia de la letra y acordes como se prepararon para este servicio.')),
                ('semitonos_transpuestos', models.IntegerField(default=0)),
                ('notacion_acordes', models.CharField(
                    choices=[
                        ('original', 'Original'),
                        ('latina', 'DO–RE–MI'),
                        ('inglesa', 'C–D–E'),
                    ],
                    default='original',
                    max_length=10,
                )),
                ('orden', models.PositiveIntegerField(default=0)),
                ('fecha_agregado', models.DateTimeField(auto_now_add=True)),
                ('agregado_por', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='canciones_repertorio_agregadas',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('cancion', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='repertorios_servicio',
                    to='core.cancion',
                )),
                ('servicio', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='repertorio',
                    to='core.servicio',
                )),
            ],
            options={
                'verbose_name': 'Canción del repertorio del servicio',
                'verbose_name_plural': 'Canciones del repertorio de los servicios',
                'ordering': ['orden', 'id'],
                'constraints': [
                    models.UniqueConstraint(
                        fields=('servicio', 'cancion'),
                        name='uniq_cancion_por_servicio',
                    ),
                ],
            },
        ),
    ]
