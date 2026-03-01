Clone the repository 
```
git clone https://github.com/gracedurham-28/limsproject.git
cd limsproject/appsett
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
  Copy example .env file 
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
Run
```
python manage.py runserver
```
OR to start the server, run manage_server.py to collect static then run server_gui.py. There will be a popup window to allow for use of the start/stop server buttons. 
Then go to the server: http://127.0.0.1:8000/admin
