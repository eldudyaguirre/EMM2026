from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0009_lider_grupo'),
    ]

    operations = [
        migrations.AddField(
            model_name='perfil',
            name='debe_cambiar_password',
            field=models.BooleanField(default=True, verbose_name='Debe cambiar contraseña al ingresar'),
        ),
    ]
