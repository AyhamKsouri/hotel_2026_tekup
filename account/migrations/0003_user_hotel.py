import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0002_alter_notification_id_alter_user_id'),
        ('gestion_hotel', '0005_hotel_description_hotel_image_couple_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='hotel',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='staff', to='gestion_hotel.hotel', verbose_name='hôtel'),
        ),
    ]
