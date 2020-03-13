from flask import Flask
from werkzeug.utils import redirect

app = Flask(__name__)

@app.route('/')
def root():
    return redirect('https://overtrack.gg/', code=301)

@app.route('/<path:path>')
def redirect_handler(path):
    return redirect('https://overtrack.gg/' + path, code=301)

