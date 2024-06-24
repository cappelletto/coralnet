# Generated by Django 4.1.10 on 2024-05-09 05:08

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('vision_backend', '0023_source_fk_restore_constraint'),
        ('sources', '0008_source_annoarea_and_pointgen_defaults'),
    ]

    operations = [
        # Repurpose the enable_robot_classifier flag to denote whether the
        # source trains its own classifiers or relies on other sources'
        # classifiers.
        # No data migration is needed.
        migrations.RenameField(
            model_name='source',
            old_name='enable_robot_classifier',
            new_name='trains_own_classifiers',
        ),
        migrations.AlterField(
            model_name='source',
            name='trains_own_classifiers',
            field=models.BooleanField(default=True, verbose_name='Source trains its own classifiers'),
        ),
        # New fields for the case of relying on other sources' classifiers.
        migrations.AddField(
            model_name='source',
            name='deployed_classifier',
            field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='deploying_sources', to='vision_backend.classifier'),
        ),
        migrations.AddField(
            model_name='source',
            name='deployed_source_id',
            field=models.BigIntegerField(null=True, blank=True),
        ),
    ]