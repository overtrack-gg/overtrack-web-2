from flask import Blueprint, render_template, request

login_blueprint = Blueprint('login', __name__)


@login_blueprint.route('/login')
def login():
    if 'next' in request.args:
        next_ = request.args['next']
    else:
        next_ = request.host_url
    return render_template(
        'login.html',
        login_twitch='https://api2.overtrack.gg/login/twitch?next=' + next_,
        login_bnet='https://api2.overtrack.gg/login/battlenet?next=' + next_
    )
