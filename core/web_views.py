"""Server-rendered management UI (Django session auth).

Provides the inline-formset incident editor and the django-filter dashboard,
gated by the three LGU roles. The JWT SPA dashboard (root URL) and these pages
share the same accounts.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .filters import IncidentFilter
from .forms import HazardImageFormSet, IncidentForm, IncidentStatusForm
from .models import Incident
from .views import record_audit


def _require_admin(request):
    return getattr(request.user, 'is_lgu_admin', False)


def _require_editor(request):
    return getattr(request.user, 'can_edit', False)


@login_required
def dashboard(request):
    """Filterable, paginated incident dashboard (all logged-in roles)."""
    incidents = Incident.objects.all().prefetch_related('images')
    f = IncidentFilter(request.GET, queryset=incidents)
    paginator = Paginator(f.qs, 10)
    page = paginator.get_page(request.GET.get('page'))

    # Preserve active filters across pagination links.
    querystring = request.GET.copy()
    querystring.pop('page', None)

    return render(request, 'manage/dashboard.html', {
        'filter': f,
        'page_obj': page,
        'querystring': querystring.urlencode(),
        'status_choices': Incident.Status.choices,
        'can_edit': _require_editor(request),
        'can_create': _require_admin(request),
    })


@login_required
def incident_create(request):
    """Log a primary incident + N hazard images in one submit (LGU Admin)."""
    if not _require_admin(request):
        messages.error(request, 'Only LGU Admins can create incidents.')
        return redirect('manage-dashboard')

    if request.method == 'POST':
        form = IncidentForm(request.POST)
        formset = HazardImageFormSet(request.POST, request.FILES)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                incident = form.save(commit=False)
                incident.logged_by = request.user
                incident.save()
                formset.instance = incident
                formset.save()
            record_audit(request, 'incident.create',
                         incident_id=incident.id, via='formset',
                         images=incident.images.count())
            messages.success(request, f'Incident #{incident.id} logged with '
                                      f'{incident.images.count()} image(s).')
            return redirect('manage-incident-edit', pk=incident.id)
    else:
        form = IncidentForm()
        formset = HazardImageFormSet()

    return render(request, 'manage/incident_form.html', {
        'form': form, 'formset': formset, 'mode': 'create',
    })


@login_required
def incident_edit(request, pk):
    """Edit an incident. LGU Admins get the full form + image formset;
    Dispatchers get a status-only form; Public Viewers are read-only."""
    incident = get_object_or_404(Incident, pk=pk)
    is_admin = _require_admin(request)
    is_dispatcher = getattr(request.user, 'is_dispatcher', False)

    if not (is_admin or is_dispatcher):
        # Public Viewer — read-only detail.
        return render(request, 'manage/incident_detail.html', {'incident': incident})

    if is_admin:
        if request.method == 'POST':
            form = IncidentForm(request.POST, instance=incident)
            formset = HazardImageFormSet(request.POST, request.FILES, instance=incident)
            if form.is_valid() and formset.is_valid():
                with transaction.atomic():
                    form.save()
                    formset.save()
                record_audit(request, 'incident.update', incident_id=incident.id, via='formset')
                messages.success(request, f'Incident #{incident.id} updated.')
                return redirect('manage-incident-edit', pk=incident.id)
        else:
            form = IncidentForm(instance=incident)
            formset = HazardImageFormSet(instance=incident)
        return render(request, 'manage/incident_form.html', {
            'form': form, 'formset': formset, 'mode': 'edit', 'incident': incident,
        })

    # Dispatcher — status update only.
    if request.method == 'POST':
        form = IncidentStatusForm(request.POST, instance=incident)
        if form.is_valid():
            form.save()
            record_audit(request, 'incident.update',
                         incident_id=incident.id, status=incident.status, role='dispatcher')
            messages.success(request, f'Incident #{incident.id} status updated.')
            return redirect('manage-dashboard')
    else:
        form = IncidentStatusForm(instance=incident)
    return render(request, 'manage/incident_status.html', {
        'form': form, 'incident': incident,
    })
