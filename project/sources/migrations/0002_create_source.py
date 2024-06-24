# Generated by Django 4.1.10 on 2024-04-17 03:07

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('labels', '0004_more_concise_regex_validators'),
        ('sources', '0001_initial'),
    ]

    state_operations = [
        migrations.CreateModel(
            name='Source',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200, unique=True)),
                ('visibility', models.CharField(choices=[('b', 'Public'), ('v', 'Private')], default='b', max_length=1)),
                ('create_date', models.DateTimeField(auto_now_add=True, verbose_name='Date created')),
                ('description', models.TextField()),
                ('affiliation', models.CharField(max_length=200)),
                ('key1', models.CharField(default='Aux1', max_length=50, verbose_name='Aux. metadata 1')),
                ('key2', models.CharField(default='Aux2', max_length=50, verbose_name='Aux. metadata 2')),
                ('key3', models.CharField(default='Aux3', max_length=50, verbose_name='Aux. metadata 3')),
                ('key4', models.CharField(default='Aux4', max_length=50, verbose_name='Aux. metadata 4')),
                ('key5', models.CharField(default='Aux5', max_length=50, verbose_name='Aux. metadata 5')),
                ('default_point_generation_method', models.CharField(default='m_200', help_text="When we create annotation points for uploaded images, this is how we'll generate the point locations. Note that if you change this setting later on, it will NOT apply to images that are already uploaded.", max_length=50, verbose_name='Point generation method')),
                ('image_annotation_area', models.CharField(help_text="This defines a rectangle of the image where annotation points are allowed to be generated.\nFor example, X boundaries of 10% and 95% mean that the leftmost 10% and the rightmost 5% of the image will not have any points. Decimals like 95.6% are allowed.\nLater, you can also set these boundaries as pixel counts on a per-image basis; for images that don't have a specific value set, these percentages will be used.", max_length=50, null=True, verbose_name='Default image annotation area')),
                ('cpce_code_filepath', models.CharField(default='', max_length=1000, verbose_name='Local absolute path to the CPCe code file')),
                ('cpce_image_dir', models.CharField(default='', help_text='Ending slash can be present or not', max_length=1000, verbose_name='Local absolute path to the directory with image files')),
                ('confidence_threshold', models.IntegerField(default=100, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)], verbose_name='Confidence threshold (%)')),
                ('enable_robot_classifier', models.BooleanField(default=True, help_text="With this option on, the automatic classification system will go through your images and add unconfirmed annotations to them. Then when you enter the annotation tool, you will be able to start from the system's suggestions instead of from a blank slate.", verbose_name='Enable robot classifier')),
                ('feature_extractor_setting', models.CharField(choices=[('efficientnet_b0_ver1', 'EfficientNet (default)'), ('vgg16_coralnet_ver1', 'VGG16 (legacy)')], default='efficientnet_b0_ver1', max_length=50, verbose_name='Feature extractor')),
                ('longitude', models.CharField(blank=True, max_length=20)),
                ('latitude', models.CharField(blank=True, max_length=20)),
                ('labelset', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='labels.labelset')),
            ],
            options={
                'permissions': (('source_view', 'View'), ('source_edit', 'Edit'), ('source_admin', 'Admin')),
            },
        ),
    ]

    operations = [
        # We are moving the Source model from the images app to the sources
        # app, and to achieve that, we:
        # - Define a state-only model creation (i.e. doesn't actually
        #   create a Postgres table) in this app: in sources 0002 (this file)
        # - Update any images.Source foreign keys to sources.Source, and
        #   disable those FKs' constraints temporarily: in annotations 0024,
        #   calcification 0003, images 0037, jobs 0016, sources 0003,
        #   vision_backend 0022
        # - Define a database-only rename of the Postgres table from
        #   images_source to sources_source (DB-only so that Django doesn't
        #   detect images.Source and sources.Source as having the same table
        #   name): in images 0038
        # - Re-enable Source FKs' constraints: in annotations 0025,
        #   calcification 0004, images 0039, jobs 0017, sources 0004,
        #   vision_backend 0023
        # - Data-migrate the Source ContentType to change its app label,
        #   to port over our existing Source permissions: in sources 0005
        # - Define a state-only model deletion (i.e. doesn't actually
        #   delete a Postgres table) in the images app: images 0040
        migrations.SeparateDatabaseAndState(state_operations=state_operations),
    ]