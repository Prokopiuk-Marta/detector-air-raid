from django.urls import path
from . import views

urlpatterns = [
    path("services/", views.ServiceListView.as_view(), name="service-list"),
    path(
        "services/<slug:slug>/",
        views.ServiceDetailView.as_view(),
        name="service-detail",
    ),
    path("outages/", views.PowerOutageListView.as_view(), name="outage-list"),
    path(
        "outages/<int:pk>/",
        views.PowerOutageDetailView.as_view(),
        name="outage-detail",
    ),
    path("incidents/", views.IncidentListView.as_view(), name="incident-list"),
    path(
        "incidents/<int:pk>/",
        views.IncidentDetailView.as_view(),
        name="incident-detail",
    ),
]
