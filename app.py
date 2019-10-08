from flask import (
    Flask,
    request,
    render_template,
    send_from_directory,
    jsonify,
    session
)
import time
from werkzeug.utils import secure_filename
import os
import json
from subprocess import Popen, PIPE, STDOUT
import sys
import logging
from src.model import Model
from src.database.connect import connect_es

basedir = os.path.abspath(os.path.dirname(__file__))
save_base_dir = os.path.join(basedir, 'save_model/')

app = Flask(__name__)

def initial_app(app):
    handler = logging.FileHandler(os.path.join(basedir, 'x2paddle.log'), encoding='UTF-8')
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    app.logger.name = 'x2paddle'
    app.logger.addHandler(handler)
    app.config['debug'] = True
    app.config['SECRET_KEY'] = os.urandom(24)
    app.config['ALLOWED_EXTENSIONS'] = set(['onnx','pb','caffemodel','prototxt'])
    return app

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in app.config['ALLOWED_EXTENSIONS']

def x2paddle(cmd, model_name, save_dir):
    p = Popen(cmd, stdout=PIPE, stderr=STDOUT, shell=True, universal_newlines=True)
    cmd_result = ''
    for line in p.stdout.readlines():
        cmd_result += str(line).rstrip() + '<br/>\n'
        sys.stdout.flush()
    zip_dir = os.path.join(save_dir, model_name + '.tar.gz')

    es_model = Model.get(id=session['id'])
    es_model.update(log=cmd_result)

    if os.path.exists(os.path.join(save_dir, 'inference_model/__model__')):
        os.system('tar cvzf ' + zip_dir + ' -C ' + save_base_dir + ' ' + model_name)
        return jsonify(name=model_name + '.tar.gz', status='success', cmd_result=cmd_result)
    else:
        return jsonify(name='', status='failed', cmd_result=cmd_result)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    #获取用户ip地址
    start_time = time.time()
    id = str(start_time) + '_' + request.remote_addr
    es_model = Model(meta={'id':id},ip=request.remote_addr)
    es_model.save()
    session['id'] = id

    if request.method == 'POST':
        files = request.files['file']
        if files and allowed_file(files.filename):
            filename = secure_filename(files.filename)
            app.logger.info('FileName: ' + filename)
            updir = os.path.join(basedir, 'upload/')
            files.save(os.path.join(updir, filename))

            es_model = Model.get(id=session['id'])
            es_model.update(models_dir=os.path.join(updir, filename))

            file_size = os.path.getsize(os.path.join(updir, filename))
            return jsonify(name=filename, size=file_size)

@app.route('/convert', methods=['POST'])
def convert():
    '''
    {0:'tensorflow',1:'onnx',2:'caffe'}
    :return:
    '''
    try:
        id = session['id']
    except:
        return jsonify(name='', status='failed', cmd_result='')

    data = json.loads(request.get_data())
    updir = os.path.join(basedir, 'upload/')
    es_model = Model.get(id=id)
    es_model.update(email=data['email'])

    app.logger.warning('这是第一个info log')

    if data['framework'] == '0':
        #tensorflow
        model_full_name = data['tf_name']
        if model_full_name == '':
            return jsonify(status='failed')
        model_name = model_full_name.split('.')[0]
        save_dir = os.path.join(save_base_dir, model_name)
        model_path = os.path.join(updir, model_full_name)
        cmd = 'x2paddle' + ' --framework=tensorflow' + ' --model=' + model_path + ' --save_dir=' + save_dir
        return x2paddle(cmd, model_name, save_dir)
    elif data['framework'] == '1':
        #onnx
        model_full_name = data['onnx_name']
        if model_full_name == '':
            return jsonify(status='failed')
        model_name = model_full_name.split('.')[0]
        save_dir = os.path.join(save_base_dir, model_name)
        model_path = os.path.join(updir, model_full_name)
        cmd = 'x2paddle' + ' --framework=onnx' + ' --model=' + model_path + ' --save_dir=' + save_dir
        return x2paddle(cmd, model_name, save_dir)
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
        return x2paddle(cmd, model_name, save_dir)

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

    app = initial_app(app)
    app.run()