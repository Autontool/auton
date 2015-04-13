from django.shortcuts import render, render_to_response, redirect
from django.http import HttpResponseRedirect
from mongoengine.django.auth import User
from django.contrib.auth import authenticate, login, logout
from django import forms
from django.template import RequestContext
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.urlresolvers import reverse
from django.views.decorators.csrf import csrf_exempt

import string
import random
from datetime import datetime
from autoncore import git_magic, add_webhook, webhook_access, update_g, add_collaborator, get_auton_configuration
from models import *
import requests
import json

import multiprocessing

import subprocess




host = 'http://54.172.63.231'
client_id = 'bbfc39dd5b6065bbe53b'
client_secret = '60014ba718601441f542213855607810573c391e'



def home(request):
    if 'target_repo' in request.GET:
        target_repo = request.GET['target_repo']
        webhook_access_url, state = webhook_access(client_id,host+'/get_access_token')
        request.session['target_repo'] = target_repo
        request.session['state'] = state
        return  HttpResponseRedirect(webhook_access_url)
    repos = []
    for orir in Repo.objects.all():
        r = {}
        for ke in orir:
            r[ke]  = orir[ke]
        tools = r['monitoring'].split(",")
        monit=""
        for t in tools:
            
            keyval = t.split("=")
            if len(keyval) != 2:
                #monit = r.monitoring
                break
            if keyval[1]:
                keyval[1]='Yes'
            else:
                keyval[1]='No'
            r[keyval[0].strip()]=keyval[1]
            monit+="=".join(keyval) +","
        r['monitoring'] = monit
        repos.append(r)
    for i in repos:
        for k in i:
            print k+""+str(i[k])
        print "------------------------"
    return render_to_response('home.html',{'repos': repos},context_instance=RequestContext(request))

        



def grant_update(request):
    return render_to_response('msg.html',{'msg': 'Magic is done'},context_instance=RequestContext(request))



  
def get_access_token(request):
    if request.GET['state'] != request.session['state']:
        return render_to_response('msg.html',{'msg':'Error, ; not an ethical attempt' },context_instance=RequestContext(request))
    data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'code': request.GET['code'],
        'redirect_uri': host+'/add_hook'
    }
    res = requests.post('https://github.com/login/oauth/access_token',data=data)
    atts = res.text.split('&')
    d={}
    for att in atts:
        keyv = att.split('=')
        d[keyv[0]] = keyv[1]
    access_token = d['access_token']
    request.session['access_token'] = access_token
    update_g(access_token)
    print 'access_token: '+access_token
    rpy_wh = add_webhook(request.session['target_repo'], host+"/add_hook")
    rpy_coll = add_collaborator(request.session['target_repo'], 'AutonUser')
    error_msg = ""
    if rpy_wh['status'] == False:
        error_msg+=str(rpy_wh['error'])
        print 'error adding webhook: '+error_msg
    if rpy_coll['status'] == False:
        error_msg+=str(rpy_coll['error'])
        print 'error adding collaborator: '+rpy_coll['error']
    else:
        print 'adding collaborator: '+rpy_coll['msg']
    if error_msg != "":
        return render_to_response('msg.html',{'msg':error_msg },context_instance=RequestContext(request))
    return render_to_response('msg.html',{'msg':'webhook attached and user added as collaborator' },context_instance=RequestContext(request))
    

      

@csrf_exempt
def add_hook_test(request):
    # cloning_repo should look like 'git@github.com:AutonUser/target.git'
    cloning_repo = 'git://github.com/ahmad88me/target.git'#request.POST['cloning_repo']
    tar = cloning_repo.split('/')[-2]
    cloning_repo = cloning_repo.replace(tar,'AutonUser')
    cloning_repo = cloning_repo.replace('git://github.com/','git@github.com:')
    target_repo = 'ahmad88me/target'#request.POST['target_repo']
    user = 'test_user'#request.POST['username']
    changed_files = ['a.txt']
    r = git_magic(target_repo, user, cloning_repo, changed_files)
    s='add_hook_test'
    #request.session['updated_files'] = j['head_commit']['modified']
    return render_to_response('msg.html',{'msg': ''+s+'<>'+r},context_instance=RequestContext(request))



@csrf_exempt
def add_hook(request):
    try:
        s = str(request.POST['payload'])
        j = json.loads(s)
        s = j['repository']['url']+'updated files: '+str(j['head_commit']['modified'])
        cloning_repo = j['repository']['git_url']
        target_repo = j['repository']['full_name']
        user = j['repository']['owner']['email']
        changed_files = j['head_commit']['modified']
        #changed_files+= j['head_commit']['removed']
        changed_files+= j['head_commit']['added']
        if 'Merge pull request' in  j['head_commit']['message'] :
            return render_to_response('msg.html',{'msg': 'This indicate that this merge request will be ignored'},context_instance=RequestContext(request))
    except:
        try:
            repo = Repo.objects.get(url=target_repo)
            repo.last_used = datetime.today()
            repo.monitoring = s
            repo.save()
        except DoesNotExist:
            repo = Repo()
            repo.url=target_repo
            repo.monitoring = s
            repo.save()
        except Exception as e:
            print 'database_exception: '+str(e)
        return render_to_response('msg.html',{'msg': 'This request should be a webhook ping'},context_instance=RequestContext(request))
    print '##################################################'
    print 'changed_files: '+str(changed_files)
    # cloning_repo should look like 'git@github.com:AutonUser/target.git'
    tar = cloning_repo.split('/')[-2]
    cloning_repo = cloning_repo.replace(tar,'AutonUser')
    cloning_repo = cloning_repo.replace('git://github.com/','git@github.com:')
#     r = git_magic(target_repo, user, cloning_repo, changed_files)
    #if r['status']==True:
    mont = get_auton_configuration(user)
    s = ""
    for i in mont:
        s+=i+"="+str(mont[i])+", "
    
#     try:
#         repo = Repo.objects.get(url=target_repo)
#         repo.last_used = datetime.today()
#         repo.monitoring = s
#         repo.save()
#     except DoesNotExist:
#         repo = Repo()
#         repo.url=target_repo
#         repo.monitoring = s
#         repo.save()
#     except Exception as e:
#         print 'database_exception: '+str(e)
            
            
            
            #r['database_exception']=str(e)
    #multiprocessing.Process(target=git_magic,args=(target_repo, user, cloning_repo, changed_files)).start()
    #git_magic(target_repo, user, cloning_repo, changed_files)
    comm = "python /home/ubuntu/auton/Auton/autoncore.py "
    comm+=' "'+target_repo+'" "'+user+'" "'+cloning_repo+'" '
    for c in changed_files:
        comm+='"'+c+'" '
    print 'running autoncore code as: '+comm
    subprocess.Popen(comm,shell=True)
    #call(comm,shell=True)
    r=""
    #r = str(r)
    #request.session['updated_files'] = j['head_commit']['modified']
    return render_to_response('msg.html',{'msg': ''+s+'<>'+r},context_instance=RequestContext(request))









