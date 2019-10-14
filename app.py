from flask import (
    Flask,
    request,
    render_template,
    send_from_directory,
    jsonify,
    session
)
import os
import json
import logging
from src.es_models import EsModel
from src.database.connect import connect_es
from src.models import TensorflowModel, CaffeModel, OnnxModel
from src.tasks import ConvertConsumer, UploadConsumer, Producer

import queue
uploading_queue = queue.Queue(maxsize=2)
uploaded_queue = queue.Queue(maxsize=100)
converted_pool = dict()

base_dir = os.path.abspath(os.path.dirname(__file__))
upload_base_dir = os.path.join(base_dir, 'upload/')
convert_base_dir = os.path.join(base_dir, 'save_model/')

app = Flask(__name__)

def create_app(app):
    app.debug = True
    app.config['SECRET_KEY'] = os.urandom(24)
    handler = logging.FileHandler('x2paddle.log', encoding='UTF-8')
    handler.setLevel(logging.DEBUG)
    format = logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(format)
    app.logger.name = 'x2paddle'
    app.logger.addHandler(handler)
    return app

def create_model(request):
    if request.form.get('framework') == 'tensorflow':
        model = TensorflowModel(upload_base_dir, convert_base_dir, request)
    elif request.form.get('onnx') == 'tensorflow':
        model = OnnxModel(upload_base_dir, convert_base_dir, request)
    else:
        model = CaffeModel(upload_base_dir, convert_base_dir, request)
    return model

@app.route('/x2paddle', methods=['POST'])
def x2paddle():
    if request.method == 'POST':
        model = create_model(request)
        #
        if not model.check_filetype():
            return jsonify(status='failed', message='filetype error')

        # initial database object
        es_model = EsModel(meta={'id': model.id}, ip=request.remote_addr)
        es_model.save()
        session['id'] = model.id

        producer = Producer('Producer', uploading_queue, converted_pool, app)
        if producer.add_task(model):
            producer.start()
            print('uploading_queue size: ', uploading_queue.qsize())
            producer.join()
            return jsonify(producer.result)
        else:
            return jsonify(name=model.id, status='failed', message='waiting')

@app.route('/download/<path:filename>', methods=['GET', 'POST'])
def download(filename):
    filename = filename[:-7]+'/'+ filename
    return send_from_directory(directory=convert_base_dir, filename=filename)

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
    app = create_app(app)

    #create consumer
    uploadConsumer  = UploadConsumer('uploadConsumer', uploading_queue, uploaded_queue, app)
    uploadConsumer.start()

    convertConsumer  = ConvertConsumer('convertConsumer', uploaded_queue, converted_pool, app)
    convertConsumer.start()

    app.run(host='0.0.0.0')