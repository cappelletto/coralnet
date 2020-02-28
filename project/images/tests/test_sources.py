from __future__ import unicode_literals
from django.shortcuts import resolve_url
from django.urls import reverse
from django.utils import timezone

from annotations.model_utils import AnnotationAreaUtils
from images.model_utils import PointGen
from images.models import Source
from lib.tests.utils import BasePermissionTest, ClientTest


class PermissionTest(BasePermissionTest):

    def test_source_about(self):
        url = reverse('source_about')
        self.assertPermissionGranted(url, None)
        self.assertPermissionGranted(url, self.user_outsider)

    def test_source_list(self):
        url = reverse('source_about')
        self.assertPermissionGranted(url, None)
        self.assertPermissionGranted(url, self.user_outsider)

    def test_source_new(self):
        url = reverse('source_new')
        self.assertRedirectsToLogin(url, None)
        self.assertPermissionGranted(url, self.user_outsider)

    def test_invites_manage(self):
        url = reverse('invites_manage')
        self.assertRedirectsToLogin(url, None)
        self.assertPermissionGranted(url, self.user_outsider)

    def test_source_detail_box_private_source(self):
        url = reverse('source_detail_box', args=[self.private_source.pk])
        self.assertPermissionGranted(url, None)
        self.assertPermissionGranted(url, self.user_outsider)

    def test_source_detail_box_public_source(self):
        url = reverse('source_detail_box', args=[self.public_source.pk])
        self.assertPermissionGranted(url, None)
        self.assertPermissionGranted(url, self.user_outsider)

    def test_source_main_private_source(self):
        url = reverse('source_main', args=[self.private_source.pk])
        self.assertPermissionDenied(url, None)
        self.assertPermissionDenied(url, self.user_outsider)
        self.assertPermissionGranted(url, self.user_viewer)
        self.assertPermissionGranted(url, self.user_editor)
        self.assertPermissionGranted(url, self.user_admin)

    def test_source_main_public_source(self):
        url = reverse('source_main', args=[self.public_source.pk])
        self.assertPermissionGranted(url, None)
        self.assertPermissionGranted(url, self.user_outsider)
        self.assertPermissionGranted(url, self.user_viewer)
        self.assertPermissionGranted(url, self.user_editor)
        self.assertPermissionGranted(url, self.user_admin)

    def test_source_edit_private_source(self):
        url = reverse('source_edit', args=[self.private_source.pk])
        self.assertPermissionDenied(url, None)
        self.assertPermissionDenied(url, self.user_outsider)
        self.assertPermissionDenied(url, self.user_viewer)
        self.assertPermissionDenied(url, self.user_editor)
        self.assertPermissionGranted(url, self.user_admin)

    def test_source_edit_public_source(self):
        url = reverse('source_edit', args=[self.public_source.pk])
        self.assertPermissionDenied(url, None)
        self.assertPermissionDenied(url, self.user_outsider)
        self.assertPermissionDenied(url, self.user_viewer)
        self.assertPermissionDenied(url, self.user_editor)
        self.assertPermissionGranted(url, self.user_admin)

    def test_source_admin_private_source(self):
        url = reverse('source_admin', args=[self.private_source.pk])
        self.assertPermissionDenied(url, None)
        self.assertPermissionDenied(url, self.user_outsider)
        self.assertPermissionDenied(url, self.user_viewer)
        self.assertPermissionDenied(url, self.user_editor)
        self.assertPermissionGranted(url, self.user_admin)

    def test_source_admin_public_source(self):
        url = reverse('source_admin', args=[self.public_source.pk])
        self.assertPermissionDenied(url, None)
        self.assertPermissionDenied(url, self.user_outsider)
        self.assertPermissionDenied(url, self.user_viewer)
        self.assertPermissionDenied(url, self.user_editor)
        self.assertPermissionGranted(url, self.user_admin)


class SourceAboutTest(ClientTest):
    """
    Test the About Sources page.
    """
    @classmethod
    def setUpTestData(cls):
        super(SourceAboutTest, cls).setUpTestData()

        cls.user_with_sources = cls.create_user()
        cls.user_without_sources = cls.create_user()

        cls.private_source = cls.create_source(
            cls.user_with_sources,
            visibility=Source.VisibilityTypes.PRIVATE)
        cls.public_source = cls.create_source(
            cls.user_with_sources,
            visibility=Source.VisibilityTypes.PUBLIC)

    def test_load_page_anonymous(self):
        response = self.client.get(resolve_url('source_about'))
        self.assertTemplateUsed(response, 'images/source_about.html')
        self.assertContains(
            response, "You need an account to work with Sources")
        # Source list should just have the public source
        self.assertContains(response, self.public_source.name)
        self.assertNotContains(response, self.private_source.name)

    def test_load_page_without_source_memberships(self):
        self.client.force_login(self.user_without_sources)
        response = self.client.get(resolve_url('source_about'))
        self.assertTemplateUsed(response, 'images/source_about.html')
        self.assertContains(
            response, "You're not part of any Sources")
        # Source list should just have the public source
        self.assertContains(response, self.public_source.name)
        self.assertNotContains(response, self.private_source.name)

    def test_load_page_with_source_memberships(self):
        self.client.force_login(self.user_with_sources)
        response = self.client.get(resolve_url('source_about'))
        self.assertTemplateUsed(response, 'images/source_about.html')
        self.assertContains(
            response, "See your Sources")
        # Source list should just have the public source
        self.assertContains(response, self.public_source.name)
        self.assertNotContains(response, self.private_source.name)


class SourceListTestWithSources(ClientTest):
    """
    Test the source list page when there's at least one source.
    """
    @classmethod
    def setUpTestData(cls):
        super(SourceListTestWithSources, cls).setUpTestData()

        cls.admin = cls.create_user()

        # Create sources with names to ensure a certain source list order
        cls.private_source = cls.create_source(
            cls.admin, name="Source 1",
            visibility=Source.VisibilityTypes.PRIVATE)
        cls.public_source = cls.create_source(
            cls.admin, name="Source 2",
            visibility=Source.VisibilityTypes.PUBLIC)

    def test_anonymous(self):
        response = self.client.get(resolve_url('source_list'), follow=True)
        # Should redirect to source_about
        self.assertTemplateUsed(response, 'images/source_about.html')

    def test_member_of_none(self):
        user = self.create_user()
        self.client.force_login(user)

        response = self.client.get(resolve_url('source_list'), follow=True)
        # Should redirect to source_about
        self.assertTemplateUsed(response, 'images/source_about.html')

    def test_member_of_public(self):
        user = self.create_user()
        self.add_source_member(
            self.admin, self.public_source, user, Source.PermTypes.VIEW.code)
        self.client.force_login(user)

        response = self.client.get(resolve_url('source_list'))
        self.assertTemplateUsed(response, 'images/source_list.html')
        self.assertListEqual(
            list(response.context['your_sources']),
            [dict(
                id=self.public_source.pk, name=self.public_source.name,
                your_role="View")]
        )
        self.assertListEqual(
            list(response.context['other_public_sources']),
            []
        )

    def test_member_of_private(self):
        user = self.create_user()
        self.add_source_member(
            self.admin, self.private_source, user, Source.PermTypes.VIEW.code)
        self.client.force_login(user)

        response = self.client.get(resolve_url('source_list'))
        self.assertTemplateUsed(response, 'images/source_list.html')
        self.assertListEqual(
            list(response.context['your_sources']),
            [
                dict(
                    id=self.private_source.pk, name=self.private_source.name,
                    your_role="View"
                ),
            ]
        )
        self.assertListEqual(
            list(response.context['other_public_sources']),
            [self.public_source]
        )

    def test_member_of_public_and_private(self):
        user = self.create_user()
        self.add_source_member(
            self.admin, self.private_source, user, Source.PermTypes.EDIT.code)
        self.add_source_member(
            self.admin, self.public_source, user, Source.PermTypes.ADMIN.code)
        self.client.force_login(user)

        response = self.client.get(resolve_url('source_list'))
        self.assertTemplateUsed(response, 'images/source_list.html')
        # Sources should be in name-alphabetical order
        self.assertListEqual(
            list(response.context['your_sources']),
            [
                dict(
                    id=self.private_source.pk, name=self.private_source.name,
                    your_role="Edit"
                ),
                dict(
                    id=self.public_source.pk, name=self.public_source.name,
                    your_role="Admin"
                ),
            ]
        )
        self.assertListEqual(
            list(response.context['other_public_sources']),
            []
        )


class SourceNewTest(ClientTest):
    """
    Test the New Source page.
    """
    @classmethod
    def setUpTestData(cls):
        super(SourceNewTest, cls).setUpTestData()

        cls.user = cls.create_user()

    def create_source(self, **kwargs):
        data = dict(
            name="Test Source",
            visibility=Source.VisibilityTypes.PRIVATE,
            affiliation="Testing Society",
            description="Description\ngoes here.",
            key1="Aux1", key2="Aux2", key3="Aux3", key4="Aux4", key5="Aux5",
            min_x=10, max_x=90, min_y=10, max_y=90,
            point_generation_type=PointGen.Types.SIMPLE,
            simple_number_of_points=16, number_of_cell_rows='',
            number_of_cell_columns='', stratified_points_per_cell='',
            latitude='-17.3776', longitude='25.1982')
        data.update(**kwargs)
        response = self.client.post(
            reverse('source_new'), data, follow=True)
        return response

    def test_access_page(self):
        """
        Access the page without errors.
        """
        self.client.force_login(self.user)
        response = self.client.get(reverse('source_new'))
        self.assertStatusOK(response)
        self.assertTemplateUsed(response, 'images/source_new.html')

    def test_source_defaults(self):
        """
        Check for default values in the source form.
        """
        self.client.force_login(self.user)
        response = self.client.get(reverse('source_new'))

        form = response.context['sourceForm']
        self.assertEqual(
            form['visibility'].value(), Source.VisibilityTypes.PUBLIC)
        self.assertEqual(form['key1'].value(), 'Aux1')
        self.assertEqual(form['key2'].value(), 'Aux2')
        self.assertEqual(form['key3'].value(), 'Aux3')
        self.assertEqual(form['key4'].value(), 'Aux4')
        self.assertEqual(form['key5'].value(), 'Aux5')

    def test_source_create(self):
        """
        Successful creation of a new source.
        """
        datetime_before_creation = timezone.now()

        self.client.force_login(self.user)
        response = self.create_source()

        new_source = Source.objects.latest('create_date')
        self.assertTemplateUsed('images/source_main.html')
        self.assertEqual(response.context['source'], new_source)
        self.assertContains(response, "Source successfully created.")

        self.assertEqual(new_source.name, "Test Source")
        self.assertEqual(new_source.visibility, Source.VisibilityTypes.PRIVATE)
        self.assertEqual(new_source.affiliation, "Testing Society")
        self.assertEqual(new_source.description, "Description\ngoes here.")
        self.assertEqual(new_source.key1, "Aux1")
        self.assertEqual(new_source.key2, "Aux2")
        self.assertEqual(new_source.key3, "Aux3")
        self.assertEqual(new_source.key4, "Aux4")
        self.assertEqual(new_source.key5, "Aux5")
        self.assertEqual(
            new_source.default_point_generation_method,
            PointGen.args_to_db_format(
                point_generation_type=PointGen.Types.SIMPLE,
                simple_number_of_points=16,
            ),
        )
        self.assertEqual(
            new_source.image_annotation_area,
            AnnotationAreaUtils.percentages_to_db_format(
                min_x=10, max_x=90,
                min_y=10, max_y=90,
            ),
        )
        self.assertEqual(new_source.latitude, '-17.3776')
        self.assertEqual(new_source.longitude, '25.1982')

        # Fields that aren't in the form.
        self.assertEqual(new_source.labelset, None)
        self.assertEqual(new_source.confidence_threshold, 100)
        self.assertEqual(new_source.enable_robot_classifier, True)

        # Check that the source creation date is reasonable:
        # - a timestamp taken before creation should be before the creation
        #   date.
        # - a timestamp taken after creation should be after the creation date.
        self.assertTrue(datetime_before_creation <= new_source.create_date)
        self.assertTrue(new_source.create_date <= timezone.now())

    def test_name_required(self):
        self.client.force_login(self.user)

        response = self.create_source(name="")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(response, "This field is required.")

        # Should have no source created.
        self.assertEqual(Source.objects.all().count(), 0)

    def test_affiliation_required(self):
        self.client.force_login(self.user)

        response = self.create_source(affiliation="")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(response, "This field is required.")

        self.assertEqual(Source.objects.all().count(), 0)

    def test_description_required(self):
        self.client.force_login(self.user)

        response = self.create_source(description="")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(response, "This field is required.")

        self.assertEqual(Source.objects.all().count(), 0)

    def test_aux_names_required(self):
        self.client.force_login(self.user)

        response = self.create_source(key1="")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(response, "This field is required.")

        response = self.create_source(key2="")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(response, "This field is required.")

        response = self.create_source(key3="")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(response, "This field is required.")

        response = self.create_source(key4="")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(response, "This field is required.")

        response = self.create_source(key5="")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(response, "This field is required.")

        # Should have no source created.
        self.assertEqual(Source.objects.all().count(), 0)

    def test_temporal_aux_name_not_accepted(self):
        """
        If an aux. meta field name looks like it's tracking date or time,
        don't accept it.
        """
        self.client.force_login(self.user)
        response = self.create_source(
            key1="date",
            key2="Year",
            key3="TIME",
            key4="month",
            key5="day",
        )

        # Should be back on the new source form with errors.
        self.assertTemplateUsed(response, 'images/source_new.html')
        error_dont_use_temporal = (
            "Date of image acquisition is already a default metadata field."
            " Do not use auxiliary metadata fields"
            " to encode temporal information."
        )
        self.assertDictEqual(
            response.context['sourceForm'].errors,
            dict(
                key1=[error_dont_use_temporal],
                key2=[error_dont_use_temporal],
                key3=[error_dont_use_temporal],
                key4=[error_dont_use_temporal],
                key5=[error_dont_use_temporal],
            )
        )
        # Should have no source created.
        self.assertEqual(Source.objects.all().count(), 0)

    def test_aux_name_conflict_with_builtin_name(self):
        """
        If an aux. meta field name conflicts with a built-in metadata field,
        show an error.
        """
        self.client.force_login(self.user)
        response = self.create_source(
            key1="name",
            key2="Comments",
            key3="FRAMING GEAR used",
        )

        # Should be back on the new source form with errors.
        self.assertTemplateUsed(response, 'images/source_new.html')
        error_conflict = (
            "This conflicts with either a built-in metadata"
            " field or another auxiliary field."
        )
        self.assertDictEqual(
            response.context['sourceForm'].errors,
            dict(
                key1=[error_conflict],
                key2=[error_conflict],
                key3=[error_conflict],
            )
        )
        # Should have no source created.
        self.assertEqual(Source.objects.all().count(), 0)

    def test_aux_name_conflict_with_other_aux_name(self):
        """
        If two aux. meta field names are the same, show an error.
        """
        self.client.force_login(self.user)
        response = self.create_source(
            key2="Site",
            key3="site",
        )

        # Should be back on the new source form with errors.
        self.assertTemplateUsed(response, 'images/source_new.html')
        error_conflict = (
            "This conflicts with either a built-in metadata"
            " field or another auxiliary field."
        )
        self.assertDictEqual(
            response.context['sourceForm'].errors,
            dict(
                key2=[error_conflict],
                key3=[error_conflict],
            )
        )
        # Should have no source created.
        self.assertEqual(Source.objects.all().count(), 0)

    def test_annotation_area_required(self):
        self.client.force_login(self.user)

        response = self.create_source(min_x="")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(response, "This field is required.")

        response = self.create_source(max_x="")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(response, "This field is required.")

        response = self.create_source(min_y="")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(response, "This field is required.")

        response = self.create_source(max_y="")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(response, "This field is required.")

        self.assertEqual(Source.objects.all().count(), 0)

    def test_pointgen_type_required(self):
        self.client.force_login(self.user)

        response = self.create_source(point_generation_type="")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(response, "This field is required.")

    def test_pointgen_type_invalid(self):
        self.client.force_login(self.user)

        response = self.create_source(point_generation_type="straight line")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(
            response,
            "Select a valid choice. straight line is not one of the available"
            " choices.")

    def test_pointgen_simple_success(self):
        self.client.force_login(self.user)

        response = self.create_source(
            point_generation_type=PointGen.Types.SIMPLE,
            simple_number_of_points=50, number_of_cell_rows='',
            number_of_cell_columns='', stratified_points_per_cell='')

        new_source = Source.objects.latest('create_date')
        self.assertTemplateUsed('images/source_main.html')
        self.assertEqual(response.context['source'], new_source)

        self.assertEqual(
            new_source.default_point_generation_method,
            PointGen.args_to_db_format(
                point_generation_type=PointGen.Types.SIMPLE,
                simple_number_of_points=50))

    def test_pointgen_stratified_success(self):
        self.client.force_login(self.user)

        response = self.create_source(
            point_generation_type=PointGen.Types.STRATIFIED,
            simple_number_of_points='', number_of_cell_rows=4,
            number_of_cell_columns=5, stratified_points_per_cell=6)

        new_source = Source.objects.latest('create_date')
        self.assertTemplateUsed('images/source_main.html')
        self.assertEqual(response.context['source'], new_source)

        self.assertEqual(
            new_source.default_point_generation_method,
            PointGen.args_to_db_format(
                point_generation_type=PointGen.Types.STRATIFIED,
                number_of_cell_rows=4, number_of_cell_columns=5,
                stratified_points_per_cell=6))

    def test_pointgen_uniform_grid_success(self):
        self.client.force_login(self.user)

        response = self.create_source(
            point_generation_type=PointGen.Types.UNIFORM,
            simple_number_of_points='', number_of_cell_rows=4,
            number_of_cell_columns=7, stratified_points_per_cell='')

        new_source = Source.objects.latest('create_date')
        self.assertTemplateUsed('images/source_main.html')
        self.assertEqual(response.context['source'], new_source)

        self.assertEqual(
            new_source.default_point_generation_method,
            PointGen.args_to_db_format(
                point_generation_type=PointGen.Types.UNIFORM,
                number_of_cell_rows=4, number_of_cell_columns=7))

    def test_pointgen_filling_extra_fields_ok(self):
        self.client.force_login(self.user)

        # Filling more fields than necessary here, even with values that
        # would be invalid
        response = self.create_source(
            point_generation_type=PointGen.Types.UNIFORM,
            simple_number_of_points=-2, number_of_cell_rows=4,
            number_of_cell_columns=7, stratified_points_per_cell=10000)

        new_source = Source.objects.latest('create_date')
        self.assertTemplateUsed('images/source_main.html')
        self.assertEqual(response.context['source'], new_source)

        self.assertEqual(
            new_source.default_point_generation_method,
            PointGen.args_to_db_format(
                point_generation_type=PointGen.Types.UNIFORM,
                number_of_cell_rows=4, number_of_cell_columns=7))

    def test_pointgen_simple_missing_required_fields(self):
        self.client.force_login(self.user)

        response = self.create_source(
            point_generation_type=PointGen.Types.SIMPLE,
            simple_number_of_points='', number_of_cell_rows='',
            number_of_cell_columns='', stratified_points_per_cell='')

        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertDictEqual(
            response.context['pointGenForm'].errors,
            dict(
                simple_number_of_points=["This field is required."],
            )
        )

    def test_pointgen_stratified_missing_required_fields(self):
        self.client.force_login(self.user)

        response = self.create_source(
            point_generation_type=PointGen.Types.STRATIFIED,
            simple_number_of_points='', number_of_cell_rows='',
            number_of_cell_columns='', stratified_points_per_cell='')

        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertDictEqual(
            response.context['pointGenForm'].errors,
            dict(
                number_of_cell_rows=["This field is required."],
                number_of_cell_columns=["This field is required."],
                stratified_points_per_cell=["This field is required."],
            )
        )

    def test_pointgen_uniform_missing_required_fields(self):
        self.client.force_login(self.user)

        response = self.create_source(
            point_generation_type=PointGen.Types.UNIFORM,
            simple_number_of_points='', number_of_cell_rows='',
            number_of_cell_columns='', stratified_points_per_cell='')

        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertDictEqual(
            response.context['pointGenForm'].errors,
            dict(
                number_of_cell_rows=["This field is required."],
                number_of_cell_columns=["This field is required."],
            )
        )

    def test_pointgen_too_few_simple_points(self):
        self.client.force_login(self.user)

        response = self.create_source(
            point_generation_type=PointGen.Types.SIMPLE,
            simple_number_of_points=0, number_of_cell_rows='',
            number_of_cell_columns='', stratified_points_per_cell='')
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertDictEqual(
            response.context['pointGenForm'].errors,
            dict(
                simple_number_of_points=[
                    "Ensure this value is greater than or equal to 1."],
            )
        )

    def test_pointgen_too_few_rows_columns_per_cell(self):
        self.client.force_login(self.user)

        response = self.create_source(
            point_generation_type=PointGen.Types.STRATIFIED,
            simple_number_of_points='', number_of_cell_rows=0,
            number_of_cell_columns=0, stratified_points_per_cell=0)
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertDictEqual(
            response.context['pointGenForm'].errors,
            dict(
                number_of_cell_rows=[
                    "Ensure this value is greater than or equal to 1."],
                number_of_cell_columns=[
                    "Ensure this value is greater than or equal to 1."],
                stratified_points_per_cell=[
                    "Ensure this value is greater than or equal to 1."],
            )
        )

    def test_pointgen_too_many_points(self):
        self.client.force_login(self.user)

        response = self.create_source(
            point_generation_type=PointGen.Types.STRATIFIED,
            simple_number_of_points='', number_of_cell_rows=10,
            number_of_cell_columns=10, stratified_points_per_cell=11)
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertDictEqual(
            response.context['pointGenForm'].errors,
            dict(
                __all__=[
                    "You specified 1100 points total."
                    " Please make it no more than 1000."],
            )
        )

    def test_latitude_longitude_required(self):
        self.client.force_login(self.user)

        response = self.create_source(latitude="")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(response, "This field is required.")

        response = self.create_source(longitude="")
        self.assertTemplateUsed(response, 'images/source_new.html')
        self.assertContains(response, "This field is required.")

        self.assertEqual(Source.objects.all().count(), 0)


class SourceEditTest(ClientTest):
    """
    Test the Edit Source page.
    """
    @classmethod
    def setUpTestData(cls):
        super(SourceEditTest, cls).setUpTestData()

        cls.user = cls.create_user()

        # Create a source
        cls.source = cls.create_source(cls.user)
        cls.url = reverse('source_edit', args=[cls.source.pk])

    def test_access_page(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertStatusOK(response)
        self.assertTemplateUsed(response, 'images/source_edit.html')

    def test_source_edit(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            dict(
                name="Test Source 2",
                visibility=Source.VisibilityTypes.PUBLIC,
                affiliation="Testing Association",
                description="This is\na description.",
                key1="Island",
                key2="Site",
                key3="Habitat",
                key4="Section",
                key5="Transect",
                min_x=5,
                max_x=95,
                min_y=5,
                max_y=95,
                point_generation_type=PointGen.Types.STRATIFIED,
                number_of_cell_rows=4,
                number_of_cell_columns=6,
                stratified_points_per_cell=3,
                confidence_threshold=80,
                latitude='5.789',
                longitude='-50',
            ),
        )

        self.assertRedirects(
            response,
            reverse('source_main', kwargs={'source_id': self.source.pk})
        )

        self.source.refresh_from_db()
        self.assertEqual(self.source.name, "Test Source 2")
        self.assertEqual(self.source.visibility, Source.VisibilityTypes.PUBLIC)
        self.assertEqual(self.source.affiliation, "Testing Association")
        self.assertEqual(self.source.description, "This is\na description.")
        self.assertEqual(self.source.key1, "Island")
        self.assertEqual(self.source.key2, "Site")
        self.assertEqual(self.source.key3, "Habitat")
        self.assertEqual(self.source.key4, "Section")
        self.assertEqual(self.source.key5, "Transect")
        self.assertEqual(
            self.source.image_annotation_area,
            AnnotationAreaUtils.percentages_to_db_format(
                min_x=5, max_x=95, min_y=5, max_y=95,
            )
        )
        self.assertEqual(
            self.source.default_point_generation_method,
            PointGen.args_to_db_format(
                point_generation_type=PointGen.Types.STRATIFIED,
                number_of_cell_rows=4,
                number_of_cell_columns=6,
                stratified_points_per_cell=3,
            )
        )
        self.assertEqual(self.source.confidence_threshold, 80)
        self.assertEqual(self.source.latitude, '5.789')
        self.assertEqual(self.source.longitude, '-50')


class SourceInviteTest(ClientTest):
    """
    Test sending and accepting invites to sources.
    """
    @classmethod
    def setUpTestData(cls):
        super(SourceInviteTest, cls).setUpTestData()

        cls.user_creator = cls.create_user()
        cls.source = cls.create_source(cls.user_creator)

        cls.user_editor = cls.create_user()

    def test_source_invite(self):
        # Send invite as source admin
        self.client.force_login(self.user_creator)
        self.client.post(
            reverse('source_admin', kwargs={'source_id': self.source.pk}),
            dict(
                sendInvite='sendInvite',
                recipient=self.user_editor.username,
                source_perm=Source.PermTypes.EDIT.code,
            ),
        )

        # Accept invite as prospective source member
        self.client.force_login(self.user_editor)
        self.client.post(
            reverse('invites_manage'),
            dict(
                accept='',
                sender=self.user_creator.pk,
                source=self.source.pk,
            ),
        )

        # Test that the given permission level works
        self.client.force_login(self.user_editor)
        response = self.client.get(
            reverse('upload_images', kwargs={'source_id': self.source.pk}))
        self.assertTemplateUsed(response, 'upload/upload_images.html')