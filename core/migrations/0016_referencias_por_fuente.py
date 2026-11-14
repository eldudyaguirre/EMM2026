from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0015_referencia_lectura_liturgica')]

    operations = [
        migrations.AlterField(
            model_name='referencialecturaliturgica',
            name='fecha',
            field=models.DateField(),
        ),
        migrations.AddConstraint(
            model_name='referencialecturaliturgica',
            constraint=models.UniqueConstraint(fields=('fecha', 'fuente'), name='uniq_ref_fecha_fuente'),
        ),
    ]
