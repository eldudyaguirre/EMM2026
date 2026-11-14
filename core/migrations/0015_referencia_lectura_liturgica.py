from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0014_lectura_liturgica')]

    operations = [
        migrations.CreateModel(
            name='ReferenciaLecturaLiturgica',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateField(unique=True)),
                ('anio_liturgico', models.CharField(max_length=9)),
                ('tiempo_liturgico', models.CharField(max_length=40)),
                ('semana_liturgica', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('dia_semana', models.CharField(max_length=12)),
                ('ciclo_dominical', models.CharField(blank=True, max_length=1)),
                ('ciclo_ferial', models.CharField(blank=True, max_length=2)),
                ('celebracion', models.CharField(blank=True, max_length=200)),
                ('primera_lectura_ref', models.CharField(blank=True, max_length=250)),
                ('salmo_ref', models.CharField(blank=True, max_length=250)),
                ('segunda_lectura_ref', models.CharField(blank=True, max_length=250)),
                ('aclamacion_ref', models.CharField(blank=True, max_length=250)),
                ('evangelio_ref', models.CharField(blank=True, max_length=250)),
                ('fuente', models.CharField(choices=[('misal_mx', 'Misal.mx'), ('arquidiocesis_cuenca', 'Arquidiócesis de Cuenca'), ('usccb', 'USCCB (referencia comparativa)'), ('manual', 'Carga o validación manual')], default='misal_mx', max_length=30)),
                ('url_fuente', models.URLField(blank=True, max_length=500)),
                ('validada', models.BooleanField(default=False, help_text='Marcar solo después de contrastar la referencia con una fuente litúrgica aprobada.')),
                ('observaciones', models.TextField(blank=True)),
                ('consultada', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Referencia de lectura litúrgica',
                'verbose_name_plural': 'Referencias de lecturas litúrgicas',
                'ordering': ['fecha'],
            },
        ),
        migrations.AddIndex(
            model_name='referencialecturaliturgica',
            index=models.Index(fields=['anio_liturgico', 'ciclo_dominical'], name='core_ref_anio_ciclo_idx'),
        ),
        migrations.AddIndex(
            model_name='referencialecturaliturgica',
            index=models.Index(fields=['tiempo_liturgico', 'semana_liturgica'], name='core_ref_tiempo_sem_idx'),
        ),
    ]
