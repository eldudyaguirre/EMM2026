from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('core', '0013_merge_password_y_capodastro')]
    operations = [
        migrations.CreateModel(
            name='LecturaLiturgica',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dia', models.PositiveSmallIntegerField()),
                ('mes', models.PositiveSmallIntegerField()),
                ('ciclo', models.CharField(choices=[('F', 'Celebración fija'), ('I', 'Ferial I'), ('II', 'Ferial II'), ('A', 'Dominical A'), ('B', 'Dominical B'), ('C', 'Dominical C')], default='F', max_length=2)),
                ('fecha_especifica', models.DateField(blank=True, help_text='Para solemnidades móviles u otras excepciones.', null=True)),
                ('nombre_celebracion', models.CharField(blank=True, max_length=200)),
                ('primera_lectura', models.TextField(blank=True)), ('salmo', models.TextField(blank=True)),
                ('segunda_lectura', models.TextField(blank=True)), ('aclamacion', models.TextField(blank=True)),
                ('evangelio', models.TextField(blank=True)), ('fecha_fuente', models.DateField(blank=True, null=True)),
                ('url_fuente', models.URLField(blank=True, max_length=500)), ('actualizado', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['mes', 'dia', 'ciclo'], 'verbose_name': 'Lectura litúrgica', 'verbose_name_plural': 'Lecturas litúrgicas'},
        ),
        migrations.AddConstraint(model_name='lecturaliturgica', constraint=models.UniqueConstraint(condition=models.Q(('fecha_especifica__isnull', True)), fields=('dia', 'mes', 'ciclo'), name='uniq_lectura_dia_mes_ciclo')),
        migrations.AddIndex(model_name='lecturaliturgica', index=models.Index(fields=['fecha_especifica'], name='core_lectur_fecha_e5b6e2_idx')),
        migrations.AddIndex(model_name='lecturaliturgica', index=models.Index(fields=['mes', 'dia'], name='core_lectur_mes_6b5b8f_idx')),
    ]
