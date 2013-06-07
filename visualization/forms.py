import json
from django import forms
from django.forms.fields import ChoiceField, CharField, BooleanField, IntegerField
from django.forms.widgets import HiddenInput
from annotations.forms import CustomCheckboxSelectMultiple
from annotations.models import LabelSet, Label, LabelGroup
from images.models import Source, Value1, Value2, Value3, Value4, Value5, Metadata, Image
from lib.forms import clean_comma_separated_image_ids_field

class YearModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, Metadata):
        return Metadata.photo_date.year


class VisualizationSearchForm(forms.Form):
    class Meta:
        fields = ('value1', 'value2', 'value3',
              'value4', 'value5', 'year', 'labels', 'image_status', 'annotator')
    class Media:
        js = (
            # From app-specific static directory
            "js/VisSearchFormHelper.js",
            )
        
    def __init__(self,source_id,*args,**kwargs):

        super(VisualizationSearchForm,self).__init__(*args,**kwargs)
        source = Source.objects.filter(id=source_id)[0]

        metadatas = Metadata.objects.filter(image__source=source).distinct().dates('photo_date', 'year')
        years = []
        for metadata in metadatas:
            if metadata:
                if not metadata.year in years:
                    years.append(metadata.year)

        self.fields['year'] = ChoiceField(choices=[('',"All")] + [(year,year) for year in years],
                                          required=False)
        labelset = LabelSet.objects.filter(source=source)[0]
        self.fields['labels'] = forms.ModelChoiceField(labelset.labels.all(),
                                            empty_label="View Whole Images",
                                            required=False)
        for key, valueField, valueClass in [
                (source.key1, 'value1', Value1),
                (source.key2, 'value2', Value2),
                (source.key3, 'value3', Value3),
                (source.key4, 'value4', Value4),
                (source.key5, 'value5', Value5)
                ]:
            if key:
                choices = [('', 'All')]
                valueObjs = valueClass.objects.filter(source=source).order_by('name')
                for valueObj in valueObjs:
                    choices.append((valueObj.id, valueObj.name))
                
                self.fields[valueField] = ChoiceField(choices, label=key, required=False)

        status_choices = [('', 'All'), ('n','Needs annotation')]
        if source.enable_robot_classifier:
            status_choices.extend([('r', 'Annotated by robot'),('h', 'Annotated by human')])
        else:
            status_choices.append(('a', 'Annotated'))

        self.fields['image_status'] = forms.ChoiceField(choices=status_choices,
                                                        required=False)

        # TODO: Move these fields out of __init__()?  Seems not necessary to
        # instantiate them dynamically. -Stephen
        self.fields['annotator'] = forms.ChoiceField(choices=[(0,'Human'), (1,'Robot'), (2, 'Both')], required=False)
        self.fields['edit_metadata_view'] = forms.BooleanField(required=False)

        # TODO: Move labels, annotator, and view fields to other
        # form classes?


class ImageSpecifyForm(forms.Form):

    # Images can be specified in one of two ways. This selects which way.
    specify_method = forms.ChoiceField(
        choices=(
            ('search_keys', ''),
            ('image_ids', ''),
        ),
        widget=HiddenInput(),
    )

    specify_str = forms.CharField(widget=HiddenInput())


    # TODO: Will the field ideas below be needed anymore?

    # The search keys as a JSON-ized dictionary
    #searchKeys = forms.CharField(widget=HiddenInput())

    # Number of images, as a sanity check when using the
    # search keys.
    #num_of_images = forms.IntegerField(widget=HiddenInput())

    # The ids of the images in this search, as a
    # comma-separated string.
    #image_ids = forms.CharField(widget=HiddenInput())


    def __init__(self, *args, **kwargs):

        self.source = kwargs.pop('source')
        super(ImageSpecifyForm,self).__init__(*args, **kwargs)

    def clean_specify_str(self):

        if self.cleaned_data['specify_method'] == 'search_keys':

            # Load the dict of search keys from the string input.
            search_keys_dict_raw = json.loads(self.cleaned_data['specify_str'])
            patch_mode = (search_keys_dict_raw['labels'] is not None)

            # Get rid of empty-valued search keys.
            search_keys_dict = dict(
                [(k, search_keys_dict_raw[k])
                 for k in search_keys_dict_raw
                 if search_keys_dict_raw[k] != '']
            )
            filter_args = dict()

            # Go over each search key/value from the form input, and turn
            # those into image queryset filters.
            for k,v in search_keys_dict.iteritems():

                if k.startswith('value'):

                    # value1, value2, ..., value5
                    filter_args['metadata__'+k+'__id'] = v

                elif k == 'year':

                    filter_args['metadata__photo_date__year'] = int(v)

                elif k == 'image_status' and not patch_mode:

                    # annotation status (by human, or by robot).
                    # ONLY account for this if not searching in patch mode.
                    if self.source.enable_robot_classifier:
                        if v == 'n':
                            filter_args['status__annotatedByHuman'] = False
                            filter_args['status__annotatedByRobot'] = False
                        elif v == 'r':
                            filter_args['status__annotatedByHuman'] = False
                            filter_args['status__annotatedByRobot'] = True
                        elif v == 'h':
                            filter_args['status__annotatedByHuman'] = True
                        # else, don't filter
                    else:
                        if v == 'n':
                            filter_args['status__annotatedByHuman'] = False
                        elif v == 'a':
                            filter_args['status__annotatedByHuman'] = True
                        # else, don't filter

                elif k in ['view', 'labels', 'annotator']:

                    # these args aren't for filtering images, so don't do
                    # anything for them.
                    pass

                else:

                    # if we let in any unknown args, raise an error to be safe
                    raise ValueError("Unknown search key: {k}".format(k=k))

            self.cleaned_data['specify_str'] = filter_args

        else:  # 'image_ids'

            self.cleaned_data['specify_str'] = \
                clean_comma_separated_image_ids_field(
                    self.cleaned_data['specify_str'],
                    self.source,
                )

        return self.cleaned_data['specify_str']

    def get_images(self):
        """
        Call this after cleaning the form to get the images
        specified by the fields.
        """
        if self.cleaned_data['specify_method'] == 'search_keys':

            search_keys_as_filter_args = self.cleaned_data['specify_str']
            return Image.objects.filter(source=self.source, **search_keys_as_filter_args)

        else:  # 'image_ids'

            image_ids = self.cleaned_data['specify_str']
            return Image.objects.filter(source=self.source, pk__in=image_ids)


class ImageBatchDeleteForm(ImageSpecifyForm):
    pass

class ImageBatchDownloadForm(ImageSpecifyForm):
    pass


# Similar to VisualizationSearchForm with the difference that
# label selection appears on a multi-select checkbox form
# TODO: Merge with VisualizationSearchForm to remove redundancy

class StatisticsSearchForm(forms.Form):
    class Meta:
        fields = ('value1', 'value2', 'value3',
              'value4', 'value5', 'labels', 'groups', 'include_robot')

    def __init__(self,source_id,*args,**kwargs):
        super(StatisticsSearchForm,self).__init__(*args,**kwargs)

        # Grab the source and it's labelset
        source = Source.objects.filter(id=source_id)[0]
        labelset = LabelSet.objects.filter(source=source)[0]
        groups = LabelGroup.objects.all().distinct()

        # Get the location keys
        for key, valueField, valueClass in [
                (source.key1, 'value1', Value1),
                (source.key2, 'value2', Value2),
                (source.key3, 'value3', Value3),
                (source.key4, 'value4', Value4),
                (source.key5, 'value5', Value5)
                ]:
            if key:
                choices = [('', 'All')]
                valueObjs = valueClass.objects.filter(source=source).order_by('name')
                for valueObj in valueObjs:
                    choices.append((valueObj.id, valueObj.name))

                self.fields[valueField] = ChoiceField(choices, label=key, required=False)

        #gets all the labels
        labels = labelset.labels.all().order_by('group__id', 'name')

        # Put the label choices in order
        label_choices = \
            [(label.id, label.name) for label in labels]

        group_choices = \
            [(group.id, group.name) for group in groups]
        
        # Custom widget for label selection
        #self.fields['labels'].widget = CustomCheckboxSelectMultiple(choices=self.fields['labels'].choices)
        self.fields['labels']= forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple,
                                                         choices=label_choices, required=False)

        self.fields['groups']= forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple,
                                                         choices=group_choices, required=False)
        
        self.fields['include_robot'] = BooleanField(required=False)


