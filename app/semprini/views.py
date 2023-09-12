import os
import requests
import logging
import traceback

from django.shortcuts import redirect, render
from django.urls import reverse
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.contrib.auth import logout, login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages


def heartbeat(request):
    return JsonResponse({ 'build_number': f'{os.environ.get("BUILD_NUMBER", "0")}' })


@login_required
def mylogout(request):
    logout(request)
    return redirect(reverse("snip:index", args=(), kwargs={}))


def login_github(request):
    client_id = settings.GITHUB_CLIENT_ID
    scope = 'read:user'
    state = 'dontpanic'  # to prevent csrf
    return redirect(
        'https://github.com/login/oauth/authorize?client_id={}&scope={}&state={}'.format(client_id,
                                                                                         scope, state,
                                                                                         ))


def login_github_callback(request):
    # verify the state variable value for csrf
    code = request.GET.get('code', None)

    if not code:
        messages.error(request, "Invalid Code received from Github Auth API");
        logging.getLogger('error').error('code not present in request {}'.format(request.GET))
        return redirect(reverse("app:index", args=(), kwargs={}))

    # first redirect
    params = {
        'client_id': settings.GITHUB_CLIENT_ID,
        'client_secret': settings.GITHUB_SECRET,
        'code': code,
        'Content-Type': 'application/json'
    }

    headers = {
        'Accept': 'application/json'
    }

    # get an access token
    result = requests.post('https://github.com/login/oauth/access_token', data=params, headers=headers)
    token = result.json().get('access_token')
    logging.getLogger('info').info('token received in response from github')

    # after getting the token, access the user api to get user details
    user_api_url = 'https://api.github.com/user'
    headers = {
        'Authorization': 'token ' + token,
        'Accept': 'application/json'
    }
    result = requests.get(user_api_url, headers=headers)
    user_data = result.json()
    logging.getLogger('info').info('user data from github {}'.format(user_data))
    email = user_data.get('email', None)
    if not email:
        email=""

    username = user_data.get('login', None)
    if not username:
        messages.error(request, "Invalid data received from GitHub")
        logging.getLogger('error').error('login not present in data received from github {}'.format(user_data))
        return redirect("/")

    # get the user details, now login this user.
    try:
        user = User.objects.get(username=username)
        logging.getLogger('info').info('user already exists in db')
    except User.DoesNotExist as e:
        # if user does not exists in db, create a user and save it.
        name = user_data.get('name', None)
        if name:
            splitted_name = name.split(' ')
            first_name = splitted_name[0]
            if len(splitted_name) > 1:
                last_name = splitted_name[1]
            else:
                last_name = ''
        else:
            first_name = ''
            last_name = ''

        # create user
        user = User()
        user.username = username
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.is_admin = False
        user.is_active = True
        user.is_superuser = False

        user.save()
        logging.getLogger('info').info('user created in db')

    except Exception as e:
        messages.error(request, "Some error occurred while logging. Please let us know.")
        logging.getLogger('error').error(traceback.format_exc())

    login(request, user)
    messages.success(request, "Login Successful")
    return redirect('/')
