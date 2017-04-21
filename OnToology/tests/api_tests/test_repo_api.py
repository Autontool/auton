import json
import string
import random

import os
from . import create_user, delete_all_repos, create_repo

from django.test import Client
from unittest import TestCase
from OnToology.models import *


class TestRepoAPI(TestCase):
    def setUp(self):
        if len(OUser.objects.all()) == 0:
            create_user()
        self.url = 'ahmad88me/demo'
        self.owner = StringField(max_length=100, default='no')
        self.user = OUser.objects.all()[0]

    def test_add_repo(self):
        c = Client()
        response = c.post('/api/repos', {'url': self.url, 'owner': self.user.username},
                          HTTP_AUTHORIZATION='Token '+self.user.token)
        self.assertEqual(response.status_code, 201,
                         msg='repo is not created, status_code: '+str(response.status_code)+response.content)
        self.assertGreaterEqual(len(Repo.objects.all()), 1, msg='repo is not added')
        delete_all_repos()

    def test_add_repo_missing_parameters(self):
        c = Client()
        response = c.post('/api/repos',
                          HTTP_AUTHORIZATION='Token '+self.user.token)
        self.assertEqual(response.status_code, 400)

    def test_add_repo_authorization(self):
        c = Client()
        response = c.post('/api/repos', {'url': self.url, 'owner': self.user.username},
                          HTTP_AUTHORIZATION='Token ' + self.user.token+"wrong")
        self.assertEqual(response.status_code, 401)

    def test_list_repos(self):
        create_repo()
        c = Client()
        response = c.get('/api/repos', HTTP_AUTHORIZATION='Token '+self.user.token)
        self.assertEqual(response.status_code, 200, msg=response.content)
        jresponse = json.loads(response.content)
        self.assertIn('repos', jresponse, msg='repos is not in the response')
        self.assertEqual(jresponse['repos'][0], Repo.objects.all()[0].json())
        delete_all_repos()

    def test_delete_repo(self):
        create_repo()
        repoid = str(Repo.objects.all()[0].id)
        c = Client()
        response = c.delete('/api/repos/'+repoid, HTTP_AUTHORIZATION='Token ' + self.user.token)
        self.assertEqual(response.status_code, 204, msg=response.content)
        self.assertEqual(len(Repo.objects.all()), 0, msg="the repo is not deleted")
        delete_all_repos()