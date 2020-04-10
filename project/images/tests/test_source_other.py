from __future__ import unicode_literals

from bs4 import BeautifulSoup
from django.test import override_settings
from django.urls import reverse

from images.model_utils import PointGen
from images.models import Source
from lib.tests.utils import BasePermissionTest, ClientTest
from newsfeed.models import NewsItem


class PermissionTest(BasePermissionTest):
    """
    Test permissions for source-related views other than source about and
    source list, which are tested in different classes. (Those views have
    specific redirect logic.)
    """
    def test_source_detail_box(self):
        url = reverse('source_detail_box', args=[self.source.pk])
        template = 'images/source_detail_box.html'

        self.source_to_private()
        self.assertPermissionLevel(url, self.SIGNED_OUT, template=template)
        self.source_to_public()
        self.assertPermissionLevel(url, self.SIGNED_OUT, template=template)

    def test_source_main(self):
        url = reverse('source_main', args=[self.source.pk])
        template = 'images/source_main.html'

        self.source_to_private()
        self.assertPermissionLevel(url, self.SOURCE_VIEW, template=template)
        self.source_to_public()
        self.assertPermissionLevel(url, self.SIGNED_OUT, template=template)


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
        response = self.client.get(reverse('source_about'))
        self.assertTemplateUsed(response, 'images/source_about.html')
        self.assertContains(
            response, "You need an account to work with Sources")
        # Source list should just have the public source
        self.assertContains(response, self.public_source.name)
        self.assertNotContains(response, self.private_source.name)

    def test_load_page_without_source_memberships(self):
        self.client.force_login(self.user_without_sources)
        response = self.client.get(reverse('source_about'))
        self.assertTemplateUsed(response, 'images/source_about.html')
        self.assertContains(
            response, "You're not part of any Sources")
        # Source list should just have the public source
        self.assertContains(response, self.public_source.name)
        self.assertNotContains(response, self.private_source.name)

    def test_load_page_with_source_memberships(self):
        self.client.force_login(self.user_with_sources)
        response = self.client.get(reverse('source_about'))
        self.assertTemplateUsed(response, 'images/source_about.html')
        self.assertContains(
            response, "See your Sources")
        # Source list should just have the public source
        self.assertContains(response, self.public_source.name)
        self.assertNotContains(response, self.private_source.name)


class SourceListTest(ClientTest):
    """
    Test the source list page (except the map).
    """
    @classmethod
    def setUpTestData(cls):
        super(SourceListTest, cls).setUpTestData()

        cls.admin = cls.create_user()

        # Create sources with names to ensure a certain source list order
        cls.private_source = cls.create_source(
            cls.admin, name="Source 1",
            visibility=Source.VisibilityTypes.PRIVATE)
        cls.public_source = cls.create_source(
            cls.admin, name="Source 2",
            visibility=Source.VisibilityTypes.PUBLIC)

    def test_anonymous(self):
        response = self.client.get(reverse('source_list'), follow=True)
        # Should redirect to source_about
        self.assertTemplateUsed(response, 'images/source_about.html')

    def test_member_of_none(self):
        user = self.create_user()
        self.client.force_login(user)

        response = self.client.get(reverse('source_list'), follow=True)
        # Should redirect to source_about
        self.assertTemplateUsed(response, 'images/source_about.html')

    def test_member_of_public(self):
        user = self.create_user()
        self.add_source_member(
            self.admin, self.public_source, user, Source.PermTypes.VIEW.code)
        self.client.force_login(user)

        response = self.client.get(reverse('source_list'))
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

        response = self.client.get(reverse('source_list'))
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

        response = self.client.get(reverse('source_list'))
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


@override_settings(MAP_IMAGE_COUNT_TIERS=[2, 3, 5])
class SourceMapTest(ClientTest):
    """
    Test the map on the source list page.
    """
    @classmethod
    def setUpTestData(cls):
        super(SourceMapTest, cls).setUpTestData()

        cls.user = cls.create_user()

    def test_map_sources_all_fields(self):
        source = self.create_source(
            self.user, visibility=Source.VisibilityTypes.PUBLIC)
        for _ in range(2):
            self.upload_image(self.user, source)

        self.client.force_login(self.user)
        response = self.client.get(reverse('source_list'))

        self.assertDictEqual(
            response.context['map_sources'][0],
            dict(
                sourceId=source.id,
                latitude=source.latitude,
                longitude=source.longitude,
                type='public',
                size=1,
                detailBoxUrl=reverse('source_detail_box', args=[source.pk]),
            ),
        )

    def test_map_sources_type_field(self):
        # Test both possible type values.
        public_source = self.create_source(
            self.user, visibility=Source.VisibilityTypes.PUBLIC)
        for _ in range(2):
            self.upload_image(self.user, public_source)

        private_source = self.create_source(
            self.user, visibility=Source.VisibilityTypes.PRIVATE)
        for _ in range(2):
            self.upload_image(self.user, private_source)

        self.client.force_login(self.user)
        response = self.client.get(reverse('source_list'))

        # Set comparison, since source order is not defined here.
        ids_and_types = {
            (d['sourceId'], d['type'])
            for d in response.context['map_sources']
        }
        self.assertSetEqual(
            ids_and_types,
            {
                (public_source.pk, 'public'),
                (private_source.pk, 'private'),
            },
        )

    def test_map_sources_size_field(self):
        """Test all possible source size tiers (size meaning image count)."""
        source_tier_0 = self.create_source(self.user)
        self.upload_image(self.user, source_tier_0)

        source_tier_1 = self.create_source(self.user)
        for _ in range(2):
            self.upload_image(self.user, source_tier_1)

        source_tier_2 = self.create_source(self.user)
        for _ in range(4):
            self.upload_image(self.user, source_tier_2)

        source_tier_3 = self.create_source(self.user)
        for _ in range(5):
            self.upload_image(self.user, source_tier_3)

        self.client.force_login(self.user)
        response = self.client.get(reverse('source_list'))

        # Set comparison, since source order is not defined here.
        # Note that source_tier_0 is not in the map sources.
        ids_and_sizes = {
            (d['sourceId'], d['size'])
            for d in response.context['map_sources']
        }
        self.assertSetEqual(
            ids_and_sizes,
            {
                (source_tier_1.pk, 1),
                (source_tier_2.pk, 2),
                (source_tier_3.pk, 3),
            },
        )

    def test_exclude_test_sources(self):
        source_1 = self.create_source(self.user, name="Source 1")
        for _ in range(2):
            self.upload_image(self.user, source_1)

        test_source_1 = self.create_source(self.user, name="Test 1")
        for _ in range(2):
            self.upload_image(self.user, test_source_1)

        test_source_2 = self.create_source(
            self.user, name="User's temporary source")
        for _ in range(2):
            self.upload_image(self.user, test_source_2)

        self.client.force_login(self.user)
        response = self.client.get(reverse('source_list'))

        ids = {d['sourceId'] for d in response.context['map_sources']}
        self.assertSetEqual(ids, {source_1.pk})


class SourceDetailBoxTest(ClientTest):
    """
    Test the map's source detail popup box.
    """
    @classmethod
    def setUpTestData(cls):
        super(SourceDetailBoxTest, cls).setUpTestData()

        cls.user = cls.create_user()

    def test_private_source(self):
        source = self.create_source(
            self.user, visibility=Source.VisibilityTypes.PRIVATE,
            affiliation="My Affiliation",
            description="My Description",
        )
        for _ in range(3):
            self.upload_image(self.user, source)

        response = self.client.get(
            reverse('source_detail_box', args=[source.pk]))

        self.assertContains(response, source.name)
        self.assertNotContains(
            response, reverse('source_main', args=[source.pk]))

        self.assertContains(response, "My Affiliation")
        self.assertContains(response, "My Description")
        self.assertContains(response, "Number of images: 3")
        self.assertNotContains(response, 'class="source-example-image"')

    def test_public_source(self):
        source = self.create_source(
            self.user, visibility=Source.VisibilityTypes.PUBLIC,
            affiliation="My Affiliation",
            description="My Description",
        )
        for _ in range(3):
            self.upload_image(self.user, source)

        response = self.client.get(
            reverse('source_detail_box', args=[source.pk]))

        self.assertContains(response, source.name)
        self.assertContains(
            response, reverse('source_main', args=[source.pk]))

        self.assertContains(response, "My Affiliation")
        self.assertContains(response, "My Description")
        self.assertContains(response, "Number of images: 3")
        self.assertContains(response, 'class="source-example-image"')


class SourceMainTest(ClientTest):
    """
    Test a source's main page.
    """
    @classmethod
    def setUpTestData(cls):
        super(SourceMainTest, cls).setUpTestData()

        cls.user = cls.create_user("user1")

    def test_source_members_box(self):
        source = self.create_source(self.user)

        user_viewer = self.create_user("user2")
        self.add_source_member(
            self.user, source, user_viewer, Source.PermTypes.VIEW.code)
        user_editor = self.create_user("user3")
        self.add_source_member(
            self.user, source, user_editor, Source.PermTypes.EDIT.code)

        self.client.force_login(self.user)
        response = self.client.get(reverse('source_main', args=[source.pk]))

        # Should be ordered by role first, not by username first
        self.assertInHTML(
            '<tr><td><a href="{}">{}</a></td><td><b>Admin</b></td></tr>'
            '<tr><td><a href="{}">{}</a></td><td><b>Edit</b></td></tr>'
            '<tr><td><a href="{}">{}</a></td><td><b>View</b></td></tr>'.format(
                reverse('profile_detail', args=[self.user.pk]), "user1",
                reverse('profile_detail', args=[user_editor.pk]), "user3",
                reverse('profile_detail', args=[user_viewer.pk]), "user2",
            ),
            response.content)

    def test_source_fields_box_1(self):
        source = self.create_source(
            self.user,
            min_x=0, max_x=100, min_y=5, max_y=95,
            point_generation_type=PointGen.Types.SIMPLE,
            simple_number_of_points=5,
            confidence_threshold=80,
            description="This is a\nmultiline description.")
        self.create_robot(source)

        self.client.force_login(self.user)
        response = self.client.get(reverse('source_main', args=[source.pk]))

        self.assertContains(response, "Last classifier trained:")
        self.assertContains(
            response,
            "Default image annotation area: X: 0 - 100% / Y: 5 - 95%")
        self.assertContains(
            response, "Annotation point generation: Simple random, 5 points")
        self.assertContains(response, "Confidence threshold: 80%")
        self.assertInHTML(
            '<br><br>This is a<br>multiline description.', response.content)

    def test_source_fields_box_2(self):
        source = self.create_source(
            self.user, visibility=Source.VisibilityTypes.PUBLIC,
            latitude='30.0296', longitude='-15.6402',
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('source_main', args=[source.pk]))

        self.assertContains(response, 'Visibility: <b>Public</b>')
        self.assertContains(response, 'Latitude: <b>30.0296</b>')
        self.assertContains(response, 'Longitude: <b>-15.6402</b>')

    def test_latest_images(self):
        source = self.create_source(self.user)

        # Upload 4 images
        self.upload_image(self.user, source)
        img2 = self.upload_image(self.user, source)
        img3 = self.upload_image(self.user, source)
        img4 = self.upload_image(self.user, source)
        # Another image in another source; shouldn't appear on the page
        other_source = self.create_source(self.user)
        self.upload_image(self.user, other_source)

        self.client.force_login(self.user)
        response = self.client.get(reverse('source_main', args=[source.pk]))

        response_soup = BeautifulSoup(response.content, 'html.parser')
        images_div = response_soup.find('div', id='images')
        a_elements = images_div.find_all('a')
        href_attributes = [
            element.attrs.get('href') for element in a_elements]

        # Should have the last 3 images from latest to earliest
        self.assertListEqual(
            href_attributes,
            [
                reverse('image_detail', args=[img4.pk]),
                reverse('image_detail', args=[img3.pk]),
                reverse('image_detail', args=[img2.pk]),
            ],
        )

    def test_image_status_box(self):
        source = self.create_source(
            self.user, point_generation_type=PointGen.Types.SIMPLE,
            simple_number_of_points=1)
        labels = self.create_labels(self.user, ['A', 'B'], 'GroupA')
        self.create_labelset(self.user, source, labels)
        robot = self.create_robot(source)

        # Unclassified
        self.upload_image(self.user, source)

        # Unconfirmed
        img = self.upload_image(self.user, source)
        self.add_robot_annotations(robot, img)
        img = self.upload_image(self.user, source)
        self.add_robot_annotations(robot, img)

        # Confirmed
        img = self.upload_image(self.user, source)
        self.add_robot_annotations(robot, img)
        self.add_annotations(self.user, img, {1: 'A'})

        # Another image in another source; shouldn't change the results
        other_source = self.create_source(self.user)
        self.upload_image(self.user, other_source)

        self.client.force_login(self.user)
        response = self.client.get(reverse('source_main', args=[source.pk]))

        self.assertInHTML(
            'Unclassified: <a href="{}">1</a>'.format(
                reverse('browse_images', args=[source.pk])
                + '?image_form_type=search&annotation_status=unclassified'),
            response.content)

        self.assertInHTML(
            'Unconfirmed: <a href="{}">2</a>'.format(
                reverse('browse_images', args=[source.pk])
                + '?image_form_type=search&annotation_status=unconfirmed'),
            response.content)

        self.assertInHTML(
            'Confirmed: <a href="{}">1</a>'.format(
                reverse('browse_images', args=[source.pk])
                + '?image_form_type=search&annotation_status=confirmed'),
            response.content)

    @override_settings(MIN_NBR_ANNOTATED_IMAGES=3)
    def test_automated_annotation_section(self):
        source = self.create_source(self.user)

        self.client.force_login(self.user)
        response = self.client.get(reverse('source_main', args=[source.pk]))
        self.assertContains(
            response,
            "This source does not have a classifier yet."
            " 3 images required to trigger training the first one.")
        self.assertNotContains(response, '<div id="acc_overview"')

        self.create_robot(source)
        response = self.client.get(reverse('source_main', args=[source.pk]))
        self.assertNotContains(
            response,
            "This source does not have a classifier yet."
            " 3 images required to trigger training the first one.")
        self.assertContains(response, '<div id="acc_overview"')

    def test_newsfeed_box(self):
        source = self.create_source(self.user)
        news_item = NewsItem(
            source_id=source.pk,
            source_name=source.name,
            user_id=self.user.pk,
            user_username=self.user.username,
            message="This is a message",
            category='source',
        )
        news_item.save()

        other_source = self.create_source(self.user)
        other_news_item = NewsItem(
            source_id=other_source.pk,
            source_name=other_source.name,
            user_id=self.user.pk,
            user_username=self.user.username,
            message="This is another message",
            category='source',
        )
        other_news_item.save()

        self.client.force_login(self.user)
        response = self.client.get(reverse('source_main', args=[source.pk]))

        self.assertContains(
            response, reverse('newsfeed_details', args=[news_item.pk]))
        self.assertContains(
            response, "This is a message")

        # Don't show news from other sources
        self.assertNotContains(
            response, reverse('newsfeed_details', args=[other_news_item.pk]))