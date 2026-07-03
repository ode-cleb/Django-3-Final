from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST


@ensure_csrf_cookie
def account_view(request):
    return render(request, 'account/account.html',
                  {'form': AuthenticationForm()})


@require_POST
def login_view(request):
    form = AuthenticationForm(request, data=request.POST)
    if form.is_valid():
        login(request, form.get_user())
        html = render_to_string('account/_logged_in.html', request=request)
        return JsonResponse({'html': html})
    return JsonResponse({'errors': form.errors}, status=400)


@require_POST
def logout_view(request):
    logout(request)
    html = render_to_string('account/_login_form.html',
                            {'form': AuthenticationForm()}, request=request)
    return JsonResponse({'html': html})