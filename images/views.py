from datetime import date, datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db import transaction
from django.forms import ValidationError
from django.forms.models import model_to_dict
from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponseRedirect
from django.template import RequestContext

from userena.models import User
from guardian.decorators import permission_required
from guardian.shortcuts import assign
from annotations.models import LabelGroup, Label, Annotation, LabelSet
from decorators import labelset_required

from images.models import Source, Image, Metadata, Point, find_dupe_image
from images.models import get_location_value_objs
from images.forms import ImageSourceForm, ImageUploadForm, ImageDetailForm, AnnotationImportForm, ImageUploadFormBasic, LabelImportForm, PointGenForm
from images.utils import filename_to_metadata, PointGen

from os.path import splitext


def source_list(request):
    """
    Page with a list of the user's Sources.
    Redirect to the About page if the user isn't logged in or doesn't have any Sources.
    """

    if request.user.is_authenticated():
        your_sources = Source.get_sources_of_user(request.user)
        other_sources = Source.get_other_public_sources(request.user)
        
        if your_sources:
            return render_to_response('images/source_list.html', {
                'your_sources': your_sources,
                'other_sources': other_sources,
                },
                context_instance=RequestContext(request)
            )

    return HttpResponseRedirect(reverse('source_about'))

def source_about(request):
    """
    Page that explains what Sources are and how to use them.
    """

    if request.user.is_authenticated():
        if Source.get_sources_of_user(request.user):
            user_status = 'has_sources'
        else:
            user_status = 'no_sources'
    else:
        user_status = 'anonymous'

    return render_to_response('images/source_about.html', {
        'user_status': user_status,
        'public_sources': Source.get_public_sources(),
        },
        context_instance=RequestContext(request)
    )

@login_required
def source_new(request):
    """
    Page with the form to create a new Image Source.
    """

    # We can get here one of two ways: either we just got to the form
    # page, or we just submitted the form.  If POST, we submitted; if
    # GET, we just got here.
    if request.method == 'POST':
        # A form bound to the POST data
        sourceForm = ImageSourceForm(request.POST)
        pointGenForm = PointGenForm(request.POST)

        # is_valid() calls our ModelForm's clean() and checks validity
        source_form_is_valid = sourceForm.is_valid()
        point_gen_form_is_valid = pointGenForm.is_valid()

        if source_form_is_valid and point_gen_form_is_valid:
            # After calling a ModelForm's is_valid(), an instance is created.
            # We can get this instance and add a bit more to it before saving to the DB.
            newSource = sourceForm.instance
            newSource.default_point_generation_method = PointGen.args_to_db_format(**pointGenForm.cleaned_data)
            newSource.labelset = LabelSet.getEmptyLabelset()
            newSource.save()
            # Grant permissions for this source
            assign('source_admin', request.user, newSource)
            # Add a success message
            messages.success(request, 'Source successfully created.')
            # Redirect to the source's main page
            return HttpResponseRedirect(reverse('source_main', args=[newSource.id]))
        else:
            # Show the form again, with error message
            messages.error(request, 'Please correct the errors below.')
    else:
        # An unbound form (empty form)
        sourceForm = ImageSourceForm()
        pointGenForm = PointGenForm()

    # RequestContext needed for CSRF verification of POST form,
    # and to correctly get the path of the CSS file being used.
    return render_to_response('images/source_new.html', {
        'sourceForm': sourceForm,
        'pointGenForm': pointGenForm,
        },
        context_instance=RequestContext(request)
        )

def source_main(request, source_id):
    """
    Main page for a particular image source.
    """

    source = get_object_or_404(Source, id=source_id)

    # Is there a way to make the perm check in a permission_required decorator?
    # Having to manually code the redirect to login is slightly annoying.
    if source.visible_to_user(request.user):
        members = source.get_members()
        all_images = source.get_all_images()
        latest_images = all_images.order_by('-upload_date')[:5]

        stats = dict(
            num_images=all_images.count(),
            num_annotations=Annotation.objects.filter(image__source=source).count(),
        )

        return render_to_response('images/source_main.html', {
            'source': source,
            'loc_keys': ', '.join(source.get_key_list()),
            'members': members,
            'latest_images': latest_images,
            'stats': stats,
            },
            context_instance=RequestContext(request)
            )
    else:
        return HttpResponseRedirect('%s?next=%s' % (settings.LOGIN_URL, request.path))

# Must have the 'source_admin' permission for the Source whose id is source_id
@permission_required('source_admin', (Source, 'id', 'source_id'))
def source_edit(request, source_id):
    """
    Edit an image source: name, visibility, location keys, etc.
    """

    source = get_object_or_404(Source, id=source_id)

    if request.method == 'POST':

        # Cancel
        cancel = request.POST.get('cancel', None)
        if cancel:
            messages.success(request, 'Edit cancelled.')
            return HttpResponseRedirect(reverse('source_main', args=[source_id]))

        # Submit
        sourceForm = ImageSourceForm(request.POST, instance=source)
        pointGenForm = PointGenForm(request.POST)

        source_form_is_valid = sourceForm.is_valid()
        point_gen_form_is_valid = pointGenForm.is_valid()

        if source_form_is_valid and point_gen_form_is_valid:
            editedSource = sourceForm.instance
            editedSource.default_point_generation_method = PointGen.args_to_db_format(**pointGenForm.cleaned_data)
            editedSource.save()
            messages.success(request, 'Source successfully edited.')
            return HttpResponseRedirect(reverse('source_main', args=[source_id]))
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # Just reached this form page
        sourceForm = ImageSourceForm(instance=source)
        pointGenForm = PointGenForm(source=source)

    return render_to_response('images/source_edit.html', {
        'source': source,
        'editSourceForm': sourceForm,
        'pointGenForm': pointGenForm,
        },
        context_instance=RequestContext(request)
        )


@transaction.commit_on_success    # This is supposed to make sure Metadata, Value, and Image objects only save if whole form passes
@permission_required('source_admin', (Source, 'id', 'source_id'))
def image_upload(request, source_id):
    """
    View for uploading images to a source.

    If one file in a multi-file upload fails to upload,
    none of the images in the upload are saved.
    """

    source = get_object_or_404(Source, id=source_id)
    uploadedImages = []
    duplicates = 0
    imagesUploaded = 0

    if request.method == 'POST':
        form = ImageUploadForm(request.POST, request.FILES, source=source)

        # TODO: Figure out why it's getting 500 (NoneType object is not subscriptable)
        # on certain combinations of files.  For example, bmp + cpc in one upload.
        if form.is_valid():

            encountered_error = False

            # Need getlist instead of simply request.FILES, in order to handle
            # multiple files.
            fileList = request.FILES.getlist('files')
            dupe_option = form.cleaned_data['skip_or_replace_duplicates']

            for file in fileList:

                filenameWithoutExtension = splitext(file.name)[0]

                if form.cleaned_data['has_data_from_filenames']:

                    try:
                        metadataDict = filename_to_metadata(filenameWithoutExtension, source)

                    #TODO: Have far more robust exception/error checking, which checks
                    # not just the filename parsing, but also the validity of the image files
                    # themselves.
                    # The idea is you need to call is_valid() with each file somehow,
                    # because it only checks one file per call.
                    # Perhaps this is a good time to jump ship and go with an AJAX form which
                    # sends files to Django one by one.
                    except (ValueError, StopIteration):
                        messages.error(request, 'Upload failed - Error when parsing the filename %s for metadata.' % file.name)
                        encountered_error = True
                        transaction.rollback()
                        uploadedImages = []
                        duplicatesDeleted = 0
                        break

                    # Detect duplicate images and handle them
                    dupe = find_dupe_image(source, **metadataDict)
                    if dupe:
                        duplicates += 1
                        if dupe_option == 'skip':
                            # Skip uploading this file.
                            continue
                        elif dupe_option == 'replace':
                            # Proceed uploading this file, and delete the dupe.
                            dupe.delete()

                    # Set the metadata
                    valueDict = get_location_value_objs(source, metadataDict['values'], createNewValues=True)
                    photoDate = date(year = int(metadataDict['year']),
                                     month = int(metadataDict['month']),
                                     day = int(metadataDict['day']))
                    metadata = Metadata(name=filenameWithoutExtension,
                                        photo_date=photoDate,
                                        **valueDict)

                else:
                    metadata = Metadata(name=filenameWithoutExtension)

                metadata.save()

                point_generation_method = source.default_point_generation_method

                # Save the image into the DB
                img = Image(original_file=file,
                        uploaded_by=request.user,
                        point_generation_method=point_generation_method,
                        metadata=metadata,
                        source=source)
                img.save()

                # Generate points
                if point_generation_method:
                    points = PointGen.generate_points(img, **PointGen.db_to_args_format(point_generation_method))

                    # Save points
                    for pt in points:
                        Point(row=pt['row'],
                              column=pt['column'],
                              point_number=pt['point_number'],
                              image=img,
                        ).save()

                # Up to 5 uploaded images will be shown
                # upon successful upload.

                # Prepend to list, so most recent image comes first
                uploadedImages.insert(0, img)
                if len(uploadedImages) > 5:
                    uploadedImages = uploadedImages[:5]

                imagesUploaded += 1

            if not encountered_error:

                # Construct success message.
                if dupe_option == 'replace':
                    duplicate_msg_base = "%d duplicates replaced."
                else:
                    duplicate_msg_base = "%d duplicates skipped."

                if duplicates > 0:
                    duplicate_msg = duplicate_msg_base % duplicates
                else:
                    duplicate_msg = ''
                    
                uploaded_msg = "%d images uploaded." % imagesUploaded
                success_msg = uploaded_msg + ' ' + duplicate_msg

                messages.success(request, success_msg)

        else:
            messages.error(request, 'Please correct the errors below.')


    # GET
    else:
        form = ImageUploadForm(source=source)

    return render_to_response('images/image_upload.html', {
        'source': source,
        'imageUploadForm': form,
        'uploadedImages': uploadedImages,
        },
        context_instance=RequestContext(request)
    )


# TODO: Make custom permission_required_blahblah decorators.
# For example, based on an image id, see if the user has permission to it. Make that permission_required_image.
#@permission_required('source_admin', (Source, 'id', 'Image.objects.get(pk=image_id).source.id'))
#def image_detail(request, image_id):
@permission_required('source_admin', (Source, 'id', 'source_id'))
def image_detail(request, image_id, source_id):
    """
    View for seeing an image's full size and details/metadata.
    """

    image = get_object_or_404(Image, id=image_id)
    #source = get_object_or_404(Source, Image.objects.get(pk=image_id).source.id)
    source = get_object_or_404(Source, id=source_id)
    metadata = image.metadata

    # Get the metadata fields (including the right no. of keys for the source)
    # and organize into fieldsets.  The image detail form already has this
    # logic, so let's just borrow the form's functionality...
    imageDetailForm = ImageDetailForm(source=source, initial=model_to_dict(metadata))
    fieldsets = imageDetailForm.fieldsets

    # ...But we don't need the form's "Other" value fields.
    # (Code note: [:] creates a copy of the list, so we're not iterating over the same list we're removing things from)
    for field in fieldsets['keys'][:]:
        if field.name.endswith('_other'):
            fieldsets['keys'].remove(field)

    detailsets = dict()
    for key, fieldset in fieldsets.items():
        detailsets[key] = [dict(label=field.label,
                                name=field.name,
                                value=getattr(metadata, field.name))
                         for field in fieldset]

    # Default max viewing width
    # Feel free to change the constant according to the page layout.
    scaled_width = min(image.original_width, 1000)

    return render_to_response('images/image_detail.html', {
        'source': source,
        'image': image,
        'metadata': metadata,
        'detailsets': detailsets,
        'scaled_width': scaled_width,
        },
        context_instance=RequestContext(request)
    )

@transaction.commit_on_success   # "Other" location values are only saved if form is error-less
@permission_required('source_admin', (Source, 'id', 'source_id'))
def image_detail_edit(request, image_id, source_id):
    """
    Edit image details.
    """

    image = get_object_or_404(Image, id=image_id)
    metadata = get_object_or_404(Metadata, id=image.metadata_id)
    source = get_object_or_404(Source, id=source_id)

    if request.method == 'POST':

        # Cancel
        cancel = request.POST.get('cancel', None)
        if cancel:
            messages.success(request, 'Edit cancelled.')
            return HttpResponseRedirect(reverse('image_detail', args=[source_id, image_id]))

        # Submit
        form = ImageDetailForm(request.POST, instance=metadata, source=source)

        if form.is_valid():
            form.save()
            messages.success(request, 'Image successfully edited.')
            return HttpResponseRedirect(reverse('image_detail', args=[source_id, image_id]))
        else:
            transaction.rollback()  # Don't save "Other" location values to database
            messages.error(request, 'Please correct the errors below.')
    else:
        # Just reached this form page
        form = ImageDetailForm(instance=metadata, source=source)

    return render_to_response('images/image_detail_edit.html', {
        'source': source,
        'image': image,
        'imageDetailForm': form,
        },
        context_instance=RequestContext(request)
        )

#TODO: check permissions
def import_groups(request, fileLocation):
    file = open(fileLocation, 'r') #opens the file for reading
    for line in file:
        line = line.replace("; ", ';')
        words = line.split(';')

        #creates a label object and stores it in the database
        group = LabelGroup(name=words[0], code=words[1])
        group.save()
    file.close()
    

@transaction.commit_on_success
def import_labels(request, source_id):

    source = get_object_or_404(Source, id=source_id)

    #creates a new labelset for the source
    labelset = LabelSet()
    labelset.save()

    labelsImported = 0
    newLabels = 0
    existingLabels = 0

    if request.method == 'POST':
        labelImportForm = LabelImportForm(request.POST, request.FILES)

        if labelImportForm.is_valid():

            file = request.FILES['labels_file']

            # We'll assume we're using an InMemoryUploadedFile, as opposed to a filename of a temp-disk-storage file.
            # If we encounter a case where we have a filename, use the below:
            #file = open(fileLocation, 'r') #opens the file for reading

            #iterates over each line in the file and processes it
            for line in file:
                #sanitizes and splits apart the string/line
                line = line.strip().replace("; ", ';')
                words = line.split(';')

                # Ignore blank lines
                if line == '':
                    continue

                labelName, labelCode, groupName = words[0], words[1], words[2]
                group = get_object_or_404(LabelGroup, name=groupName)

                # (1) Create a new label, (2) use an existing label,
                # or (3) throw an error if a file label and existing
                # label of the same code don't match.
                try:
                    existingLabel = Label.objects.get(code=labelCode)
                except Label.DoesNotExist:
                    #creates a label object and stores it in the database
                    label = Label(name=labelName, code=labelCode, group=group)
                    label.save()
                    newLabels += 1
                else:
                    if (existingLabel.name == labelName and
                        existingLabel.code == labelCode and
                        existingLabel.group == group
                    ):
                        label = existingLabel
                        existingLabels += 1
                    else:
                        raise ValidationError(
                            """Our database already has a label with code %s,
                            but it doesn't match yours.
                            Ours: %s, %s, %s
                            Yours: %s, %s, %s""" % (
                            labelCode,
                            existingLabel.name, existingLabel.code, existingLabel.group.name,
                            labelName, labelCode, groupName
                            ))

                #adds label to the labelset
                labelset.labels.add(label)
                labelsImported += 1

            file.close() #closes file since we're done

            labelset.description = labelImportForm.cleaned_data['labelset_description']
            labelset.save()
            source.labelset = labelset
            source.save()

            success_msg = "%d labels imported: %d new labels and %d existing labels." % (labelsImported, newLabels, existingLabels)
            messages.success(request, success_msg)
            return HttpResponseRedirect(reverse('source_main', args=[source_id]))

        else:
            messages.error(request, 'Please correct the errors below.')

    # GET
    else:
        labelImportForm = LabelImportForm()

    return render_to_response('images/label_import.html', {
            'labelImportForm': labelImportForm,
            'source': source,
            },
            context_instance=RequestContext(request)
    )


def get_image_identifier(valueList, year):
    """
    Use the location values and the year to build a string identifier for an image:
    Shore1;Reef5;...;2008
    """
    return ';'.join(valueList + [year])

def annotations_file_to_python(annoFile, source):
    """
    Takes: an annotations file

    Returns: the Pythonized annotations:
    A dictionary like this:
    {'Shore1;Reef3;...;2008': [{'row':'695', 'col':'802', 'label':'POR'},
                               {'row':'284', 'col':'1002', 'label':'ALG'},
                               ...],
     'Shore2;Reef5;...;2009': [...]
     ... }

    Checks for: correctness of file formatting, i.e. all words/tokens are there on each line
    (will throw an error otherwise)
    """

    # We'll assume annoFile is an InMemoryUploadedFile, as opposed to a filename of a temp-disk-storage file.
    # If we encounter a case where we have a filename, use the below:
    #annoFile = open(annoFile, 'r')

    parseErrorMsg = 'Error parsing line %d in the annotations file:\n%s'
    
    numOfKeys = source.num_of_keys()

    # The order of the words/tokens is encoded here.  If the order ever
    # changes, we should only have to change this part.
    wordsFormat = ['value'+str(i) for i in range(1, numOfKeys+1)]
    wordsFormat += ['date', 'row', 'col', 'label']
    numOfWordsExpected = len(wordsFormat)

    annotationsDict = dict()

    for lineNum, line in enumerate(annoFile, 1):

        # Sanitize the line and split it into words/tokens.
        # Allow for separators of ";" or "; "
        cleanedLine = line.strip().replace("; ", ';')
        words = cleanedLine.split(';')

        # Check that the basic line formatting is right, i.e. all words/tokens are there.
        if len(words) != numOfWordsExpected:
            raise ValueError(parseErrorMsg % (lineNum, line))

        # Encode the line data into a dictionary: {'value1':'Shore2', 'row':'575', ...}
        lineData = dict(zip(wordsFormat, words))

        # Use the location values and the year to build a string identifier for the image, such as:
        # Shore1;Reef5;...;2008
        # We'll assume the year is the first 4 characters of the date.
        valueList = [lineData['value'+str(i)] for i in range(1,numOfKeys+1)]
        year = lineData['date'][:4]
        imageIdentifier = get_image_identifier(valueList, year)

        # Add/update a dictionary entry for the image with this identifier.
        # The dict entry's value is a list of labels.  Each label is a dict:
        # {'row':'484', 'col':'320', 'label':'POR'}
        if not annotationsDict.has_key(imageIdentifier):
            annotationsDict[imageIdentifier] = []
            
        annotationsDict[imageIdentifier].append(
            dict(row=lineData['row'], col=lineData['col'], label=lineData['label'])
        )

    annoFile.close()

    return annotationsDict
        

# Below: The old equivalent of annotations_file_to_python + database insertion.
# Before removing this (and the URL associated with this method), check that the existing
# code covers everything that this method tries to do.

#def import_annotations(request, source_id, fileLocation):
#    source = get_object_or_404(Source, id=source_id)
#    file = open(fileLocation, 'r') #opens the file for reading
#    count = 0 #keeps track of total points in one image
#    prevImg = None #keeps track of the image processed on the previous iteration
#
#    #iterate over each line in the file and processes it
#    for line in file:
#        #sanitizes and splits apart the string/line
#        line = line.replace("; ", ';')
#        words = line.split(';')
#
#        #gets the 5 values that would describe the image
#        value1 = get_object_or_404(Value1, name=words[0], source=source)
#        value2 = get_object_or_404(Value2, name=words[1], source=source)
#        value3 = get_object_or_404(Value3, name=words[2], source=source)
#        value4 = get_object_or_404(Value4, name=words[3], source=source)
#        value5 = get_object_or_404(Value5, name=words[4], source=source)
#
#        #there should be one unique image that has the 5 values above, so get that image
#        metadata = get_object_or_404(Metadata, value1=value1,
#                                     value2=value2, value3=value3,
#                                     value4=value4, value5=value5)
#        image = get_object_or_404(Image, metadata=metadata)
#
#        #check if this is the first image being processed
#        if prevImg is None:
#            prevImg = image
#
#        #if the previous image was the same as this one, increment the point count
#        if prevImg == image:
#            count += 1
#        else:
#            count = 1
#
#        prevImg = image
#
#        #gets the label for the point, assumes it's already in the database
#        label = get_object_or_404(Label, name=words[8])
#        get_object_or_404(LabelSet, sources=source, labels=label) #check that label is in labelset
#        row = int(words[6])
#        col = int(words[7])
#
#        #creates a point object and saves it in the database
#        point = Point(row=row, col=col, point_number=count, image=image)
#        point.save()
#
#        #creates an annotation object and saves it in the database
#        annotation = Annotation(annotation_date=datetime.now(), point=point, image=image,
#                                label=label, source=source)
#        annotation.save()
#
#        #end for loop
#
#    file.close() #closes the file since we're done

    
@transaction.commit_on_success
@labelset_required('source_id', 'You need to create a labelset for your source before you can import annotations.')
@permission_required('source_admin', (Source, 'id', 'source_id'))
def annotation_import(request, source_id):

    source = get_object_or_404(Source, id=source_id)
    importedUser = User.objects.get(username="Imported")

    uploadedImages = []
    imagesUploaded = 0
    annotationsImported = 0

    if request.method == 'POST':
        annotationsForm = AnnotationImportForm(request.POST, request.FILES)
        imageForm = ImageUploadFormBasic(request.POST, request.FILES)

        # TODO: imageForm.is_valid() just validates the first image file.
        # Make sure all image files are checked to be valid images.
        if annotationsForm.is_valid() and imageForm.is_valid():

            annoFile = request.FILES['annotations_file']
            
            annotationData = annotations_file_to_python(annoFile, source)

            imageFiles = request.FILES.getlist('files')
            encountered_error = False

            for imageFile in imageFiles:

                filenameWithoutExtension = splitext(imageFile.name)[0]

                try:
                    metadataDict = filename_to_metadata(filenameWithoutExtension, source)
                except ValueError:
                    messages.error(request, 'Upload failed - Error when parsing the filename %s for metadata.' % imageFile.name)
                    encountered_error = True
                    uploadedImages = []
                    transaction.rollback()
                    break

                # Set the metadata
                valueDict = get_location_value_objs(source, metadataDict['values'], createNewValues=True)
                photoDate = date(year = int(metadataDict['year']),
                                 month = int(metadataDict['month']),
                                 day = int(metadataDict['day']))
                metadata = Metadata(name=filenameWithoutExtension,
                                    photo_date=photoDate,
                                    **valueDict)
                metadata.save()

                # Use the location values and the year to build a string identifier for the image, such as:
                # Shore1;Reef5;...;2008
                imageIdentifier = get_image_identifier(metadataDict['values'], metadataDict['year'])

                # Use the identifier as the index into the annotation file's data.
                imageAnnotations = annotationData[imageIdentifier]

                img = Image(original_file=imageFile,
                        uploaded_by=request.user,
                        point_generation_method=PointGen.args_to_db_format(
                            point_generation_type=PointGen.Types.IMPORTED,
                            imported_number_of_points=len(imageAnnotations)
                        ),
                        metadata=metadata,
                        source=source)
                img.save()

                # Iterate over this image's annotations.
                pointNum = 1
                for anno in imageAnnotations:

                    # Save the Point in the database.
                    point = Point(row=anno['row'], column=anno['col'], point_number=pointNum, image=img)
                    point.save()

                    # Get the Label object for the annotation's label.
                    # TODO: Gracefully handle the case when a label's not found.
                    try:
                        label = Label.objects.get(code=anno['label'])
                    except:
                        raise ValidationError('Database either has no label or multiple labels with code %s.' % anno['label'])

                    # TODO: Check that the Label object is actually in this Source's labelset.
                    #LabelSet.objects.get(sources=source, labels=label)

                    # Save the Annotation in the database. Leave the user as null; we can display
                    # a null annotator as "annotation was imported".
                    annotation = Annotation(user=importedUser,
                                            point=point, image=img, label=label, source=source)
                    annotation.save()

                    annotationsImported += 1
                    pointNum += 1

                imagesUploaded += 1

                # Up to 5 uploaded images will be shown upon successful upload.
                uploadedImages.insert(0, img)
                if len(uploadedImages) > 5:
                    uploadedImages = uploadedImages[:5]
                

            if not encountered_error:

                uploaded_msg = "%d images uploaded." % imagesUploaded
                annotations_msg = "%d annotations imported." % annotationsImported
                success_msg = uploaded_msg + ' ' + annotations_msg
                
                messages.success(request, success_msg)
            
        else:
            messages.error(request, 'Please correct the errors below.')

    # GET
    else:
        annotationsForm = AnnotationImportForm()
        imageForm = ImageUploadFormBasic()

    return render_to_response('images/image_and_annotation_upload.html', {
        'source': source,
        'annotationsUploadForm': annotationsForm,
        'imageUploadForm': imageForm,
        'uploadedImages': uploadedImages,
        },
        context_instance=RequestContext(request)
    )
