import base64
import json
import logging
import os
from typing import Union, Optional

import time
from pprint import pprint

import jwt
import requests
from flask import Flask, redirect, request, jsonify, url_for, Response, Blueprint, render_template
import requests_oauthlib
from jwt import InvalidSignatureError, InvalidTokenError
from oauthlib.oauth2 import InvalidClientIdError, OAuth2Error

HMAC_KEY = base64.b64decode(os.environ['HMAC_KEY'])

CLIENT_ID = os.environ['DISCORD_CLIENT_ID']
CLIENT_SECRET = os.environ['DISCORD_CLIENT_SECRET']
AUTHORISE_URL = 'https://discordapp.com/api/oauth2/authorize'
VIEW_CHANNEL = 0x00000400
SEND_MESSAGES = 0x00000800
MANAGE_ROLES = 0x10000000
MANAGE_CHANNELS = 0x00000010
ADD_REACTIONS = 0x00000040

TOKEN_URL = 'https://discordapp.com/api/oauth2/token'

DISCORD_BOT_TOKEN = os.environ['DISCORD_BOT_TOKEN']
DISCORD_BOT_ID = os.environ.get('DISCORD_BOT_ID', '470874176350191637')

GUILDS_CHANNELS = 'https://discordapp.com/api/guilds/%s/channels'

CHANNELS_EDIT_PERMISSIONS = 'https://discordapp.com/api/channels/%s/permissions/%s'
CHANNELS_CREATE_MESSAGE = 'https://discordapp.com/api/channels/%s/messages'

TEXT_CHANNEL = 0

logger = logging.getLogger(__name__)

discord_bot = requests.Session()
discord_bot.headers.update({
    'Authorization': f'Bot {DISCORD_BOT_TOKEN}'
})

discord_bot_blueprint = Blueprint('discord_bot', __name__)


@discord_bot_blueprint.route('/')
def root():
    return render_template('discord_bot/root.html')


@discord_bot_blueprint.route('/authorize_bot')
def authorize_bot():
    oauth = requests_oauthlib.OAuth2Session(
        CLIENT_ID,
        redirect_uri=url_for('discord_bot.bot_authorized', _external=True),
        scope=['bot'],
    )

    authorisation_url, state = oauth.authorization_url(AUTHORISE_URL, permissions=SEND_MESSAGES | MANAGE_ROLES | MANAGE_CHANNELS)
    logger.info(f'Got OAUTH authorisation url: {authorisation_url}')

    return redirect(authorisation_url, code=302)


@discord_bot_blueprint.route('/bot_authorized')
def bot_authorized():
    # verify that this request has gone through discord auth flow
    logger.info(f'Fetching OAUTH token from {request.url}')
    try:
        token = requests_oauthlib.OAuth2Session(
            CLIENT_ID,
            redirect_uri=request.base_url
        ).fetch_token(
            TOKEN_URL,
            client_secret=CLIENT_SECRET,
            authorization_response=request.url.replace('http://', 'https://')
        )
    except OAuth2Error as e:
        logger.warning(f'OAuth verification failed: {e}')
        return Response(
            json.dumps({
                'error': f'OAuth verification failed: {e}'
            }),
            status=403
        )
    print('Token:')
    pprint(token)

    if not int(request.args['permissions']) & SEND_MESSAGES:
        return 'Error: did not get permission to send messages'

    r = discord_bot.get(
        GUILDS_CHANNELS % (request.args['guild_id'],)
    )
    r.raise_for_status()
    channels = r.json()
    print('Channels:')
    pprint(channels)

    channel_group = []
    for channel in channels:
        if channel['type'] == TEXT_CHANNEL:
            # url = _make_signed_url(url_for('discord_bot.add_to_channel'), channel_id=channel['id'])
            channel_group.append({
                'name': channel['name'],
                'payload': _make_signed_payload(channel_id=channel['id'])
            })

    return render_template(
        'discord_bot/channel_add.html',
        channels=channel_group,
        allow_create_channel=int(request.args['permissions']) & MANAGE_CHANNELS,
        create_channel_payload=_make_signed_payload(guild_id=request.args['guild_id'], create_channel=True),
        server_name=token['guild']['name'],
        server_icon='https://cdn.discordapp.com/icons/{id}/{icon}.webp?'.format(
            id=token['guild']['id'],
            icon=token['guild']['icon']
        )
    )


@discord_bot_blueprint.route('/add_to_channel')
def add_to_channel():
    logger.info(f'Decoding JWT payload')
    try:
        args = jwt.decode(
            request.args.get('payload', ''),
            HMAC_KEY,
            algorithms=['HS256']
        )['args']
    except InvalidTokenError as e:
        logger.error(f'Failed to decode JWT token')
        return Response(
            json.dumps({
                'error': f'Invalid token: {e}'
            }),
            status=403
        )
    logger.info(f'JWT payload: {args}')

    if 'channel_id' in args:
        channel_id = args['channel_id']
        added_post_permission = _add_post_permission(channel_id)
    elif 'create_channel' in args:
        channel_id = _create_channel(args['guild_id'], request.args['channel_name'])
        if not channel_id:
            return Response(
                f'<html><head></head><body>'
                f'<p>Did not have permission to create channel - '
                f'please verify that the OverTrack bot has permission create a channel then <a href="{request.url}">retry</a></p>'
                f'</body></html>',
                content_type='text/html'
            )

    else:
        logger.error('Can\'t handle add_to_channel request')
        return Response(
            json.dumps({
                'error': 'Invalid request'
            }),
            status=400
        )

    logger.info(f'Sending intro message')
    create_message = discord_bot.post(
        CHANNELS_CREATE_MESSAGE % (channel_id,),
        json={
            'content': 'Hi!'
        }
    )
    pprint(create_message.content)
    if create_message.status_code == 403:
        logger.warning(f'Failed to send intro message: {create_message.status_code}')
        return Response(
            f'<html><head></head><body>'
            f'<p>Could not post to channel - '
            f'please verify that the OverTrack bot has permission to post (or to modify channel permissions) then <a href="{request.url}">retry</a></p>'
            f'</body></html>',
            content_type='text/html'
        )
    create_message.raise_for_status()
    pprint(create_message.json())
    logger.info(f'Intro message sent: {create_message.status_code} - id: {create_message.json()["id"]}')

    return redirect(url_for('discord_bot.root'))
    # return jsonify(data=create_message.json())


def _create_channel(guild_id: str, channel_name: str) -> Optional[str]:
    logger.info(f'Creating channel {channel_name} in {guild_id}')
    create_channel = discord_bot.post(
        GUILDS_CHANNELS % (guild_id, ),
        json={
            'name': channel_name,
            'type': TEXT_CHANNEL,
            'topic': 'OverTrack Bot',  # TODO: channel topic,
            'permission_overwrites': [
                {
                    'id': guild_id,
                    'type': 'role',
                    'allow': VIEW_CHANNEL | ADD_REACTIONS,
                    'deny': SEND_MESSAGES
                },
                {
                    'id': DISCORD_BOT_ID,
                    'type': 'member',
                    'allow': SEND_MESSAGES | VIEW_CHANNEL,
                    'deny': 0
                },
            ]
        }
    )
    if create_channel.status_code == 403:
        logger.warning(f'Did not have permissions to create channel: {create_channel.status_code}')
        return None

    create_channel.raise_for_status()

    print('Create channel:')
    pprint(create_channel.json())

    channel_id = create_channel.json()['id']
    logger.info(f'Created new channel, id={channel_id}')
    return channel_id


def _add_post_permission(channel_id: str) -> bool:
    logger.info(f'Adding SEND_MESSAGES permission for {DISCORD_BOT_ID} to post to {channel_id}')
    edit_permisions = discord_bot.put(
        CHANNELS_EDIT_PERMISSIONS % (channel_id, DISCORD_BOT_ID),
        json={
            'allow': SEND_MESSAGES | VIEW_CHANNEL,
            'type': 'member'
        }
    )
    if edit_permisions.status_code == 403:
        logger.warning(f'Failed to add SEND_MESSAGES permission: {edit_permisions.status_code}')
        return False
    elif 200 <= edit_permisions.status_code < 300:
        logger.warning(f'Added SEND_MESSAGES permission: {edit_permisions.status_code}')
        return True
    else:
        edit_permisions.raise_for_status()


def _make_signed_payload(**kwargs: Union[str, bool, int]) -> str:
    return jwt.encode(
        {
            'args': kwargs,
            'exp': time.time() + 60 * 15
        },
        key=HMAC_KEY,
        algorithm='HS256'
    ).decode()


# def main() -> None:
#     from overtrack.util.logging_config import config_logger
#     config_logger(__name__, logging.INFO, False)
#     app.run(port=5005)
#
#
# if __name__ == '__main__':
#     main()
