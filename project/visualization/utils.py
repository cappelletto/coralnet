import urllib
from io import BytesIO
from django.conf import settings
from django.core.files.storage import get_storage_class
from django.core.paginator import Paginator, EmptyPage, InvalidPage
from PIL import Image as PILImage
from images.models import Point


def paginate(results, items_per_page, query_args):
    paginator = Paginator(results, items_per_page)

    # Make sure page request is an int. If not, deliver first page.
    try:
        page = int(query_args.get('page', '1'))
    except ValueError:
        page = 1

    # If page request is out of range, deliver last page of results.
    try:
        page_results = paginator.page(page)
    except (EmptyPage, InvalidPage):
        page_results = paginator.page(paginator.num_pages)

    # If there are previous or next pages, construct links to them.
    # These links include GET parameters in the form of
    # ?arg1=value1&arg2=value2 etc.

    prev_page_link = None
    if page_results.has_previous():
        prev_page_query_args = query_args.copy()
        prev_page_query_args['page'] = page_results.previous_page_number()
        prev_page_link = '?' + urllib.urlencode(prev_page_query_args)

    next_page_link = None
    if page_results.has_next():
        next_page_query_args = query_args.copy()
        next_page_query_args['page'] = page_results.next_page_number()
        next_page_link = '?' + urllib.urlencode(next_page_query_args)

    return page_results, prev_page_link, next_page_link


def get_patch_path(point_id):
    point = Point.objects.get(pk=point_id)

    return settings.POINT_PATCH_FILE_PATTERN.format(
        full_image_path=point.image.original_file.name,
        point_pk=point.pk,
    )

def get_patch_url(point_id):
    return get_storage_class()().url(get_patch_path(point_id))

def generate_patch_if_doesnt_exist(point):
    """
    If this point doesn't have an image patch file yet, then
    generate one.
    :param point: Point object to generate a patch for
    :return: None
    """
    # Get the storage class, then get an instance of it.
    storage = get_storage_class()()
    # Check if patch exists for the point
    patch_relative_path = get_patch_path(point.pk)
    if storage.exists(patch_relative_path):
        return

    # Generate the patch

    # Size of patch (after scaling)
    PATCH_X = 150
    PATCH_Y = 150
    # Patch covers this proportion of the original image's greater dimension
    REDUCE_SIZE = 1.0/5.0

    original_image_relative_path = point.image.original_file.name
    original_image_file = storage.open(original_image_relative_path)
    image = PILImage.open(original_image_file)

    #determine the crop box
    max_x = point.image.original_width
    max_y = point.image.original_height
    #careful; x is the column, y is the row
    x = point.column
    y = point.row

    # TODO: The division ops here MIGHT be dangerous for Python 3, because
    # the default has changed from integer to decimal division
    patchSize = int(max(max_x,max_y)*REDUCE_SIZE)
    patchSize = (patchSize/2)*2  #force patch size to be even
    halfPatchSize = patchSize/2
    scaledPatchSize = (PATCH_X, PATCH_Y)

    # If a patch centered on (x,y) would be too far off to the left,
    # then just take a patch on the left edge of the image.
    if x - halfPatchSize < 0:
        left = 0
        right = patchSize
    # If too far to the right, take a patch on the right edge
    elif x + halfPatchSize > max_x:
        left = max_x - patchSize
        right = max_x
    else:
        left = x - halfPatchSize
        right = x + halfPatchSize

    # If too far toward the top, take a patch on the top edge
    if y - halfPatchSize < 0:
        upper = 0
        lower = patchSize
    # If too far toward the bottom, take a patch on the bottom edge
    elif y + halfPatchSize > max_y:
        upper = max_y - patchSize
        lower = max_y
    else:
        upper = y - halfPatchSize
        lower = y + halfPatchSize

    box = (left,upper,right,lower)

    # Crop the image
    region = image.crop(box)
    region = region.resize(scaledPatchSize)

    # Save the image.
    #
    # First use Pillow's save() method on an IO stream (so we don't have to
    # create a temporary file).
    # Then save the image, using the path constructed earlier and the
    # contents of the stream.
    # This approach should work with both local and remote storage.
    with BytesIO() as stream:
        region.save(stream, 'JPEG')
        storage.save(patch_relative_path, stream)