from datetime import datetime
from apscheduler.schedulers.background import BlockingScheduler
import random
import logging
import json
import os
from mastodon import Mastodon
with open('vars.json', 'r') as x:
	configJson = json.load(x)
logging.basicConfig()
logging.getLogger('apscheduler').setLevel(logging.DEBUG)
scheduler = BlockingScheduler()
#db = create_engine(os.environ['DATABASE_URL']) #heroku
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
app = Flask('test_app')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
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
				msg = "Reminder: %s starts %s @ %s" % (i.name,i.date,i.time)
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

if __name__ == '__main__':
	db.create_all()
	scheduler.add_job(notifyEngine, 'cron', minute=0)
	scheduler.start()