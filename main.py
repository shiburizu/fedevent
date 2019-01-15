from flask import Flask, render_template, request, flash, redirect, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import random
import logging
import json
import os
with open('vars.json', 'r') as x:
    configJson = json.load(x)
logging.basicConfig()
logging.getLogger('apscheduler').setLevel(logging.DEBUG)
scheduler = BackgroundScheduler()
scheduler.start()
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL'] #heroku 'sqlite:///fedevent.db'
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/'
db = SQLAlchemy(app)

from mastodon import Mastodon

api = Mastodon(access_token=configJson["mast_access"], 
				client_id=configJson["mast_client_id"], 
				client_secret=configJson["mast_client_secret"], 
				api_base_url=configJson["mast_api_url"])

class events(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(80))
	desc = db.Column(db.Text)
	date = db.Column(db.String(80))
	time = db.Column(db.String(80))
	cost = db.Column(db.String(80))
	gps = db.Column(db.String(80))
	interval = db.Column(db.Integer) #how we know how many note intervals are left
	status = db.Column(db.Integer)
	subscribers = db.Column(db.Text)
	subcount = db.Column(db.Integer)
	creator = db.Column(db.String(80))

class keys(db.Model): #2FA to bypass storing accounts, works for APub instances that allow DMs like Mastodon and Pleroma
	id = db.Column(db.Integer, primary_key=True)
	user = db.Column(db.String(80))
	key = db.Column(db.String(80))

def notifyEngine():
	eventlist = db.session.query(events).all()
	for i in eventlist:
		if i.subcount != 0 and i.interval != 0:
			msg = ''
			diff = datetime.strptime(i.date, "%Y-%m-%d") - datetime.now()
			if diff.days+1 <= 7 and i.interval == 3:
				msg = "Reminder: %s is coming up in %s days." % (i.name,diff.days+1)
				i.interval = 2
			if diff.days+1 <= 3 and i.interval == 2:
				msg = "Reminder: %s is coming up in %s days." % (i.name,diff.days+1)
				i.interval = 1
			if diff.days == 0 and i.interval == 1:
				msg = "Reminder: %s starts at %s." % (i.name,i.time)
				i.interval = 0
			db.session.commit()
			if msg:
				for n in i.subscribers.split(","):
					api.status_post("@%s " % n + msg, visibility='direct')
		if i.interval == 0:
			diff = datetime.strptime(i.date, "%Y-%m-%d") - datetime.now()
			if diff.seconds <= 0:
				i.status = 0
				db.session.commit() #expired

@app.route('/generateKey',methods=['GET'])
def generateKey():
	if db.session.query(keys).filter_by(user=request.args.get('user')).first():
		api.status_post("@%s : Your 2FA Key is %s" % (request.args.get('user'),db.session.query(keys).filter_by(user=request.args.get('user')).first().key) , visibility='direct')
	else: #TODO make sure every user has unique 2FA key
		if request.args.get('user').strip() != "":
			key = ""
			for i in range(1,5):
				key += str(random.randint(1,9))
			newKey = keys(
				user = request.args.get('user'),
				key = key
			)
			db.session.add(newKey)
			db.session.commit()
			api.status_post("@%s : Your 2FA Key is %s" % (request.args.get('user'),key) , visibility='direct')
	return ('', 204)

@app.route('/showEvent/<id>')
def showEvent(id):
	event = db.session.query(events).filter_by(id=id).first()
	return render_template('showEvent.html',details=event)

@app.route('/eventForm')
def eventForm():
	return render_template('eventForm.html',date=datetime.now().strftime("%Y-%m-%d"))

@app.route('/createEvent', methods=['POST'])
def createEvent():
	if db.session.query(keys).filter_by(user=request.form.get('user'),key=request.form.get('key')).first() != None:
		n = 0 #evaluate which interval this is supposed to start at for best accuracy
		diff = datetime.strptime(request.form.get('date'), "%Y-%m-%d") - datetime.now()
		if diff.days+1 >= 7:
			n = 3
		if diff.days+1 >= 3 and diff.days+1 < 7:
			n = 2
		if diff.days == 1:
			n = 1
		t = datetime.strptime(request.form.get('time'), "%H:%M")
		dt = datetime.strftime(t,"%I:%M %p")
		newevent = events(
			name = request.form.get('name'),
			desc = request.form.get('description'),
			date = request.form.get('date'),
			time = dt,
			cost = request.form.get('cost'),
			gps = request.form.get('location').replace("L","l",1),
			interval = n,
			status = 1,
			subscribers = "",
			subcount = 0,
			creator = request.form.get('user')
		)
		db.session.add(newevent)
		db.session.commit()
		return redirect('/')
	else:
		flash("Incorrect 2FA code.")
		return redirect('/')

@app.route('/subscribeEvent/<eventid>', methods=['POST'])
def subscribeEvent(eventid):
	if db.session.query(keys).filter_by(user=request.form.get('user'),key=request.form.get('key')).first() != None:	
		event = db.session.query(events).filter_by(id=eventid).first()
		if request.form.get('user') in event.subscribers:
			flash('Already subscribed.')
			return redirect('/')
		if event.subscribers == '':
			event.subscribers += request.form.get('user')
			event.subcount += 1
			db.session.commit()
			return redirect('/')
		else:
			event.subscribers += "," + request.form.get('user')
			event.subcount += 1
			db.session.commit()
			return redirect('/')
	else:
		flash("Incorrect 2FA code.")
		return redirect('/')

@app.route('/unsubscribeEvent/<eventid>', methods=['POST'])
def unsubscribeEvent(eventid):
	if db.session.query(keys).filter_by(user=request.form.get('user'),key=request.form.get('key')).first() != None:	
		event = db.session.query(events).filter_by(id=eventid).first()
		if "," + request.form.get('user') in event.subscribers:
				event.subscribers = event.subscribers.replace("," + request.form.get('user'),"")
				event.subcount -= 1
				db.session.commit()
				flash("Unsubscribed successfully.")
				return redirect("/")
		else:
			if event.subscribers[:len(request.form.get('user'))+1] == request.form.get('user'):
				event.subscribers = event.subscribers.replace(request.form.get('user'),"",1)#if we got here it means it was the very first occurence, only needs to be done once.
				event.subcount -= 1
				db.session.commit()
				flash("Unsubscribed successfully.")
				return redirect("/")
			else:
				flash("User was not subscribed to this event.")
				return redirect("/")
	else:
		flash("Incorrect 2FA code.")
		return redirect('/')
	
@app.route('/deleteEvent/<eventid>', methods=['POST'])
def deleteEvent(eventid):
	if db.session.query(keys).filter_by(user=request.form.get('user'),key=request.form.get('key')).first() != None:	
		event = db.session.query(events).filter_by(id=eventid).first()
		if event.creator == request.form.get('user'):
			db.session.delete(event)
			db.session.commit()
			flash("Event deleted.")
			return redirect("/")
		else:
			flash("This can only be done by the event creator.")
			return redirect("/")
	else:
		flash("Incorrect 2FA code.")
		return redirect('/')

@app.route('/about')
def about():
	return render_template('about.html')

@app.route('/')
def index():
	list = db.session.query(events).all()
	return render_template('index.html',list=list)

if __name__ == '__main__':
	db.create_all()
	#scheduler.add_job(notifyEngine, 'interval', minutes=1)
	port = int(os.environ.get('PORT', 5000))
	app.run(host='0.0.0.0', port=port, debug=False)