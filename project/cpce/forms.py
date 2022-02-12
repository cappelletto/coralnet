from django.core.exceptions import ValidationError
from django.forms import Form
from django.forms.fields import BooleanField, CharField, ChoiceField
from django.forms.widgets import HiddenInput, RadioSelect, TextInput
from django.utils.safestring import mark_safe

from images.models import Source
from upload.forms import MultipleFileField, MultipleFileInput
from upload.utils import text_file_to_unicode_stream
from .utils import get_previous_cpcs_status, labelset_has_plus_code


class CpcImportForm(Form):
    cpc_files = MultipleFileField(
        label='CPC files',
        # Multi-file input whose dialog only allows selecting .cpc
        widget=MultipleFileInput(attrs=dict(accept='.cpc')),
        error_messages=dict(required="Please select one or more CPC files."),
    )
    plus_notes = BooleanField(
        label="Support CPCe Notes codes using + as a separator",
        required=False,
    )

    def __init__(self, source, *args, **kwargs):
        kwargs['initial'] = dict(
            # Only check the plus notes option by default if the labelset
            # has codes with + in them. Otherwise, the uploader probably
            # didn't intend to use plus codes, and any Notes present in the
            # CPC files would make the upload fail.
            plus_notes=(
                source.labelset and labelset_has_plus_code(source.labelset)),
        )
        super().__init__(*args, **kwargs)

    def clean_cpc_files(self):
        """
        Check for extensions of .cpc. This isn't foolproof, but it can
        catch simple file selection mistakes.
        """
        cpc_files = self.cleaned_data['cpc_files']

        for cpc_file in cpc_files:
            if not cpc_file.name.endswith('.cpc'):
                raise ValidationError(
                    "This is not a CPC file: {fn}".format(fn=cpc_file.name))

        return self.cleaned_data['cpc_files']

    def get_cpc_names_and_streams(self):
        cpc_names_and_streams = []
        for cpc_file in self.cleaned_data['cpc_files']:
            cpc_unicode_stream = text_file_to_unicode_stream(cpc_file)
            cpc_names_and_streams.append((cpc_file.name, cpc_unicode_stream))
        return cpc_names_and_streams


class CpcExportForm(Form):
    annotation_filter = None  # See __init__()
    override_filepaths = None  # See __init__()

    local_image_dir = CharField(
        label="Folder with images",
        max_length=Source._meta.get_field('cpce_image_dir').max_length,
        widget=TextInput(attrs={'class': 'cpc-filepath'}))
    local_code_filepath = CharField(
        label="Code file",
        max_length=Source._meta.get_field('cpce_code_filepath').max_length,
        widget=TextInput(attrs={'class': 'cpc-filepath'}))

    label_mapping = ChoiceField(
        label="Map CoralNet label codes to",
        choices=(
            ('id_only',
             "ID field only"),
            ('id_and_notes',
             "ID and Notes fields (using + character as a separator)"),
        ),
        widget=RadioSelect,
    )

    def __init__(self, source, image_results, *args, **kwargs):
        has_plus_code = (
            source.labelset and labelset_has_plus_code(source.labelset))
        kwargs['initial'] = dict(
            local_image_dir=source.cpce_image_dir,
            local_code_filepath=source.cpce_code_filepath,
            # Only use Notes by default if the labelset has codes with + in
            # them. Otherwise, the user probably didn't intend to use
            # the ID+Notes concat feature, and if there were any
            # previously-uploaded CPC files which contained Notes, those
            # Notes would be excluded from this export.
            label_mapping='id_and_notes' if has_plus_code else 'id_only',
        )

        super().__init__(*args, **kwargs)

        # annotation_filter

        if source.confidence_threshold == 100:

            # Don't need to show this field, since there can be no unconfirmed
            # annotations above 100% confidence.
            self.fields['annotation_filter'] = CharField(
                widget=HiddenInput(), initial='confirmed_only')

        else:

            confirmed_and_confident_label = (
                f"Confirmed annotations AND Unconfirmed annotations"
                f" above the machine confidence threshold of"
                f" {source.confidence_threshold}%")

            self.fields['annotation_filter'] = ChoiceField(
                label="Annotations to include",
                choices=(
                    ('confirmed_only', "Confirmed annotations only"),
                    ('confirmed_and_confident', confirmed_and_confident_label),
                ),
                initial='confirmed_only',
                widget=RadioSelect,
            )

        # override_filepaths

        override_filepaths_kwargs = dict(
            label="Use CPCe environment info from",
            initial='no',
            widget=RadioSelect,
        )
        previous_cpcs_status = get_previous_cpcs_status(image_results)

        if previous_cpcs_status == 'all':

            override_filepaths_kwargs['choices'] = (
                ('no', "Previously-uploaded CPC files"),
                ('yes', "The two fields below"),
            )
            self.fields['override_filepaths'] = ChoiceField(
                **override_filepaths_kwargs)
            self.previous_cpcs_help_text = mark_safe(
               "<strong>All of the images</strong> in this search"
               " have previously-uploaded CPC files available."
               " When exporting to CPC, the previous notes and header values"
               " will be preserved."
               " You may decide what to do with the CPCe environment info"
               " below. Click the '?' help button for more information.")

        elif previous_cpcs_status == 'some':

            override_filepaths_kwargs['choices'] = (
                ('no', "Previously-uploaded CPC files (if present),"
                       " otherwise the two fields below"),
                ('yes', "The two fields below (for the whole image set)"),
            )
            self.fields['override_filepaths'] = ChoiceField(
                **override_filepaths_kwargs)
            self.previous_cpcs_help_text = mark_safe(
                "<strong>Some of the images</strong> in this search"
                " have previously-uploaded CPC files available."
                " When exporting to CPC, the previous notes and header values"
                " will be preserved."
                " You may decide what to do with the CPCe environment info"
                " below. Click the '?' help button for more information.")

        else:

            # 'none'
            # Don't need to show this field, since there are no previous
            # filepaths to override.
            self.fields['override_filepaths'] = CharField(
                widget=HiddenInput(), initial='no')
            self.previous_cpcs_help_text = mark_safe(
                "<strong>None of the images</strong> in this search"
                " have previously-uploaded CPC files available."
                " They will use the CPCe environment info in the text fields"
                " below, and will not have notes or header values."
                " Click the '?' help button for more information.")

        self.order_fields([
            'override_filepaths', 'local_code_filepath', 'local_image_dir',
            'annotation_filter', 'label_mapping'])
