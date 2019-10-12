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
import logging
from src.models import Model
from src.database.connect import connect_es
import uuid
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

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in app.config['ALLOWED_EXTENSIONS']

def run_script(cmd, model_name, save_dir):
    p = Popen(cmd, stdout=PIPE, stderr=STDOUT, shell=True, universal_newlines=True)
    cmd_result = ''
    for line in p.stdout.readlines():
        cmd_result += str(line).rstrip() + '<br/>\n'
        sys.stdout.flush()
    zip_dir = os.path.join(save_dir, model_name + '.tar.gz')

    if os.path.exists(os.path.join(save_dir, 'inference_model/__model__')):
        os.system('tar cvzf ' + zip_dir + ' -C ' + save_base_dir + ' ' + model_name)
        app.logger.info('convert success')
        return jsonify(name=model_name + '.tar.gz', status='success', cmd_result=cmd_result)
    else:
        app.logger.info('convert failed')
        return jsonify(name='', status='failed', cmd_result=cmd_result)

def convert(file):
    data = file.form
    app.logger.info('start convert')
    framework = data.get('framework')
    model_name = file.filename.split('.')[0]
    save_dir = os.path.join(save_base_dir, file.id, model_name)
    if  framework== 'tensorflow':
        #tensorflow
        cmd = 'x2paddle' + ' --framework=tensorflow' + ' --model=' + file.file_dir + ' --save_dir=' + save_dir
        return run_script(cmd, model_name, save_dir)
    elif framework == 'onnx':
        #onnx
        model_full_name = file.filename
        if model_full_name == '':
            return jsonify(status='failed')
        model_name = model_full_name.split('.')[0]
        save_dir = os.path.join(save_base_dir, model_name)

        cmd = 'x2paddle' + ' --framework=onnx' + ' --model=' + file.file_dir  + ' --save_dir=' + save_dir
        return run_script(cmd, model_name, save_dir)

    elif framework == 'caffe':
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
        return run_script(cmd, model_name, save_dir)

import queue
import threading,time
threading.stack_size(65536)
uploading_queue = queue.Queue(maxsize=10)
uploaded_queue = queue.Queue(maxsize=100)
converted_queue = queue.Queue(maxsize=100)

class File():
    def __init__(self, request):
        self.id = uuid.uuid4().hex
        self.headers = request.headers
        self.file = request.files['file']
        self.form = request.form
        self.file_dir = None
        self.filename = self.file.filename

class Producer(threading.Thread):
    def __init__(self, name, wait_queue, finish_queue):
        self.id = None
        self.wait_queue = wait_queue
        self.finish_queue = finish_queue
        threading.Thread.__init__(self, name=name)
        self.daemon=True
        self.result = None

    def add_task(self,file):
        print("producing %s %s to the queue!" % (file.id, file.filename))
        self.id = file.id
        if self.wait_queue.full():
            return False
        self.wait_queue.put(file)
        print("%s finished!" % self.getName())
        return True

    def run(self):
        while True:
            id, result = self.finish_queue.get()
            if self.id == id:
                app.logger.info(self.id + ' producer get ack success')
                self.result = result
                break

class UploadConsumer(threading.Thread):
  def __init__(self, name, wait_queue, finish_queue):
    threading.Thread.__init__(self, name=name)
    self.wait_queue = wait_queue
    self.finish_queue = finish_queue
    self.daemon = True

  def run(self):
    while True:
        app.logger.info('start upload')

        file = self.wait_queue.get()
        print("%s is consuming. %s in the queue is consumed!" % (self.getName(),file.id ))
        filename = secure_filename(file.filename)
        app.logger.info('FileName: ' + filename)
        updir = os.path.join(basedir, 'upload/'+file.id)
        if not os.path.exists(updir):
            os.mkdir(updir)
        file_dir = os.path.join(updir, filename)
        file.file.save(file_dir)
        file.file_dir = file_dir
        self.finish_queue.put(file)
        app.logger.info('upload success')

class ConvertConsumer(threading.Thread):
  def __init__(self, name, wait_queue, finish_queue):
    threading.Thread.__init__(self, name=name)
    self.wait_queue = wait_queue
    self.finish_queue = finish_queue
    self.daemon = True
  def run(self):
    while True:
        with app.test_request_context():
            file = self.wait_queue.get()
            print(request.form)
            app.logger.info('start convert')
            print("%s is consuming. %s in the queue is consumed!" % (self.getName(), file.id))
            app.logger.info('file_dir: ' + file.file_dir)
            result = convert(file)
            self.finish_queue.put((file.id, result))
            app.logger.info('convert done')

@app.route('/x2paddle', methods=['POST'])
def x2paddle():
    #获取用户ip地址
    start_time = time.time()
    id = str(start_time) + '_' + request.remote_addr
    es_model = Model(meta={'id':id},ip=request.remote_addr)
    es_model.save()
    session['id'] = id
    if request.method == 'POST':
        file = request.files['file']
        if file and allowed_file(file.filename):
            print(file.filename)
            app.logger.info('file type is allow')
            producer = Producer('Producer', uploading_queue, converted_queue)
            print(id)
            file = File(request)
            if producer.add_task(file):
                producer.start()
                print(uploading_queue.qsize())
                producer.join()
                return producer.result
            else:
                return jsonify(name=file.filename, status='waited')

@app.route('/download/<path:filename>', methods=['GET', 'POST'])
def download(filename):
    filename = filename[:-7]+'/'+ filename
    return send_from_directory(directory=save_base_dir, filename=filename)

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
    app = initial_app(app)

    #create consumer
    uploadConsumer  = UploadConsumer('Consumer', uploading_queue, uploaded_queue)
    uploadConsumer.start()
    convertConsumer  = ConvertConsumer('Consumer', uploaded_queue, converted_queue)
    convertConsumer.start()

    app.run()