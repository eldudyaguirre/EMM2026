from django.db import migrations, models


def copiar_capodastro_original(apps, schema_editor):
    RepertorioServicio = apps.get_model('core', 'RepertorioServicio')
    db_alias = schema_editor.connection.alias
    for entrada in RepertorioServicio.objects.using(db_alias).select_related('cancion').iterator():
        cancion = entrada.cancion
        entrada.usa_capodastro = bool(cancion.usa_capodastro)
        entrada.traste_capodastro = cancion.traste_capodastro if cancion.usa_capodastro else None
        entrada.save(update_fields=['usa_capodastro', 'traste_capodastro'], using=db_alias)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_repertorio_servicio'),
    ]

    operations = [
        migrations.AddField(
            model_name='repertorioservicio',
            name='usa_capodastro',
            field=models.BooleanField(
                default=False,
                help_text='Indica si esta versión del repertorio usa capodastro.',
            ),
        ),
        migrations.AddField(
            model_name='repertorioservicio',
            name='traste_capodastro',
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text='Traste del capodastro para este servicio, independiente de la canción original.',
            ),
        ),
        migrations.RunPython(copiar_capodastro_original, migrations.RunPython.noop),
    ]
