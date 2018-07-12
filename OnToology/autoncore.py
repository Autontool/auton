#!/usr/bin/python
#
# Copyright 2012-2013 Ontology Engineering Group, Universidad Politecnica de Madrid, Spain
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
# @author Ahmad Alobaid
#




from github import Github
from datetime import datetime
from subprocess import call
import string
import random
import time
import StringIO
import settings
import io

from __init__ import *

import Integrator


import shutil
import logging

from mongoengine import *


from urllib import quote


use_database = True

ToolUser = 'OnToologyUser'


parent_folder = None



publish_dir = os.environ['publish_dir']
home = os.environ['github_repos_dir']  # e.g. home = 'blahblah/temp/'
verification_log_fname = 'verification.log'
sleeping_time = 7
refresh_sleeping_secs = 10  # because github takes time to refresh
ontology_formats = ['.rdf', '.owl', '.ttl']
g = None
log_file_dir = None  # '&1'#which is stdout #sys.stdout#by default
tools_conf = {
    'ar2dtool': {'folder_name': 'diagrams', 'type': 'png'},
    'widoco': {'folder_name': 'documentation'},
    'oops': {'folder_name': 'evaluation'},
    'owl2jsonld': {'folder_name': 'context'}
}


def prepare_logger(user, ext='.log_new'):
    sec = ''.join([random.choice(string.ascii_letters + string.digits) for _ in range(9)])
    l = os.path.join(home, 'log', user + sec + ext)
    f = open(l, 'w')
    f.close()
    logging.basicConfig(filename=l, format='%(asctime)s %(levelname)s: %(message)s', level=logging.DEBUG)
    return l


def dolog(msg):
    logging.critical(msg)


def init_g():
    global g
    username = os.environ['github_username']
    password = os.environ['github_password']
    g = Github(username, password)


def git_magic(target_repo, user, changed_filesss):
    logger_fname = prepare_logger(user)
    global g
    global parent_folder
    global log_file_dir
    parent_folder = user
    if not settings.test_conf['local']:
        prepare_log(user)
    dolog('############################### magic #############################')
    dolog('target_repo: ' + target_repo)
    change_status(target_repo, 'Preparing')
    from models import Repo
    drepo = Repo.objects.get(url=target_repo)
    drepo.clear_ontology_status_pairs()
    for ftov in changed_filesss:
        if ftov[-4:] in ontology_formats:
            if ftov[:len('OnToology/')] != 'OnToology/':  # This is to solve bug #265
                drepo.update_ontology_status(ontology=ftov, status='pending')
    # so the tool user can takeover and do stuff
    username = os.environ['github_username']
    password = os.environ['github_password']
    g = Github(username, password)
    local_repo = target_repo.replace(target_repo.split('/')[-2], ToolUser)
    if not settings.test_conf['local']:
        delete_repo(local_repo)
        time.sleep(refresh_sleeping_secs)
    dolog('repo deleted')
    if not settings.test_conf['local'] or settings.test_conf['fork'] or settings.test_conf['clone']:  # in case it is not test or test with fork option
        dolog('will fork the repo')
        change_status(target_repo, 'forking repo')
        forked_repo = fork_repo(target_repo)
        cloning_url = forked_repo.ssh_url
        time.sleep(refresh_sleeping_secs)
        dolog('repo forked')
        drepo.progress = 10.0
        drepo.save()
    else:
        print "no fork"
    if not settings.test_conf['local'] or settings.test_conf['clone']:
        change_status(target_repo, 'cloning repo')
        clone_repo(cloning_url, user)
        dolog('repo cloned')
        drepo.progress = 20.0
    files_to_verify = []
    # print "will loop through changed files"
    if log_file_dir is None:
        prepare_log(user)

    Integrator.tools_execution(changed_files=changed_filesss, base_dir=os.path.join(home, user), logfile=log_file_dir,
                               target_repo=target_repo, g_local=g, dolog_fname=logger_fname,
                               change_status=change_status, repo=drepo)

    exception_if_exists = ""
    files_to_verify = [c for c in changed_filesss if c[-4:] in ontology_formats]
    for c in changed_filesss:
        if c[:-4] in ontology_formats:
            print "file to verify: "+c
        else:
            print "c: %s c-4: %s" % (c, c[-4:])

    # After the loop
    dolog("number of files to verify %d" % (len(files_to_verify)))
    if len(files_to_verify) == 0:
        print "files: "+str(files_to_verify)
        change_status(target_repo, 'Ready')
        drepo.progress = 100
        drepo.save()
        return
    # if not test or test with push
    if not settings.test_conf['local'] or settings.test_conf['push']:
        commit_changes()
        dolog('changes committed')
    else:
        print 'No push for testing'
    remove_old_pull_requests(target_repo)
    if exception_if_exists == "":  # no errors
        change_status(target_repo, 'validating')
    else:
        change_status(target_repo, exception_if_exists)
        # in case there is an error, create the pull request as well
    # Now to enabled
    # This kind of verification is too naive and need to be eliminated
    # for f in files_to_verify:
    #     repo = None
    #     if use_database:
    #         from models import Repo
    #         repo = Repo.objects.get(url=target_repo)
    #     try:
    #         verify_tools_generation_when_ready(f, repo)
    #         dolog('verification is done successfully')
    #     except Exception as e:
    #         dolog('verification have an exception: ' + str(e))

    if use_database:
        if Repo.objects.get(url=target_repo).state != 'validating':
            r = Repo.objects.get(url=target_repo)
            s = r.state
            s = s.replace('validating', '')
            r.state = s
            r.save()
            # The below "return" is commented so pull request are created even if there are files that are not generated
    # if not testing or testing with pull enabled
    if settings.test_conf['pull']:
        print "pull is true"
    else:
        print "pull is false"
    if not settings.test_conf['local'] or settings.test_conf['pull']:
        change_status(target_repo, 'creating a pull request')
        try:
            r = send_pull_request(target_repo, ToolUser)
            dolog('pull request is sent')
            change_status(target_repo, 'pull request is sent')
            change_status(target_repo, 'Ready')
        except Exception as e:
            exception_if_exists += str(e)
            dolog('failed to create pull request: '+exception_if_exists)
            change_status(target_repo, 'failed to create a pull request')
    else:
        print 'No pull for testing'
    drepo.progress = 100
    drepo.save()
    # change_status(target_repo, 'Ready')


def verify_tools_generation_when_ready(ver_file_comp, repo=None):
    ver_file = os.path.join(get_target_home(), ver_file_comp['file'], verification_log_fname)
    ver_file = get_abs_path(ver_file)
    dolog('ver file: ' + ver_file)
    if ver_file_comp['ar2dtool_enable'] == ver_file_comp['widoco_enable'] == ver_file_comp['oops_enable'] == ver_file_comp['owl2jsonld_enable'] == False:
        return
    for i in range(20):
        time.sleep(15)
        f = open(ver_file, "r")
        s = f.read()
        f.close()
        if ver_file_comp['ar2dtool_enable'] and 'ar2dtool' not in s:
            continue
        if ver_file_comp['widoco_enable'] and 'widoco' not in s:
            continue
        if ver_file_comp['oops_enable'] and 'oops' not in s:
            continue
        if ver_file_comp['owl2jsonld_enable'] and 'owl2jsonld' not in s:
            continue
        os.remove(ver_file)  # the verification file is no longer needed
        dolog('The removed file is: ' + ver_file)
        return verify_tools_generation(ver_file_comp, repo)
    repo.state = ver_file_comp['file'] + \
        ' is talking too much time to generate output'
    if settings.test_conf['local']:
        assert False, 'Taking too much time for verification'
    else:  # I want to see the file in case of testing
        os.remove(ver_file)  # the verification file is no longer needed


def update_file(target_repo, path, message, content, branch=None):
    global g
    username = os.environ['github_username']
    password = os.environ['github_password']
    g = Github(username, password)
    repo = g.get_repo(target_repo)
    if branch is None:
        sha = repo.get_file_contents(path).sha
        dolog('default branch with file sha: %s' % str(sha))
    else:
        sha = repo.get_file_contents(path, branch).sha
        dolog('branch %s with file %s sha: %s' % (branch, path, str(sha)))
    apath = path
    if apath[0] != "/":
        apath = "/" + apath.strip()
    dolog("username: " + username)
    dolog('will update the file <%s> on repo<%s> with the content <%s>,  sha <%s> and message <%s>' %
          (apath, target_repo, content, sha, message))
    dolog("repo.update_file('%s', '%s', \"\"\"%s\"\"\" , '%s' )" % (apath, message, content, sha))
    for i in range(3):
        try:
            if branch is None:
                repo.update_file(apath, message, content, sha)
            else:
                repo.update_file(apath, message, content, sha, branch=branch)
            dolog('file updated')
            return
        except:
            dolog('chance #%d file update' % i)
            time.sleep(1)
    dolog('after 10 changes, still could not update ')
    # so if there is a problem it will raise an exception which will be captured by the calling function
    repo.update_file(apath, message, content, sha)


def verify_tools_generation(ver_file_comp, repo=None):
    # AR2DTool
    if ver_file_comp['ar2dtool_enable']:
        target_file = os.path.join(get_abs_path(get_target_home()),
                                   ver_file_comp['file'],
                                   tools_conf['ar2dtool']['folder_name'],
                                   ar2dtool.ar2dtool_config_types[0][:-5],
                                   get_file_from_path(ver_file_comp['file']) +
                                   "." + tools_conf['ar2dtool']['type'] +
                                   '.graphml')
        file_exists = os.path.isfile(target_file)
        if repo is not None and not file_exists:
            repo.state += ' The Diagram of the file %s is not generated ' % \
                (ver_file_comp['file'])
            repo.save()
        if settings.test_conf['local']:
            assert file_exists, 'the file %s is not generated' % (target_file)
        elif not file_exists:
            dolog('The Diagram of the file %s is not generated ' %
                  (ver_file_comp['file']))
    # Widoco
    if ver_file_comp['widoco_enable']:
        target_file = os.path.join(get_abs_path(get_target_home()), ver_file_comp['file'],
                                   tools_conf['widoco']['folder_name'],
                                   'index.html')
        file_exists = os.path.isfile(target_file)
        if repo is not None and not file_exists:
            repo.state += ' The Documentation of the file %s if not generated ' % (
                ver_file_comp['file'])
            repo.save()
        if settings.test_conf['local']:
            assert file_exists, 'the file %s is not generated' % (target_file)
        elif not file_exists:
            dolog('The Documentation of the file %s if not generated ' %
                  (ver_file_comp['file']))
    # OOPS
    if ver_file_comp['oops_enable']:
        target_file = os.path.join(get_abs_path(get_target_home()), ver_file_comp['file'],
                                   tools_conf['oops']['folder_name'],
                                   'oopsEval.html')
        file_exists = os.path.isfile(target_file)
        if repo is not None and not file_exists:
            repo.state += ' The Evaluation report of the file %s if not generated ' % (
                ver_file_comp['file'])
            repo.save()
        if settings.test_conf['local']:
            assert file_exists, 'the file %s is not generated' % (target_file)
        elif not file_exists:
            dolog('The Evaluation report of the file %s if not generated ' %
                  (ver_file_comp['file']))
    # owl2jsonld
    if ver_file_comp['owl2jsonld_enable']:
        target_file = os.path.join(get_abs_path(get_target_home()),
                                   ver_file_comp['file'],
                                   tools_conf['owl2jsonld']['folder_name'],
                                   'context.jsonld')
        file_exists = os.path.isfile(target_file)
        if repo is not None and not file_exists:
            repo.state += ' The Context documentation of the file %s if not generated ' % (
                ver_file_comp['file'])
            repo.save()
        if settings.test_conf['local']:
            assert file_exists, 'the file %s is not generated' % (target_file)
        elif not file_exists:
            dolog('The Context documentation of the file %s if not generated ' %
                  (ver_file_comp['file']))

    if 'not generated' in repo.state:
        repo = g.get_repo(repo.url)
        for iss in repo.get_issues():
            if 'OnToology error notification' in iss.title:
                iss.edit(state='closed')
        repo.create_issue('OnToology error notification', repo.state)


def get_ontologies_from_a_submodule(path, url):
    """
    :param path: local path within the repository
    :param url: url of the repository
    :return: list of detected ontologies
    """
    global g
    ontologies = []
    print "get_ontologies_from_a_submodule: path=%s and url=%s" % (path, url)
    try:
        target_repo = ("/".join(url.split('/')[-2:])).strip()[:-4]
        repo = g.get_repo(target_repo)
        sha = repo.get_commits()[0].sha
        files = repo.get_git_tree(sha=sha, recursive=True).tree
        ontoology_home_name = 'OnToology'
        for f in files:
            if f.path[:len(ontoology_home_name)] != ontoology_home_name:
                if f.type == 'blob':
                    for ontfot in ontology_formats:
                        if f.path[-len(ontfot):] == ontfot:
                            print "get_ontologies_from_a_submodule f.path: %s" % f.path
                            ontologies.append(os.path.join(path, f.path))
                            break
    except Exception as e:
        print "get_ontologies_from_a_submodule exception: "+str(e)
    return ontologies


def get_ontologies_from_submodules_tree(tree, repo):
    """
    :param tree: a github tree
    :param repo: a repo object from GitHub
    :return: a list of detected ontologies
    """
    ontologies = []
    submodule_tree_elements = [f for f in tree if f.path == '.gitmodules']
    if len(submodule_tree_elements) == 1:
        config_parser = ConfigParser.RawConfigParser()
        file_content = repo.get_file_contents(submodule_tree_elements[0].path).decoded_content
        print "file_content"
        print file_content
        file_content = file_content.replace('\t', '')  # because it was containing \t
        config_parser.readfp(io.BytesIO(file_content))
        sections = config_parser.sections()

        for sec in sections:
            p = config_parser.get(sec, "path")
            u = config_parser.get(sec, "url")
            ontologies += get_ontologies_from_a_submodule(path=p, url=u)
    return ontologies


def get_ontologies_in_online_repo(target_repo):
    global g
    ontologies = []
    if type(g) == type(None):
        init_g()
    try:
        repo = g.get_repo(target_repo)
        sha = repo.get_commits()[0].sha
        files = repo.get_git_tree(sha=sha, recursive=True).tree
        ontoology_home_name = 'OnToology'

        for f in files:
            if f.path[:len(ontoology_home_name)] != ontoology_home_name:
                if f.type == 'blob':
                    for ontfot in ontology_formats:
                        if f.path[-len(ontfot):] == ontfot:
                            ontologies.append(f.path)
                            break
        ontologies += get_ontologies_from_submodules_tree(files, repo)
    except Exception as e:
        print "get_ontologies_in_online_repo exception: "+str(e)
    return ontologies


def prepare_log(user):
    global log_file_dir
    global default_stderr
    global default_stdout
    file_dir = build_file_structure(user + '.log', 'log', home)
    f = open(file_dir, 'w')
    log_file_dir = file_dir
    return f


def is_organization(target_repo):
    return g.get_repo(target_repo).organization is not None


def has_access_to_repo(target_repo):
    global g
    id = g.get_user().id
    if is_organization(target_repo):
        try:
            collaborators = g.get_repo(target_repo).get_collaborators()
            for coll in collaborators:
                if id == coll.id:
                    return True
            return False
        except:
            return False
    return True


def delete_repo(local_repo):
    global g
    if g is None:
        init_g()
    try:
        g.get_repo(local_repo).delete()
        dolog('repo deleted ')
    except:
        dolog('the repo doesn\'t exists [not an error]')


def fork_repo(target_repo):
    """
    :param target_repo: username/reponame
    :return: forked repo (e.g. OnToologyUser/reponame)
    """
    # the wait time to give github sometime so the repo can be forked
    # successfully
    time.sleep(sleeping_time)
    # this is a workaround and not a proper way to do a fork
    # comm = "curl --user \"%s:%s\" --request POST --data \'{}\' https://api.github.com/repos/%s/forks" % (
    #     username, password, target_repo)
    # if not settings.test_conf['local']:
    #     comm += ' >> "' + log_file_dir + '"'
    # dolog(comm)
    # call(comm, shell=True)
    username = os.environ['github_username']
    password = os.environ['github_password']
    gg = Github(username, password)
    repo = gg.get_repo(target_repo)
    user = gg.get_user()
    forked_repo = user.create_fork(repo)
    dolog('forked to: '+forked_repo.name)
    return forked_repo


def clone_repo(cloning_url, parent_folder, dosleep=True):
    global g
    if g is None:
        init_g()
    dolog('home: %s' % (home))
    dolog('parent_folder: %s' % (parent_folder))
    #dolog('logfile: %s' % (log_file_dir))
    if dosleep:
        # the wait time to give github sometime so the repo can be cloned
        time.sleep(sleeping_time)
    try:
        # comm = "rm" + " -Rf " + home + parent_folder
        comm = "rm" + " -Rf " + os.path.join(home, parent_folder)
        # if not settings.test_conf['local']:
        #     comm += ' >> "' + log_file_dir + '"'
        dolog(comm)
        call(comm, shell=True)
    except Exception as e:
        dolog('rm failed: ' + str(e))
    # comm = "git" + " clone" + " " + cloning_repo + " " + home + parent_folder
    comm = "git clone --recurse-submodules  " + cloning_url + " " + os.path.join(home, parent_folder)
    # if not settings.test_conf['local']:
    #     comm += ' >> "' + log_file_dir + '"'
    dolog(comm)
    print "comm: %s" % comm
    call(comm, shell=True)
    # Change ownership to solve the problem of permission denied to create OnToology.cfg file
    comm = 'chown $USER  "%s"' % os.path.join(home, parent_folder)
    print "chown command: "
    print comm
    dolog(comm)
    call(comm, shell=True)
    # comm = "chmod -R 777 " + home + parent_folder
    # if not settings.TEST:
    #     comm += ' >> "' + log_file_dir + '"'
    # dolog(comm)
    # call(comm, shell=True)
    # return home + parent_folder
    return os.path.join(home, parent_folder)


def commit_changes():
    global g
    if g is None:
        init_g()
    gu = 'git config  user.email "ontoology'+'@delicias.dia.fi.upm.es";'
    gu += 'git config  user.name "%s" ;' % (ToolUser)
    # comm = "cd " + home + parent_folder + ";" + gu + " git add . "
    comm = "cd " + os.path.join(home, parent_folder) + ";" + gu + " git add . "
    if not settings.test_conf['local']:
        comm += ' >> "' + log_file_dir + '"'
    dolog(comm)
    call(comm, shell=True)

    # comm = "cd " + home + parent_folder + ";" + \
    comm = "cd " + os.path.join(home, parent_folder) + ";" + \
           gu + " git commit -m 'automated change' "
    if not settings.test_conf['local']:
        comm += ' >> "' + log_file_dir + '"'
    dolog(comm)
    call(comm, shell=True)
    gup = "git config push.default matching;"
    # comm = "cd " + home + parent_folder + ";" + gu + gup + " git push "
    comm = "cd " + os.path.join(home, parent_folder) + ";" + gu + gup + " git push "
    if not settings.test_conf['local']:
        comm += ' >> "' + log_file_dir + '"'
    dolog(comm)
    call(comm, shell=True)


def refresh_repo(target_repo):
    global g
    if g is None:
        init_g()
    local_repo = target_repo.split('/')[-1]
    g.get_user().get_repo(local_repo).delete()
    g.get_user().create_fork(target_repo)


def remove_old_pull_requests(target_repo):
    global g
    if g is None:
        init_g()
    title = 'OnToology update'
    for p in g.get_repo(target_repo).get_pulls():
        try:
            if p.title == title:
                p.edit(state="closed")
        except Exception as e:
            print "Exception removing an old pull request: "+str(e)
            dolog("Exception removing an old pull request: "+str(e))


def send_pull_request(target_repo, username):
    title = 'OnToology update'
    body = title
    err = ""
    time.sleep(sleeping_time)
    repo = g.get_repo(target_repo)
    try:
        repo.create_pull(head=username + ':master', base='master', title=title, body=body)
        return {'status': True, 'msg': 'pull request created successfully'}
    except Exception as e:
        err = str(e)
        dolog('pull request error: ' + err)
        if 'No commits between' in err:
            dolog('pull request detecting no commits')
            repo.notes = 'No difference to generate the pull request, make a change in the repo so the pull request can be generated.'
            repo.save()
    return {'status': False, 'error': err}


def webhook_access(client_id, redirect_url, isprivate):
    if isprivate:
        scope = 'repo'
    else:
        scope = 'public_repo'
    # scope = 'admin:org_hook'
    # scope+=',admin:org,admin:public_key,admin:repo_hook,gist,notifications,delete_repo,repo_deployment,
    # repo,public_repo,user,admin:public_key'
    sec = ''.join([random.choice(string.ascii_letters + string.digits)
                   for _ in range(9)])
    return "https://github.com/login/oauth/authorize?client_id=" + client_id + "&redirect_uri=" +\
           redirect_url + "&scope=" + scope + "&state=" + sec, sec


def get_user_github_email(username):
    try:
        return g.get_user(username).email
    except:
        return None


def remove_webhook(target_repo, notification_url):
    global g
    if g is None:
        init_g()
    # for some reason adding the below two prints solves the problem for removing the webhook, strange but true
    print "target_repo: "+str(target_repo)
    print "notification url: "+str(notification_url)
    for hook in g.get_repo(target_repo).get_hooks():
        try:
            if hook.config["url"] == notification_url:
                hook.delete()
                break
        except Exception as e:
            print "error removing the webhook: %s" %(str(e))
            time.sleep(2)
    sys.stdout.flush()
    sys.stderr.flush()


def add_webhook(target_repo, notification_url, newg=None):
    global g
    if newg is None:
        if g is None:
            init_g()
        newg = g
    name = "web"
    active = True
    events = ["push"]
    config = {
        "url": notification_url,
        "content_type": "form"
    }
    try:
        newg.get_repo(target_repo).create_hook(name, config, events, active)
        return {'status': True}
    except Exception as e:
        return {'status': False, 'error': str(e)}  # e.data}


def add_collaborator(target_repo, user, newg=None):
    global g
    if newg is None:
        if g is None:
            init_g()
        newg = g
    try:
        print "adding collaborator from user: %s " % str(newg.get_user().name)
        if newg.get_user().name is None or newg.get_user().email is None:
            return {'status': False, 'error': 'Make sure you have your name and email public and not empty on GitHub'}
        if newg.get_repo(target_repo).has_in_collaborators(user):
            return {'status': True, 'msg': 'this user is already a collaborator'}
        else:
            invitation = newg.get_repo(target_repo).add_to_collaborators(user)
            if invitation is None:
                print "no invitation is created"
                {'status': False, 'error': 'Invitation is not generated'}
            else:
                try:
                    username = os.environ['github_username']
                    password = os.environ['github_password']
                    g_ontoology_user = Github(username, password)
                    g_ontoology_user.get_user().accept_invitation(invitation)
                    print "invitation accepted: "+str(invitation)
                    return {'status': True, 'msg': 'added as a new collaborator'}
                except Exception as e:
                    print "exception: "+str(e)
                    print "invitation not accepted or invalid: "+str(invitation)
                    return {'status': False, 'error': 'Could not accept the invitation for becoming a collaborator'}
    except Exception as e:
        return {'status': False, 'error': str(e)}  # e.data}


def previsual(useremail, target_repo):
    from Integrator.previsual import start_previsual
    try:
        OUser.objects.all()
    except:
        django_setup_script()
    from OnToology.models import OUser
    user = OUser.objects.filter(email=useremail)
    if len(user) != 1:
        error_msg = "%s is invalid email %s" % useremail
        print(error_msg)
        dolog("previsual> "+error_msg)
        return error_msg
    user = user[0]
    found = False
    repo = None
    for r in user.repos:
        if target_repo == r.url:
            found = True
            repo = r
            break
    if found:
        dolog("previsual> "+"repo is found and now generating previsualization")
        repo.state = 'Generating Previsualization'
        repo.notes = ''
        repo.previsual_page_available = True
        repo.save()
        #prepare_log(user.email)
        # cloning_repo should look like 'git@github.com:AutonUser/target.git'
        cloning_repo = 'git@github.com:%s.git' % target_repo
        sec = ''.join([random.choice(string.ascii_letters + string.digits) for _ in range(4)])
        folder_name = 'prevclone-' + sec
        clone_repo(cloning_repo, folder_name, dosleep=True)
        repo_dir = os.path.join(home, folder_name)
        dolog("previsual> will call start previsual")
        msg = start_previsual(repo_dir, target_repo)
        if msg == "":  # not errors
            dolog("previsual> completed successfully")
            repo.state = 'Ready'
            repo.save()
            return ""
        else:
            repo.notes = msg
            repo.state = 'Ready'
            repo.save()
            return msg
    else:  # not found
        repo.state = 'Ready'
        repo.save()
        error_msg = 'You should add the repo while you are logged in before the revisual renewal'
        dolog("previsual> "+error_msg)
        return error_msg


def update_g(token):
    global g
    g = Github(token)


def get_file_content(target_repo, path, branch=None):
    global g
    username = os.environ['github_username']
    password = os.environ['github_password']
    g = Github(username, password)
    repo = g.get_repo(target_repo)
    #sha = repo.get_file_contents(path).sha
    if branch is None:
        return repo.get_file_contents(path).decoded_content
    else:
        return repo.get_file_contents(path, branch).decoded_content


def generate_bundle(base_dir, target_repo, ontology_bundle):
    """
    :param base_dir: e.g. /home/user/temp/random-folder-xyz
    :param target_repo:  user/reponame
    :param ontology_bundle: OnToology/abc/alo.owl
    :return: the bundle zip file dir if successful, or None otherwise
    """
    global g
    if g is None:
        init_g()
    try:
        print 'ontology bundle: '+ontology_bundle
        repo = g.get_repo(target_repo)
        sha = repo.get_commits()[0].sha
        files = repo.get_git_tree(sha=sha, recursive=True).tree
        print 'num of files: '+str(len(files))
        for f in files:
            try:
                for i in range(3):
                    try:
                        print 'f: '+str(f)
                        print 'next: '+str(f.path)
                        p = f.path
                        break
                    except:
                        time.sleep(2)
                p = f.path
                if p[0] == '/':
                    p = p[1:]
                abs_path = os.path.join(base_dir, p)
                if p[:len(ontology_bundle)] == ontology_bundle:
                    print 'true: '+str(p)
                    if f.type == 'tree':
                        os.makedirs(abs_path)
                    elif f.type == 'blob':
                        parent_folder = os.path.join(*abs_path.split('/')[:-1])
                        if parent_folder != base_dir: # not in the top level of the repo
                            try:
                                os.makedirs(parent_folder)
                            except:
                                pass
                        with open(abs_path, 'w') as fii:
                            file_content = repo.get_file_contents(f.path).decoded_content
                            fii.write(file_content)
                            print 'file %s content: %s' % (f.path, file_content[:10])
                    else:
                        print 'unknown type in generate bundle'
                else:
                    print 'not: '+p
            except Exception as e:
                print 'exception: '+str(e)
        zip_file = os.path.join(base_dir, '%s.zip' % ontology_bundle.split('/')[-1])
        comm = "cd %s; zip -r '%s' OnToology" % (base_dir, zip_file)
        print 'comm: %s' % comm
        call(comm, shell=True)
        return os.path.join(base_dir, zip_file)
        #return None
    except Exception as e:
        print 'error in generate_bundle: '+str(e)
        return None


def publish(name, target_repo, ontology_rel_path, useremail):
    """
    To publish the ontology via github.
    :param name:
    :param target_repo:
    :param ontology_rel_path:
    :param user:
    :return: error message, it will return an empty string if everything went ok
    """
    try:
        OUser.objects.all()
    except:
        django_setup_script()
    from OnToology.models import OUser, PublishName, Repo
    error_msg = ""
    found = False
    try:
        user = OUser.objects.get(email=useremail)
        dolog("publish> user is found")
    except Exception as e:
        error_msg = "user is not found"
        dolog("publish> error: %s" % str(e))
        return error_msg
    for r in user.repos:
        if target_repo == r.url:
            found = True
            repo = r
            break
    if ontology_rel_path[0] == '/':
        ontology_rel_path = ontology_rel_path[1:]
    if ontology_rel_path[-1] == '/':
        ontology_rel_path = ontology_rel_path[:-1]
    ontology_rel_path_with_slash = "/"+ontology_rel_path
    name = ''.join(ch for ch in name if ch.isalnum() or ch == '_')
    if found:  # if the repo belongs to the user
        if len(PublishName.objects.filter(name=name)) > 1:
            error_msg = 'a duplicate published names, please contact us ASAP to fix it'
            dolog("publish> "+error_msg)
            return error_msg

        if (len(PublishName.objects.filter(name=name)) == 0 and
                len(PublishName.objects.filter(user=user, ontology=ontology_rel_path_with_slash, repo=repo)) > 0):
            error_msg = 'can not reserve multiple names for the same ontology'
            dolog("publish> "+error_msg)
            return error_msg

        if len(PublishName.objects.filter(name=name)) == 1 and len(
                PublishName.objects.filter(user=user, ontology=ontology_rel_path_with_slash, repo=repo)) == 0:
            error_msg = "This name is already taken, please choose a different one"
            dolog("publish> "+error_msg)
            return error_msg

        # new name and ontology is not published or old name and ontology published with the same name
        if (len(PublishName.objects.filter(name=name)) == 0 and
            len(PublishName.objects.filter(user=user, ontology=ontology_rel_path_with_slash, repo=repo)) == 0) or (
                len(PublishName.objects.filter(user=user, ontology=ontology_rel_path_with_slash, repo=repo, name=name)) == 1):
            try:
                htaccess = get_file_content(target_repo=target_repo,
                                                      path=os.path.join('OnToology', ontology_rel_path,
                                                                        'documentation/.htaccess'), branch='gh-pages')
                dolog("publish> "+"gotten the htaccess successfully")
            except Exception as e:
                if '404' in str(e):
                    # return "documentation of the ontology has to be generated first."
                    error_msg= """documentation of the ontology has to be generated first. 
                    %s""" % os.path.join('OnToology', ontology_rel_path, 'documentation/.htaccess')
                    dolog("publish> "+error_msg)
                    return error_msg
                else:
                    error_msg = "github error: %s" % str(e)
                    dolog("publish> "+error_msg)
                    return error_msg
            dolog("publish> "+"htaccess content: ")
            dolog(htaccess)
            new_htaccess = htaccess_github_rewrite(target_repo=target_repo, htaccess_content=htaccess,
                                                   ontology_rel_path=ontology_rel_path)
            dolog("new htaccess: ")
            dolog(new_htaccess)
            update_file(target_repo=target_repo, path=os.path.join('OnToology', ontology_rel_path, 'documentation',
                                                                   '.htaccess'),
                        content=new_htaccess, branch='gh-pages', message='OnToology Publish')
            comm = 'mkdir "%s"' % os.path.join(publish_dir, name)
            dolog("publish> "+comm)
            call(comm, shell=True)
            f = open(os.path.join(publish_dir, name, '.htaccess'), 'w')
            f.write(new_htaccess)
            f.close()
            if len(PublishName.objects.filter(name=name)) == 0:
                p = PublishName(name=name, user=user, repo=repo, ontology=ontology_rel_path_with_slash)
                p.save()
            dolog("publish> "+"published correctly")
            return ""  # means it is published correctly
    else:
        error_msg =  """This repository is not register under your account. If you are the owner, you can add it to OnToology,
         Or you can fork it to your GitHub account and register the fork to OnToology"""
        dolog("publish> "+error_msg)
        return error_msg

########################################################################
########################################################################
# #####################  Auton configuration file  #####################
########################################################################
########################################################################


import ConfigParser


def get_confs_from_repo(target_repo):
    global g
    repo = g.get_repo(target_repo)
    sha = repo.get_commits()[0].sha
    files = repo.get_git_tree(sha=sha, recursive=True).tree
    conf_files = []
    for f in files:
        if 'OnToology.cfg' in f.path:
            conf_files.append(f)
    return repo, conf_files


def parse_online_repo_for_ontologies(target_repo):
    """ This is parse repositories for ontologies configuration files OnToology.cfg
    """
    global g
    if g is None:
        init_g()
    print "in parse online repo for ontologies"
    repo, conf_paths = get_confs_from_repo(target_repo)
    print "repo: %s, conf_paths: %s" % (str(repo), str(conf_paths))
    ontologies = []

    for cpath in conf_paths:
        p = quote(cpath.path)
        print "get file content: %s" % (str(cpath.path))
        print "after quote: %s" % p
        print "now get the decoded content"
        # file_content = repo.get_file_contents(cpath.path).decoded_content
        file_content = repo.get_file_contents(p).decoded_content
        print "file_content: "+str(file_content)
        buffile = StringIO.StringIO(file_content)
        print "will get the config"
        confs = get_auton_config(buffile)
        print "gotten confs: "+str(confs)
        o = {}
        # o['ontology'] = get_parent_path(cpath.path)[len(get_target_home()):]
        o['ontology'] = get_parent_path(p)[len(get_target_home()):]
        for c in confs:
            tool = c.replace('_enable', '')
            o[tool] = confs[c]
        ontologies.append(o)
    return ontologies


def get_auton_configuration(f=None, abs_folder=None):
    if abs_folder is not None:
        conf_file_abs = os.path.join(abs_folder, 'OnToology.cfg')
    elif f is not None:
        conf_file_abs = build_file_structure(
            'OnToology.cfg', [get_target_home(), f])
    else:
        conf_file_abs = build_file_structure(
            'OnToology.cfg', [get_target_home()])
    return get_auton_config(conf_file_abs, from_string=False)


def get_auton_config(conf_file_abs, from_string=True):
    dolog('auton config is called: ')
    ar2dtool_sec_name = 'ar2dtool'
    widoco_sec_name = 'widoco'
    oops_sec_name = 'oops'
    owl2jsonld_sec_name = 'owl2jsonld'
    ar2dtool_enable = True
    widoco_enable = True
    oops_enable = True
    owl2jsonld_enable = True
    config = ConfigParser.RawConfigParser()
    if from_string:
        opened_conf_files = config.readfp(conf_file_abs)
    else:
        opened_conf_files = config.read(conf_file_abs)
    if from_string or len(opened_conf_files) == 1:
        dolog('auton configuration file exists')
        try:
            ar2dtool_enable = config.getboolean(ar2dtool_sec_name, 'enable')
            dolog('got ar2dtool enable value: ' + str(ar2dtool_enable))
        except:
            dolog('ar2dtool enable value doesnot exist')
            pass
        try:
            widoco_enable = config.getboolean(widoco_sec_name, 'enable')
            dolog('got widoco enable value: ' + str(widoco_enable))
        except:
            dolog('widoco enable value doesnot exist')
            pass
        try:
            oops_enable = config.getboolean(oops_sec_name, 'enable')
            dolog('got oops enable value: ' + str(oops_enable))
        except:
            dolog('oops enable value doesnot exist')
        try:
            owl2jsonld_enable = config.getboolean(
                owl2jsonld_sec_name, 'enable')
            dolog('got owl2jsonld enable value: ' + str(owl2jsonld_enable))
        except:
            dolog('owl2jsonld enable value doesnot exist')
    else:
        dolog('auton configuration file does not exists')
        config.add_section(ar2dtool_sec_name)
        config.set(ar2dtool_sec_name, 'enable', ar2dtool_enable)
        config.add_section(widoco_sec_name)
        config.set(widoco_sec_name, 'enable', widoco_enable)
        config.add_section(oops_sec_name)
        config.set(oops_sec_name, 'enable', oops_enable)
        config.add_section(owl2jsonld_sec_name)
        config.set(owl2jsonld_sec_name, 'enable', owl2jsonld_enable)
        conff = conf_file_abs
        dolog('will create conf file: ' + conff)
        try:
            with open(conff, 'wb') as configfile:
                config.write(configfile)
        except Exception as e:
            dolog('expection: ')
            dolog(e)
    return {'ar2dtool_enable': ar2dtool_enable,
            'widoco_enable': widoco_enable,
            'oops_enable': oops_enable,
            'owl2jsonld_enable': owl2jsonld_enable}


def htaccess_github_rewrite(htaccess_content, target_repo, ontology_rel_path):
    """
    :param htaccess_content:
    :param target_repo: username/reponame
    :param ontology_rel_path: without leading or trailing /
    :return: htaccess with github rewrite as the domain
    """
    rewrites = [
        "RewriteRule ^$ index-en.html [R=303, L]",
        "RewriteRule ^$ ontology.n3 [R=303, L]",
        "RewriteRule ^$ ontology.xml [R=303, L]",
        "RewriteRule ^$ ontology.ttl [R=303, L]",
        "RewriteRule ^$ 406.html [R=406, L]",
        "RewriteRule ^$ ontology.json [R=303, L]",
        "RewriteRule ^$ ontology.nt [R=303, L]",

        "RewriteRule ^$ index-en.html [R=303,L]",
        "RewriteRule ^$ ontology.n3 [R=303,L]",
        "RewriteRule ^$ ontology.xml [R=303,L]",
        "RewriteRule ^$ ontology.ttl [R=303,L]",
        "RewriteRule ^$ 406.html [R=406,L]",
        "RewriteRule ^$ ontology.json [R=303,L]",
        "RewriteRule ^$ ontology.nt [R=303,L]"

    ]
    user_username = target_repo.split('/')[0]
    repo_name = target_repo.split('/')[1]
    base_url = "https://%s.github.io/%s/OnToology/%s/documentation/" % (user_username, repo_name, ontology_rel_path)
    new_htaccess = ""
    for line in htaccess_content.split('\n'):
        if line.strip() in rewrites:
            rewr_rule = line.split(' ')
            rewr_rule[2] = base_url + rewr_rule[2]
            new_htaccess += " ".join(rewr_rule) + "\n"
        else:
            if "RewriteRule" in line:
                print "NOTIN: " + line
            new_htaccess += line + "\n"
    return new_htaccess


##########################################################################
################################# generic helper functions ###############
##########################################################################


def delete_dir(target_directory):
    comm = "rm -Rf " + target_directory
    if not settings.test_conf['local']:
        comm += '  >> "' + log_file_dir + '" '
    print comm
    call(comm, shell=True)


def valid_ont_file(r):
    if r[-4:] in ontology_formats:
        return True
    return False


def get_target_home():
    return 'OnToology'


def get_abs_path(relative_path):
    return os.path.join(home, parent_folder, relative_path)


def get_level_up(relative_path):
    fi = get_file_from_path(relative_path)
    return relative_path[:-len(fi) - 1]


def get_parent_path(f):
    return '/'.join(f.split('/')[0:-1])


def get_file_from_path(f):
    return f.split('/')[-1]


# e.g. category_folder = docs, file_with_rel_dir = ahmad88me/org/ont.txt
def build_file_structure(file_with_rel_dir, category_folder='', abs_home=''):
    if abs_home == '':
        abs_dir = get_abs_path('')
    else:
        abs_dir = abs_home
    if type(category_folder) == type(""):  # if string
        if category_folder != '':
            abs_dir += category_folder + '/'
    elif type(category_folder) == type([]):  # if list
        for catfol in category_folder:
            abs_dir += catfol + '/'
    abs_dir_with_file = abs_dir + file_with_rel_dir
    abs_dir = get_parent_path(abs_dir_with_file)
    if not os.path.exists(abs_dir):
        os.makedirs(abs_dir)
    return abs_dir_with_file


##########################################################################
################################ Database functions ######################
##########################################################################

# if use_database:
#    from Auton.models import Repo
# import it for now
def change_status(target_repo, state):
    from models import Repo
    if not use_database:
        return ''
    try:
        repo = Repo.objects.get(url=target_repo)
        repo.last_used = datetime.today()
        repo.state = state
        repo.owner = parent_folder
        repo.save()
    except DoesNotExist:
        repo = Repo()
        repo.url = target_repo
        repo.state = state
        repo.owner = parent_folder
        repo.save()
    except Exception as e:
        print 'database_exception: ' + str(e)


# Before calling this function, the g must belong to the user not OnToologyUser
def get_proper_loggedin_scope(ouser, target_repo):
    if ouser.private:
        return True
    try:
        repo = g.get_repo(target_repo)
        if repo.private:
            ouser.private = True
            ouser.save()
            return True
        return False
    except:  # Since we do not have access, it should be private or invalid
        ouser.private = True
        ouser.save()
        return True


##########################################################################
#####################   Generate user log file  ##########################
##########################################################################

# just for the development phase


def generate_user_log(log_file_name):
    # comm = 'cp ' + home + 'log/' + log_file_name + '  ' + \
    comm = 'cp ' + os.path.join(home,'log',log_file_name) + '  ' + \
           os.path.join(settings.MEDIA_ROOT,
                     'logs')  # ' /home/ubuntu/auton/media/logs/'
    print comm
    sys.stdout.flush()
    if sys.stdout == default_stdout:
        print 'Warning: trying to close sys.stdout in generate_user_log function, I am disabling the closing for now'
    call(comm, shell=True)


# #########################################################################
# ###################################   main  #############################
# #########################################################################

#
# if __name__ == "__main__":
#     print "autoncore command: " + str(sys.argv)
#     if use_database:
#         connect('OnToology')
#     git_magic(sys.argv[1], sys.argv[2], sys.argv[3:])
#
#

def django_setup_script():
    #################################################################
    #           TO make this app compatible with Django             #
    #################################################################
    import os
    import sys

    proj_path = (os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir))
    # venv_python = os.path.join(proj_path, '..', '.venv', 'bin', 'python')
    # This is so Django knows where to find stuff.
    sys.path.append(os.path.join(proj_path, '..'))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "OnToology.settings")
    sys.path.append(proj_path)

    # This is so my local_settings.py gets loaded.
    os.chdir(proj_path)

    # This is so models get loaded.
    from django.core.wsgi import get_wsgi_application

    application = get_wsgi_application()

    #################################################################


if __name__ == "__main__":
    django_setup_script()
    from OnToology.models import *
    import argparse
    parser = argparse.ArgumentParser(description='')
    #parser.add_argument('task', type=str)

    parser.add_argument('--ontology_rel_path', default="")
    parser.add_argument('--publishname', default="")
    parser.add_argument('--publish', action='store_true', default=False)
    parser.add_argument('--previsual', action='store_true', default=False)
    parser.add_argument('--target_repo')
    parser.add_argument('--useremail')
    parser.add_argument('--magic', action='store_true', default=False)
    parser.add_argument('--changedfiles', action='append', nargs='*')
    # parser.add_argument('runid', type=int, metavar='Annotation_Run_ID', help='the id of the Annotation Run ')
    # parser.add_argument('--csvfiles', action='append', nargs='+', help='the list of csv files to be annotated')
    # parser.add_argument('--dotype', action='store_true', help='To conclude the type/class of the given csv file')
    args = parser.parse_args()
    if args.useremail and '@' in args.useremail:
        prepare_logger(args.useremail, ext='.core')
        if args.target_repo and len(args.target_repo.split('/')) == 2:
            if args.magic:
                print "changed files: "
                print args.changedfiles[0]
                git_magic(args.target_repo, args.useremail, args.changedfiles[0])
            if args.previsual:
                msg = previsual(useremail=args.useremail, target_repo=args.target_repo)
                if args.publish:
                    publish(name=args.publishname, target_repo=args.target_repo,
                            ontology_rel_path=args.ontology_rel_path, useremail=args.useremail)
            elif args.publish:
                pass
        else:
            print 'autoncore> invalid target repo: <%s>' % args.target_repo
    else:
        print 'autoncore> invalid user email: <%s>' % args.useremail


