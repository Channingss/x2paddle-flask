from flask import (
    Flask,
    request,
    render_template,
    send_from_directory,
    url_for,
    jsonify
)
from werkzeug.utils import secure_filename
import os
import  json

basedir = os.path.abspath(os.path.dirname(__file__))
save_base_dir = os.path.join(basedir, 'save_model/')

app = Flask(__name__)

from logging import Formatter, FileHandler
handler = FileHandler(os.path.join(basedir, 'log.txt'), encoding='utf8')
handler.setFormatter(
    Formatter("[%(asctime)s] %(levelname)-8s %(message)s", "%Y-%m-%d %H:%M:%S")
)
app.logger.addHandler(handler)

app.config['ALLOWED_EXTENSIONS'] = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif','onnx'])


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in app.config['ALLOWED_EXTENSIONS']

@app.context_processor
def override_url_for():
    return dict(url_for=dated_url_for)


def dated_url_for(endpoint, **values):
    if endpoint == 'js_static':
        filename = values.get('filename', None)
        if filename:
            file_path = os.path.join(app.root_path,
                                     'static/js', filename)
            values['q'] = int(os.stat(file_path).st_mtime)
    elif endpoint == 'css_static':
        filename = values.get('filename', None)
        if filename:
            file_path = os.path.join(app.root_path,
                                     'static/css', filename)
            values['q'] = int(os.stat(file_path).st_mtime)
    return url_for(endpoint, **values)


@app.route('/css/<path:filename>')
def css_static(filename):
    return send_from_directory(app.root_path + '/static/css/', filename)


@app.route('/js/<path:filename>')
def js_static(filename):
    return send_from_directory(app.root_path + '/static/js/', filename)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/uploadajax', methods=['POST'])
def upldfile():
    if request.method == 'POST':
        files = request.files['file']
        if files and allowed_file(files.filename):
            filename = secure_filename(files.filename)
            app.logger.info('FileName: ' + filename)
            updir = os.path.join(basedir, 'upload/')
            files.save(os.path.join(updir, filename))
            file_size = os.path.getsize(os.path.join(updir, filename))

            return jsonify(name=filename, size=file_size)

@app.route('/convert', methods=['POST'])
def convert():

    data = json.loads(request.get_data())

    model_full_name = data['name']
    updir = os.path.join(basedir, 'upload/')
    model_name = model_full_name.split('.')[0]

    save_dir =  os.path.join(save_base_dir,model_name)

    model_path = os.path.join(updir, model_full_name)

    if model_full_name.split('.')[-1] == 'onnx':
        result = os.system('x2paddle'+' --framework=onnx'+' --model='+model_path+' --save_dir='+save_dir)
        if result == 0 :
            zip_dir = os.path.join(save_dir, model_name + '.tar.gz')
            if os.path.exists(save_dir):
                os.system('tar cvzf ' + zip_dir + ' -C ' + save_base_dir + ' ' + model_name)
            return jsonify(name=model_name + '.tar.gz')

        else:
            return jsonify(name='convert failed')


@app.route('/download/<path:filename>', methods=['GET', 'POST'])
def download(filename):
    filename = filename[:-7]+'/'+ filename
    return send_from_directory(directory=save_base_dir, filename=filename)


if __name__ == '__main__':
    app.run(debug=True)
