echo "in compose run"
pwd
cat OnToology/localwsgi.py
echo "MIGRATION SCRIPT"
sh scripts/migrate.sh
echo " STARTING TEST FROM DOCKER TESTS SCRIPT"
.venv/bin/python manage.py test OnToology