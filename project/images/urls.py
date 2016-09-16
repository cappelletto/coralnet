from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^source/$', views.source_list, name="source_list"),
    url(r'^source/about/$', views.source_about, name="source_about"),
    url(r'^source/new/$', views.source_new, name="source_new"),
    url(r'^source/(?P<source_id>\d+)/$', views.source_main, name="source_main"),
    url(r'^source/(?P<source_id>\d+)/(?P<robot_version>\d+)/(?P<namestr>[a-z]+)$', views.cm_download, name="cm_download"),
    url(r'^source/(?P<source_id>\d+)/(?P<robot_version>\d+)/alleviate.pdf$', views.alleviate_download, name="alleviate_download"),
    url(r'^source/(?P<source_id>\d+)/edit/$', views.source_edit, name="source_edit"),
    url(r'^source/(?P<source_id>\d+)/robotstats/$', views.robot_stats_all, name="robot_stats_all"),
    url(r'^source/(?P<source_id>\d+)/admin/$', views.source_admin, name="source_admin"),
    url(r'^image/(?P<image_id>\d+)/view/$', views.image_detail, name="image_detail"),
    url(r'^image/(?P<image_id>\d+)/edit/$', views.image_detail_edit, name="image_detail_edit"),

    # Consider moving this to annotations or upload, or else remove this if we're no longer using it.
    url(r'^source/(?P<source_id>\d+)/label_import/$', views.import_labels, name="label_import"),

    # Consider moving this into accounts, or messages, or a separate
    # 'sources' app if we decide to have such a thing.
    url(r'^invites_manage/$', views.invites_manage, name="invites_manage"),
]
