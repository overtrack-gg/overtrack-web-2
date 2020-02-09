## Running Locally

### Dependencies
Dependencies are installed through poetry
```bash
poetry install
```
Note specifically the dependency on [overtrack-models](https://gitlab.com/OverTrack/overtrack-models)

### Running
`overtrack_web/overtrack_web/local_flask_app.py` exposes a flask app that matches much of the live version and mocks access to games 
so that games are populated from the OverTrack API using public share links.
The source of the "mock" games can be changed by changing the environment variables `APEX_GAMES_SOURCE` and `OVERWATCH_GAMES_SOURCE`.
It would also be possible to modify the initial fetching of games to use a session cookie instead, which would allow you use your own games.

`local_flask_app` does not run with the discord bot or subscribe pages active, and mocks login so that you are always logged in as a mock user.

`overtrack_web/overtrack_web/flask_app.py` is the flask app used for hosting the actual site, and requires access to overtrack's AWS resources.

Run either
```bash
FLASK_APP=apextrack.local_flask_app FLASK_DEBUG=1 poetry run flask run 
```
if you are using poetry's automatic virtual environments or 
```bash
FLASK_APP=apextrack.local_flask_app FLASK_DEBUG=1 flask run 
```
if you are managing your virtual environment yourself.
