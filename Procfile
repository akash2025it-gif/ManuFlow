release: python manage.py migrate --noinput
web: gunicorn nit_system.wsgi:application --bind 0.0.0.0:$PORT
