"""Custom response when django-axes locks out a client."""
from django.http import JsonResponse
from django.shortcuts import render

MESSAGE = (
    'Account temporarily locked due to too many failed login attempts. '
    'Please try again later or contact an LGU administrator.'
)


def lockout_response(request, credentials=None, *args, **kwargs):
    """429 — JSON for API/JWT clients, an HTML page for browser form logins."""
    if request.path.startswith('/api/'):
        return JsonResponse({'error': MESSAGE, 'locked': True}, status=429)
    return render(request, 'manage/lockout.html', {'message': MESSAGE}, status=429)
