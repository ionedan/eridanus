from google.appengine.api import users
from flask import render_template, \
    make_response, session
from datetime import datetime
from zipfile import ZipFile
from StringIO import StringIO
from models import Run, Weight
from repository import RunRepository, WeightRepository

import csv


ERIDANUS_TIME_FORMAT = '%I:%M %p'
ERIDANUS_DATE_FORMAT = '%d %b %Y'


class AuthController(object):
    def __init__(self):
        self.nickname = None
        self.logout_url = None
        self._fetch_user_data()

    def _fetch_user_data(self):
        if not session.has_key('nickname'):
            user = users.get_current_user()
            if user:
                session['nickname'] = user.nickname()
                _auth_domain = None
                session['logout_url'] = users.create_logout_url('/', _auth_domain)

    @property
    def is_authenticated(self):
        return session['nickname'] is not None

    @property
    def is_authorized(self):
        return self.is_authenticated 

    def render_view(self, url, dict):
        if not self.is_authorized:
            return 'You''re not authorized to use this website. <a href="{}">Log out</a>'.format(session['logout_url'])
        render_template(url, vm=dict)

    def render_form_template(self, url, form=None):
        if not self.is_authorized:
            return 'You''re not authorized to use this website. <a href="{}">Log out</a>'.format(session['logout_url'])
        return render_template(url, form=form)


class AdminController(AuthController):

    def __init__(self):
        super(AdminController, self).__init__()
        
    def export(self):
        run_csv=self._build_run_csv()
        weight_csv=self._build_weight_csv()
        in_memory = StringIO()
        zip = ZipFile(in_memory, "a")
        zip.writestr("run.csv", run_csv)
        zip.writestr("weight.csv", weight_csv)
        # fix for Linux zip files read in Windows
        for file in zip.filelist:
            file.create_system = 0    
        zip.close()
        in_memory.seek(0) 
        response = make_response(in_memory.read())
        response.headers["Content-Disposition"] = "attachment; filename=eridanus_data.zip"
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Content-Type'] = 'application/zip'
        #in_memory.seek(0)    
        #response.write(in_memory.read()) #?
        return response


    def _build_run_csv(self):
        items = self._fetch_all_run()
        stream = StringIO()
        fieldnames = ['usernickname', 'activity_date', 'activity_time', 'time', 'distance', 'speed', 'calories', 'notes', 'creation_datetime']
        csvwriter = csv.DictWriter(stream, fieldnames=fieldnames, dialect='excel')
        csvwriter.writeheader()
        for item in items:
            csvwriter.writerow({
                'usernickname': item.usernickname, 
                'activity_date': self._get_activity_date(item),
                'activity_time': self._get_activity_time(item),
                'duration': self._get_duration(item),
                'distance': item.distance,
                'speed': item.speed,
                'calories': item.calories,
                'notes': item.notes,
                'creation_datetime': item.creation_datetime
                })
        return stream.getvalue()

    def _build_weight_csv(self):
        items = self._fetch_all_weights()
        
        stream = StringIO()
        csvwriter = csv.writer(stream, dialect='excel')
        fieldnames = ['usernickname', 'weight', 'creation_datetime']
        csvwriter = csv.DictWriter(stream, fieldnames=fieldnames, dialect='excel')
        csvwriter.writeheader()
        for item in items:
            csvwriter.writerow({
                'usernickname': item.usernickname, 
                'weight': item.weight,
                'creation_datetime': item.creation_datetime
                })
        return stream.getvalue()

    def _build_csv(self, items):
        pass

    def _fetch_all_run(self):
        repo = RunRepository()
        return repo.fetch_all()

    def _fetch_all_weights(self):
        repo = WeightRepository()
        return repo.fetch_all()

    def _get_activity_date(self, model):
        if model.activity_date:
            return model.activity_date
        else:
            return model.date

    def _get_activity_time(self, model):
        if model.activity_time:
            return model.activity_time
        else:
            return datetime.strptime(u'20:30','%H:%M').time()

    def _get_duration(self, model):
        if model.duration:
            return model.duration
        else:
            return model.time

    def import_data(self):
        pass

    def index(self):
        return render_template('admin/home.html')


class HomeController(AuthController):
    ''' statistics class 
    Is this a model class a controller or a controller class? Not very clear
    TODO: to be reviewed
    '''
    # pylint: disable=too-many-instance-attributes
    # TODO maybe I should review this class as it could have to many responsabilities
    # a run statistic class can be created a weight stats and so on
    # https://softwareengineering.stackexchange.com/questions/302549/how-does-having-too-many-instance-variables-lead-to-duplicate-code
        
    def __init__(self):
        super(HomeController, self).__init__()

        self.date_last_run = None
        self.max_calories = 0
        self.max_distance = 0
        self.max_speed = 0.0
        self.max_time = 0
        self.min_weight = 0
        self.total_calories = 0
        self.total_distance = 0
        self.total_time = 0
        self.avg_calories = 0
        self.avg_speed = 0.0
        self.avg_distance = 0.0
        self.avg_time = 0
        self.count = 0
        self.days_past_from_last_run = 0
        self.weight_trend = 0
        self.last_weight = 0
        self.weight_growth_rate_20 = 0
        self.avg_weight_20 = 0

    def _load_data(self):
        run_items = Run.query().fetch()

        self.count = len(run_items)
        if self.count > 0:
            total_speed = 0
            for item in run_items:
                activity_date = self._get_activity_date(item)
                duration = self._get_duration(item)
                if item.calories:
                    self.total_calories += item.calories
                    if item.calories > self.max_calories:
                        self.max_calories = item.calories
                self.total_distance += item.distance
                self.total_time += duration
                if item.distance > self.max_distance:
                    self.max_distance = item.distance
                if duration > self.max_time:
                    self.max_time = duration
                speed = item.speed
                if item.speed is None:
                    speed = item.distance / (duration / 60.0)
                total_speed += speed
                if speed > self.max_speed:
                    self.max_speed = speed
                if self.date_last_run is None or activity_date > self.date_last_run:
                    self.date_last_run = activity_date
                    self.days_past_from_last_run = self._get_days_past_from_last_run(self.date_last_run)
            if self.count > 0:
                self.avg_calories = self.total_calories / self.count
                self.avg_distance = float(self.total_distance) / float(self.count)
                self.avg_time = self.total_time / self.count
                self.avg_speed = total_speed / self.count
        # computing weight stats
        weight_items = Weight.query().order(-Weight.creation_datetime).fetch()
        if len(weight_items) > 0:
            self.last_weight = weight_items[0].weight
        recno_weight = len(weight_items)
        if recno_weight > 0:
            total_weight_last20 = 0.0
            count = 0
            for item in weight_items:
                if count < 20:
                    count += 1
                    total_weight_last20 += item.weight
                    continue
                break
            self.avg_weight_20 = total_weight_last20 / float(count)
            self.weight_growth_rate_20 = (
                1.0 - self.avg_weight_20 / self.last_weight) * 100.0
            if self.weight_growth_rate_20 < 0:
                self.weight_trend = '{:0.2f}% AVG20: {:0.1f} kg'.format(
                    self.weight_growth_rate_20, self.avg_weight_20)
            elif self.weight_growth_rate_20 > 0:
                self.weight_trend = '{:0.1f}% AVG20: {:0.1f} kg'.format(
                    self.weight_growth_rate_20, self.avg_weight_20)

    def _get_activity_date(self, model):
        if model.activity_date:
            return model.activity_date
        else:
            return model.date

    def _get_duration(self, model):
        if model.duration:
            return model.duration
        else:
            return model.time
    
    def _get_days_past_from_last_run(self, date_last_run):
        if date_last_run:
            diff = abs(datetime.now().date() - date_last_run)
            return diff.days
        return None

    def get_day_from_last_run_class(self):
        if self.days_past_from_last_run is None:
            return ''
        diff = self.days_past_from_last_run
        if diff < 3:
            return 'label-success'
        elif diff < 4:
            return 'label-warning'
        else:
            return 'label-danger'

    def index(self):
        self._load_data()
        return render_template('index.html', stats=self)