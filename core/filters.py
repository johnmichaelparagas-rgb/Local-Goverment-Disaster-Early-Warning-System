import django_filters
from django import forms

from .models import Incident, MUNICIPALITY_CHOICES


class IncidentFilter(django_filters.FilterSet):
    """Composable querystring filters for the incident dashboard.

    Supports combined date-range + status (+ municipality/type) filtering, e.g.
        ?start=2026-05-01&end=2026-05-31&status=in_progress&municipality=Palo
    """
    start = django_filters.DateFilter(
        field_name='reported_at', lookup_expr='date__gte',
        label='From', widget=forms.DateInput(attrs={'type': 'date'}),
    )
    end = django_filters.DateFilter(
        field_name='reported_at', lookup_expr='date__lte',
        label='To', widget=forms.DateInput(attrs={'type': 'date'}),
    )
    status = django_filters.ChoiceFilter(
        choices=Incident.Status.choices, empty_label='All statuses',
    )
    municipality = django_filters.ChoiceFilter(
        choices=MUNICIPALITY_CHOICES, empty_label='All municipalities',
    )
    type = django_filters.ChoiceFilter(
        choices=Incident.Type.choices, empty_label='All types',
    )

    class Meta:
        model = Incident
        fields = ['start', 'end', 'status', 'municipality', 'type']
