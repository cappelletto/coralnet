# Generated by Django 4.1.10 on 2024-05-05 03:58

from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add a default for image_annotation_area to serve as a useful example,
    and change the default for default_point_generation_method from 200 points
    (based mainly on Moorea study in early 2010s) to 30 (current median for
    public sources).
    """

    dependencies = [
        ('sources', '0007_source_annotation_area_non_null'),
    ]

    operations = [
        migrations.AlterField(
            model_name='source',
            name='default_point_generation_method',
            field=models.CharField(default='m_30', max_length=50, verbose_name='Point generation method'),
        ),
        migrations.AlterField(
            model_name='source',
            name='image_annotation_area',
            field=models.CharField(default='0;100;0;100', max_length=50, verbose_name='Default image annotation area'),
        ),
    ]