from flask import url_for, render_template, Blueprint
from functools import wraps
from werkzeug.utils import redirect

from api.authentication import check_authentication
from api.blueprints.client import request

login = Blueprint('login', __name__)


@login.route('/login')
def login_endpoint():
    if 'next' in request.args:
        next_ = request.args['next']
    else:
        next_ = request.host_url
    login_url = 'https://api2.overtrack.gg/login/twitch?next=' + next_
    return render_template(
        'login.html',
        login_url=login_url
    )


def require_login(_endpoint=None):
    def wrap(endpoint):
        @wraps(endpoint)
        def check_login(*args, **kwargs):
            if check_authentication() is None:
                return endpoint(*args, **kwargs)
            else:
                return redirect(url_for('login.login_endpoint', next=request.url))

        return check_login

    if _endpoint is None:
        return wrap
    else:
        return wrap(_endpoint)
