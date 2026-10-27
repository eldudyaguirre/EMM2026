from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('core', '0008_agregar_instrumento_ninguno')]
    operations = [migrations.AddField(model_name='grupo', name='lider', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='grupos_liderados', to='core.perfil', verbose_name='Líder del grupo'))]
