from urllib import parse

from flask import Blueprint, Request, render_template, request, Response, make_response, url_for
from werkzeug.utils import redirect

from overtrack_web.lib.authentication import check_authentication

request: Request = request
login_blueprint = Blueprint('login', __name__)


@login_blueprint.route('/login')
def login():
    if 'next' in request.args:
        next_ = request.args['next']
        if check_authentication() is None and next_.startswith(request.url_root):
            return redirect(next_)
    else:
        next_ = request.host_url

    return render_template(
        'login.html',
        login_twitch='https://api2.overtrack.gg/login/twitch?next=' + next_,
        login_bnet='https://api2.overtrack.gg/login/battlenet?next=' + next_
    )

@login_blueprint.route('/logout')
def logout():
    response: Response = make_response(redirect(url_for('root')))
    domain = parse.urlsplit(request.url).hostname

    # remove non-domain specific cookie
    response.set_cookie('session', '', expires=0)

    # remove domain specific cookie for this domain
    if domain not in ['localhost', '127.0.0.1']:
        response.set_cookie('session', '', expires=0, domain=domain)

    if any(c not in '.0123456789' for c in domain):
        # not an IP address - remove cookie for subdomains of this domain
        response.set_cookie('session', '', expires=0, domain='.' + domain)
        if domain.count('.') >= 2:
            # we are on a subdomain - remove cookie for this and all other subdomains
            response.set_cookie('session', '', expires=0, domain='.' + domain.split('.', 1)[-1])

    return response
