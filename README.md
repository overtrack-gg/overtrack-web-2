[![All Contributors](https://img.shields.io/badge/all_contributors-4-orange.svg?style=flat-square)](#contributors-)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](http://makeapullrequest.com)
[![Discord chat](https://img.shields.io/badge/chat-on_discord-008080.svg?style=flat-square&logo=discord)](https://discord.gg/JywstAB)

## Running Locally

### Dependencies
Dependencies are installed through [poetry](https://python-poetry.org/docs/#installation)
```bash
poetry install
```

Poetry uses `pyproject.toml` to specify requirements as per [pep 518](https://www.python.org/dev/peps/pep-0518/).
Requirements can be added with `poetry add <package>`, and the lock file can be updated with `poetry update`.

Note overtrack-web depends on [overtrack-models](https://gitlab.com/OverTrack/overtrack-models) 
(which is specified as a git dependency in pyproject.toml and should be installed automatically by poetry).

#### Commands
Use
```bash
cd overtrack_web
FLASK_APP=overtrack_web.local_flask_app FLASK_DEBUG=1 poetry run flask run 
```
if you are using poetry's automatic virtual environments or 
```bash
cd overtrack_web
FLASK_APP=overtrack_web.local_flask_app FLASK_DEBUG=1 flask run 
```
if you are managing your virtual environment yourself.

The port can be changed by setting `FLASK_RUN_PORT`.

### Local development mode notes
`local_flask_app.py` exposes a flask app that matches much of the live version and mocks access to games so that games are
 populated from the OverTrack API using public share links.
The source of the "mock" games can be changed by changing the environment variables `APEX_GAMES_SOURCE` and `OVERWATCH_GAMES_SOURCE`.
It would also be possible to modify the initial fetching of games to use a session cookie instead, which would allow you use your own games.
Keep in mind that games are cached in `requests_cache.sqlite` for much faster local page loads and app init. Delete this and reload to redownload the games 
lists and update games.

The local flask app does not run with the discord bot or subscribe pages active, and mocks login so that you are always logged in as a dummy user.

`overtrack_web/flask_app.py` is the flask app used for hosting the actual site, and requires access to overtrack's AWS resources to run.

### Using an IDE

Once packages are installed with poetry, you can set your IDE to use the poetry created virtualenvironment.
Use `poetry show -v` to get the virtualenvironment path.

Use the environment variables from [commands](#commands) (i.e. FLASK_APP and FLASK_DEBUG) and if required set the interpreter to be the `python` executable in the virtualenvironment 
created by poetry. In PyCharm, set the module to `flask` with the parameters `run`, in other IDE's you may just need to set the command to `flask run`.

## Structure

### Python

All python code is contained within `overtrack_web/overtrack_web`.

Views should be contained within the `views` package, generally exposing a blueprint that can be registered in `flask_app.py`/`local_flask_app.py`. 

Some complex views are surrounded by try/catch statements inside the flask_app for import and registering.
This allows the application to function even if that view breaks on import (e.g. if it's initialisation requires fetching an external resource).  

### Templates

Templates can be found in `overtrack_web/templates`.

Templates are written in [jinja2](https://jinja.palletsprojects.com/en/2.11.x/)'s templating language (or pure html).

### Static content

Static content can be found in `overtrack_web/static`.

On live static content is uploaded to a CDN and `url_for` is modified to return the CDN urls for static assets.

#### SCSS

SCSS is compiled from `overtrack_web/static/scss` as part of the flask app while running locally, and placed in `static/css`.
Do not edit `static/css` manually.

On live, SCSS is compiled when building and `static/css` is uploaded to the CDN.

#### Javascript

Javascript sources can be found in `overtrack_web/static/js`.
Javascript libraries should be placed in `overtrack_web/static/js/lib`.

When running locally using `local_flask_app.py`, urls requesting `*.min.js` will be modified to `*.js`, so if `.min.js` versions are added, make sure to 
include the corresponding `.js`.

#### Images

Images are contained in `overtrack_web/static/images`.

## Contributors ✨

Thanks goes to these wonderful people ([emoji key](https://allcontributors.org/docs/en/emoji-key)):

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tr>
    <td align="center"><a href="https://overtrack.gg"><img src="https://avatars0.githubusercontent.com/u/2515062?v=4" width="100px;" alt=""/><br /><sub><b>Simon Pinfold</b></sub></a><br /><a href="https://github.com/overtrack-gg/overtrack-web-2/commits?author=synap5e" title="Code">💻</a> <a href="#design-synap5e" title="Design">🎨</a></td>
    <td align="center"><a href="https://github.com/jess-sio"><img src="https://avatars3.githubusercontent.com/u/3945148?v=4" width="100px;" alt=""/><br /><sub><b>Jessica Mortimer</b></sub></a><br /><a href="https://github.com/overtrack-gg/overtrack-web-2/commits?author=jess-sio" title="Code">💻</a> <a href="#design-jess-sio" title="Design">🎨</a></td>
    <td align="center"><a href="https://github.com/JWSenteney"><img src="https://avatars0.githubusercontent.com/u/1554771?v=4" width="100px;" alt=""/><br /><sub><b>JWSenteney</b></sub></a><br /><a href="#ideas-JWSenteney" title="Ideas, Planning, & Feedback">🤔</a></td>
    <td align="center"><a href="https://sdcore.github.io"><img src="https://avatars2.githubusercontent.com/u/5140203?v=4" width="100px;" alt=""/><br /><sub><b>Michael Voell</b></sub></a><br /><a href="#design-SDCore" title="Design">🎨</a></td>
  </tr>
</table>

<!-- markdownlint-enable -->
<!-- prettier-ignore-end -->
<!-- ALL-CONTRIBUTORS-LIST:END -->

This project follows the [all-contributors](https://github.com/all-contributors/all-contributors) specification. Contributions of any kind welcome!
