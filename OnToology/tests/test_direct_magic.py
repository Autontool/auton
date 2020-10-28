import json
import string
import random
import shutil
import os
import pika
from subprocess import call
from .api_util import create_user, create_repo, delete_all_repos_from_db, get_repo_resource_dir, clone_if_not, delete_all_users
import logging
from OnToology import rabbit
from multiprocessing import Process
from django.test import Client
from unittest import TestCase
from django.test.testcases import SerializeMixin
from OnToology.models import OUser, Repo
# from OnToology.rabbit import start_pool
from time import sleep
from  .serializer import Serializer


rabbit_host = os.environ['rabbit_host']
queue_name = 'ontoology'


def get_logger(name, logdir="", level=logging.INFO):
    # logging.basicConfig(level=level)
    logger = logging.getLogger(name)
    if logdir != "":
        handler = logging.FileHandler(logdir)
    else:
        handler = logging.StreamHandler()
    #
    # handler = logging.FileHandler('property-output.log')
    formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)
    return logger


#logger = get_logger(__name__, level=logging.DEBUG)

class ABC():
    def error(self, msg):
        print(msg)
    def debug(self, msg):
        print(msg)
    def info(self, msg):
        print(msg)
# logger = {
#     "error": print,
#     "debug": print,
#     "info": print
# }
logger = ABC()

def get_pending_messages():
    print("get pending messages")
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(rabbit_host))
    except:
        print("exception 1 in connecting")
        sleep(3)
        connection = pika.BlockingConnection(pika.ConnectionParameters(rabbit_host))

    channel = connection.channel()
    queue = channel.queue_declare(queue=queue_name, durable=True, auto_delete=False)
    num = queue.method.message_count
    connection.close()
    sleep(0.1)
    return num


class TestDirectMagic(Serializer, TestCase):
    def setUp(self):
        print("setup DirectMagic")
        delete_all_users()
        if len(OUser.objects.all()) == 0:
            create_user()
        self.url = 'ahmad88me/ontoology-auto-test-no-res'
        self.user = OUser.objects.all()[0]

        logger.debug("rabbit host in test: "+rabbit_host)
        num_of_msgs = get_pending_messages()
        logger.debug("test> number of messages in the queue is: " + str(num_of_msgs))
        delete_all_repos_from_db()

# For the jongo test
    def test_generate_all_slash_direct_but_doc(self):
        print("######################test_generate_all_slash_direct_but_doc###############\n\n")
        import OnToology.settings as settings
        logger.error("testing the logger\n\n\n\n\n")
        resources_dir = get_repo_resource_dir(os.environ['test_user_email'])
        # The below two assertion is to protect the deletion of important files
        self.assertEqual(resources_dir.split('/')[-1], 'OnToology', msg='might be a wrong resources dir OnToology')
        self.assertIn(os.environ['test_user_email'], resources_dir, msg='might be a wrong resources dir or wrong user')
        # print "will delete %s" % resources_dir
        # comm = "rm -Rf %s" % resources_dir
        # print comm
        delete_all_repos_from_db()
        create_repo(url=self.url, user=self.user)
        clone_if_not(resources_dir, self.url)

        if not os.path.exists(resources_dir):
            os.mkdir(resources_dir)
        ontology_dir = os.path.join(resources_dir, 'alo.owl')
        if os.path.exists(ontology_dir):
            shutil.rmtree(ontology_dir)
        os.mkdir(ontology_dir)

        ontology_dir = os.path.join(resources_dir, 'geolinkeddata.owl')
        if os.path.exists(ontology_dir):
            shutil.rmtree(ontology_dir)
        os.mkdir(ontology_dir)

        # inject the configuration file
        f = open(os.path.join(resources_dir, 'alo.owl/OnToology.cfg'), 'w')
        conf_file_content = """
[ar2dtool]
enable = True

[widoco]
enable = False
languages = en,es,it
webVowl = False

[oops]
enable = True

[owl2jsonld]
enable = True
                """
        f.write(conf_file_content)
        f.close()

        # inject the configuration file with the multi-lang
        f = open(os.path.join(resources_dir, 'geolinkeddata.owl/OnToology.cfg'), 'w')
        conf_file_content = """
[ar2dtool]
enable = False

[widoco]
enable = False
languages = en,es,it
webVowl = False

[oops]
enable = False

[owl2jsonld]
enable = False
                        """
        f.write(conf_file_content)
        f.close()

        logger.debug("pre API> number of messages count: " + str(get_pending_messages()))
        j = {
            "repo": self.url,
            "useremail": self.user.email,
            "changedfiles": ["alo.owl", ],
            "branch": "master",
            "action": "magic"
        }
        print("going to rabbit: ")
        rabbit.handle_action(j, logger)
        print("returned from rabbit")
        self.assertEqual(1, len(Repo.objects.all()))
        repo = Repo.objects.all()[0]

        files_to_check = ['alo.owl/OnToology.cfg',]
        docs_files = ['index-en.html', 'ontology.xml', '.htaccess', 'alo.owl.widoco.conf']
        diagrams_files = ['ar2dtool-class/alo.owl.png', 'ar2dtool-taxonomy/alo.owl.png']

        # Test block
        cmd_p = os.path.join(resources_dir, files_to_check[0])
        logger.debug(cmd_p)
        cmd_pp = "/".join(cmd_p.split("/")[:-1])
        logger.debug(cmd_pp)
        cmd = "ls -ltra " + cmd_pp
        logger.debug("\n\n cmd: "+cmd)
        stream = os.popen(cmd)
        output = stream.read()
        logger.debug(output)


        # os.system(cmd)
        eval_files = ['oops.html']
        # for f in docs_files:
        #     ff = os.path.join('alo.owl/documentation', f)
        #     files_to_check.append(ff)
        for f in diagrams_files:
            ff = os.path.join('alo.owl/diagrams', f)
            files_to_check.append(ff)
        for f in eval_files:
            ff = os.path.join('alo.owl/evaluation', f)
            files_to_check.append(ff)
        for f in files_to_check:
            print(os.path.join(resources_dir, f))
            self.assertTrue(os.path.exists(os.path.join(resources_dir, f)), msg=(f+" does not exists"))
        delete_all_repos_from_db()
        # p.terminate()
        print("---------------\n\n\n\n\n----------test_generate_all_check_generated_resources_slash###############\n\n")
