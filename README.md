Clone the repository 
```
git clone https://github.com/gracedurham-28/limsproject.git
cd /Users/gracedurham/limsproject
```
Set up the virtual environment 
```
python3 -m venv limsenv
source limsenv/bin/activate
```
Dependencies 
```
pip install --upgrade pip
pip install -r requirements.txt
```
Set up other variables 
```
cp .env.example .env
```
Database 
```
pg_restore -U postgres -d lims_app ./db_dumps/app_db.dump 
```
If you are prompted for a password -> spots2828
Collect static files 
```
python manage.py collectstatic --noinput
```
Create a superuser (admin) 
```
python manage.py createsuperuser
```
follow instructions with making a superuser
Run
```
python manage.py runserver
```

