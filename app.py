from flask import (
    Flask,
    request,
    render_template,
    send_from_directory,
    jsonify,
    session
)
from werkzeug.utils import secure_filename
import os
import json
from subprocess import Popen, PIPE, STDOUT
import sys
from celery import Celery
import logging
from src.models import Model
from src.database.connect import connect_es
from src import celeryconfig

basedir = os.path.abspath(os.path.dirname(__file__))
save_base_dir = os.path.join(basedir, 'save_model/')

app = Flask(__name__)

def initial_app(app):
    app.debug = True
    app.config['SECRET_KEY'] = os.urandom(24)
    app.config['ALLOWED_EXTENSIONS'] = set(['onnx','pb','caffemodel','prototxt'])

    handler = logging.FileHandler('x2paddle.log', encoding='UTF-8')
    handler.setLevel(logging.DEBUG)
    format = logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(format)
    app.logger.name = 'x2paddle'
    app.logger.addHandler(handler)
    return app
app = initial_app(app)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in app.config['ALLOWED_EXTENSIONS']

def x2paddle_old(cmd, model_name, save_dir):
    p = Popen(cmd, stdout=PIPE, stderr=STDOUT, shell=True, universal_newlines=True)
    cmd_result = ''
    for line in p.stdout.readlines():
        cmd_result += str(line).rstrip() + '<br/>\n'
        sys.stdout.flush()
    zip_dir = os.path.join(save_dir, model_name + '.tar.gz')

    es_model = Model.get(id=session.get('id'))
    es_model.update(log=cmd_result)
    if os.path.exists(os.path.join(save_dir, 'inference_model/__model__')):
        os.system('tar cvzf ' + zip_dir + ' -C ' + save_base_dir + ' ' + model_name)
        app.logger.info('convert success')
        return jsonify(name=model_name + '.tar.gz', status='success', cmd_result=cmd_result)
    else:
        app.logger.info('convert failed')
        return jsonify(name='', status='failed', cmd_result=cmd_result)

celery = Celery('app', broker='amqp://localhost')
celery.config_from_object(celeryconfig)
TaskBase = celery.Task
class ContextTask(TaskBase):
        abstract = True
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

import queue
import random,threading,time

q = queue.Queue()

class Producer(threading.Thread):
    def __init__(self, name,queue,files):
        threading.Thread.__init__(self, name=name)
        self.data=queue
        print("%s is producing %s to the queue!" % (self.getName(), files.filename))
        self.data.put(files)
        time.sleep(random.randrange(10)/5)
        print("%s finished!" % self.getName())

class Consumer(threading.Thread):
  def __init__(self, name, queue):
    threading.Thread.__init__(self, name=name)
    self.data = queue
  def run(self):
    while True:
      files = self.data.get()
      print("%s is consuming. %s in the queue is consumed!" % (self.getName(), files.filename))
      filename = secure_filename(files.filename)
      app.logger.info('FileName: ' + filename)
      updir = os.path.join(basedir, 'upload/')
      files.save(os.path.join(updir, filename))
      app.logger.info('upload success')

@celery.task()
def x2paddle(cmd, model_name, save_dir):
    p = Popen(cmd, stdout=PIPE, stderr=STDOUT, shell=True, universal_newlines=True)
    cmd_result = ''
    for line in p.stdout.readlines():
        cmd_result += str(line).rstrip() + '<br/>\n'
        sys.stdout.flush()
    zip_dir = os.path.join(save_dir, model_name + '.tar.gz')

    if os.path.exists(os.path.join(save_dir, 'inference_model/__model__')):
        os.system('tar cvzf ' + zip_dir + ' -C ' + save_base_dir + ' ' + model_name)
        return {'name':model_name + '.tar.gz','status':'success','cmd_result':cmd_result}
    else:
        return  {'name':model_name + '.tar.gz','status':'failed','cmd_result':cmd_result}

@app.route('/')
def index():
    app.logger.info(request.remote_addr + ' login')
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    #获取用户ip地址
    app.logger.info('start upload')
    start_time = time.time()
    id = str(start_time) + '_' + request.remote_addr
    es_model = Model(meta={'id':id},ip=request.remote_addr)
    es_model.save()
    session['id'] = id
    if request.method == 'POST':
        files = request.files['file']
        if files and allowed_file(files.filename):
            app.logger.info('file type is allow')
            producer = Producer('Producer',q, files)
            producer.start()
            updir = os.path.join(basedir, 'upload/')
            es_model = Model.get(id=session.get('id'))
            es_model.update(models_dir=os.path.join(updir, files.filename))
            return jsonify(name=files.filename)

@app.route('/convert', methods=['POST'])
def convert():
    '''
    {0:'tensorflow',1:'onnx',2:'caffe'}
    :return:
    '''
    data = json.loads(request.get_data())

    id = session.get('id')
    updir = os.path.join(basedir, 'upload/')
    es_model = Model.get(id=id)
    es_model.update(email=data['email'])
    es_model.update(framework=data['framework'])
    app.logger.info('start convert')

    if data['framework'] == '0':
        #tensorflow
        model_full_name = data['tf_name']
        if model_full_name == '':
            return jsonify(status='failed')
        model_name = model_full_name.split('.')[0]
        save_dir = os.path.join(save_base_dir, model_name)
        model_path = os.path.join(updir, model_full_name)
        cmd = 'x2paddle' + ' --framework=tensorflow' + ' --model=' + model_path + ' --save_dir=' + save_dir
        res = x2paddle.delay(cmd, model_name, save_dir)
        while not res.ready():
            time.sleep(1)
        return jsonify(res.get(timeout=1))
    elif data['framework'] == '1':
        #onnx
        model_full_name = data['onnx_name']
        if model_full_name == '':
            return jsonify(status='failed')
        model_name = model_full_name.split('.')[0]
        save_dir = os.path.join(save_base_dir, model_name)
        model_path = os.path.join(updir, model_full_name)
        cmd = 'x2paddle' + ' --framework=onnx' + ' --model=' + model_path + ' --save_dir=' + save_dir

        res = x2paddle.delay(cmd, model_name, save_dir)
        while not res.ready():
            time.sleep(1)
        return jsonify(res.get(timeout=1))
    else:
        # caffe
        caffe_weight_name = data['caffe_weight_name']
        caffe_model_name = data['caffe_model_name']
        if caffe_weight_name == '' or caffe_model_name == '':
            return jsonify(status='failed')
        model_name = caffe_model_name.split('.')[0]
        save_dir = os.path.join(save_base_dir, model_name)

        weight_path = os.path.join(updir, caffe_weight_name)
        model_path = os.path.join(updir, caffe_model_name)
        cmd = 'x2paddle' + ' --framework=caffe' + ' --prototxt=' + model_path+ ' --weight=' + weight_path+ ' --save_dir=' + save_dir

        res = x2paddle.delay(cmd, model_name, save_dir)
        while not res.ready():
            time.sleep(1)
        return jsonify(res.get(timeout=1))

@app.route('/download/<path:filename>', methods=['GET', 'POST'])
def download(filename):
    filename = filename[:-7]+'/'+ filename
    return send_from_directory(directory=save_base_dir, filename=filename)

@app.route('/testdata/<path:filename>', methods=['GET', 'POST'])
def testdata(filename):
    updir = os.path.join(basedir, 'upload/')

    return send_from_directory(directory=updir, filename=filename)

if __name__ == '__main__':
    #connect es
    config_dir= 'src/database/config.json'
    try:
        with open(config_dir) as f:
            config = json.loads(f.read())
            f.close()
    except:
        assert 'fail to load config: '+ config_dir
    connect_es(config)

    #initial server
    # app = initial_app(app)

    consumer  = Consumer('Consumer', q)
    consumer.start()

    app.run()