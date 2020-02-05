import base64
import json
import logging
import os
from pprint import pprint
from typing import Optional, Union, Tuple, Dict

import jwt
import requests
import requests_oauthlib
import time
from flask import Blueprint, Response, redirect, render_template, request, url_for
from jwt import InvalidTokenError
from oauthlib.oauth2 import OAuth2Error

from overtrack_web.lib.authentication import require_authentication, require_login
from overtrack_web.lib.decorators import restrict_origin
from overtrack_web.lib.session import session
from overtrack_models.orm.notifications import DiscordBotNotification

HMAC_KEY = base64.b64decode(os.environ['HMAC_KEY'])

CLIENT_ID = os.environ['DISCORD_CLIENT_ID']
CLIENT_SECRET = os.environ['DISCORD_CLIENT_SECRET']
AUTHORISE_URL = 'https://discordapp.com/api/oauth2/authorize'
TOKEN_URL = 'https://discordapp.com/api/oauth2/token'

DISCORD_BOT_TOKEN = os.environ['DISCORD_BOT_TOKEN']
DISCORD_BOT_ID = os.environ.get('DISCORD_BOT_ID', '470874176350191637')

GUILD_INFO = 'https://discordapp.com/api/guilds/%s'
GUILD_LIST_CHANNELS = 'https://discordapp.com/api/guilds/%s/channels'
CHANNEL_INFO = 'https://discordapp.com/api/channels/%s'
CHANNEL_EDIT_PERMISSIONS = 'https://discordapp.com/api/channels/%s/permissions/%s'
CHANNEL_CREATE_MESSAGE = 'https://discordapp.com/api/channels/%s/messages'
# https://discordapp.com/developers/docs/topics/permissions#permissions-bitwise-permission-flags
VIEW_CHANNEL = 0x00000400
SEND_MESSAGES = 0x00000800
MANAGE_ROLES = 0x10000000
MANAGE_CHANNELS = 0x00000010
ADD_REACTIONS = 0x00000040
EMBED_LINKS = 0x00004000
TEXT_CHANNEL = 0

logger = logging.getLogger(__name__)

discord_bot = requests.Session()
discord_bot.headers.update({
    'Authorization': f'Bot {DISCORD_BOT_TOKEN}'
})

discord_bot_blueprint = Blueprint('discord_bot', __name__)


@discord_bot_blueprint.route('/')
@require_login
def discord_bot():
    notifications = []
    for n in DiscordBotNotification.user_id_index.query(session.user_id):
        # TODO: should we try update server/channel names?
        notifications.append({
            'guild_name': n.guild_name,
            'channel_name': n.channel_name,
            'delete_url': url_for('discord_bot.delete_channel') + '?payload=' + _make_signed_payload(key=n.key)
        })
    return render_template(
        'discord_bot/discord_bot.html',
        notifications=notifications
    )


@discord_bot_blueprint.route('/authorize_bot')
@require_authentication
@restrict_origin()
def authorize_bot():
    # Generate a bot oauth request as per https://discordapp.com/developers/docs/topics/oauth2#advanced-bot-authorization
    # Specifically we want redirect_uri to redirect back to us and want to specify permissions
    oauth = requests_oauthlib.OAuth2Session(
        CLIENT_ID,
        redirect_uri=url_for('discord_bot.bot_authorized', _external=True),
        scope=['bot'],
    )
    authorisation_url, state = oauth.authorization_url(AUTHORISE_URL, permissions=SEND_MESSAGES | MANAGE_ROLES | MANAGE_CHANNELS)
    logger.info(f'Got OAUTH authorisation url: {authorisation_url}')

    return redirect(authorisation_url, code=302)


@discord_bot_blueprint.route('/bot_authorized')
@require_authentication
def bot_authorized():
    # Verify that this request has gone through discord auth flow
    # While we don't use `token`, we need to check that this request is a true redirect from discord, and not someone CSRFing with just guild_id set
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

    # We need to be able to send messages
    # Not being able to manage roles and channels is fine if the channel is already postable to us
    if not int(request.args['permissions']) & SEND_MESSAGES:
        return 'Error: did not get permission to send messages'

    # Check what channels we can see
    r = discord_bot.get(
        GUILD_LIST_CHANNELS % (request.args['guild_id'],)
    )
    r.raise_for_status()
    channels = r.json()
    print('Channels:')
    pprint(channels)

    # Prepare channels list for user
    # Each channel we generate a JWT payload with `channel_id` set.
    # This payload is then used in `add_to_channel` to verify that this is a legit request (ie from a user that went through the oauth flow)
    channel_group = []
    for channel in channels:
        if channel['type'] == TEXT_CHANNEL:
            channel_group.append({
                'name': channel['name'],
                'payload': _make_signed_payload(channel_id=channel['id'])
            })

    # Also provide `create_channel_payload` for creating a new channel
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
@require_authentication
@restrict_origin()
def add_to_channel():
    if request.args.get('channel_type') == 'existing':
        payload_type = 'payload_existing'
    elif request.args.get('channel_type') == 'new':
        payload_type = 'payload_new'
    else:
        logger.error(f'add_to_channel got nonsensical submission')
        return Response(
            f'<html><head></head><body>'
            f'<p>Error processing form</p>'
            f'</body></html>',
            content_type='text/html'
        )

    # Decode JWT `payload`
    # This ensures that the arguments (channel_id for existing channel, guild_id for creating channel) comes from the actual ouath'd user
    logger.info(f'Decoding JWT payload')
    try:
        args = jwt.decode(
            request.args.get(payload_type, ''),
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
        # using an existing channel - attempt to add SEND_MESSAGE permission for ourselves... don't mind if this errors
        channel_id = args['channel_id']
        added_post_permission = _add_post_permission(channel_id)
    elif 'create_channel' in args:
        # creating a new channel - create this channel with SEND_MESSAGE for ourselves and view only for everyone else
        channel_id = _create_channel(args['guild_id'], request.args['channel_name'])
        if not channel_id:
            # if we didn't create the channel, complain
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

    # Get the channel and guild name
    # This is used simply for recording in the database, so we can have channel names in the delete list
    channel_info, guild_info = _get_channel_and_guild_info(channel_id)

    # Try to send the greetings message
    logger.info(f'Sending intro message')
    create_message_r = discord_bot.post(
        CHANNEL_CREATE_MESSAGE % (channel_id,),
        json={
            'content': f'OverTrack is now posting Apex Legends games from {session.username} to this channel!'
        }
    )
    pprint(create_message_r.content)
    if create_message_r.status_code == 403:
        logger.warning(f'Failed to send intro message: {create_message_r.status_code}')
        return Response(
            f'<html><head></head><body>'
            f'<p>Could not post to channel - '
            f'please verify that the OverTrack bot has permission to post (or to modify channel permissions) then <a href="{request.url}">retry</a></p>'
            f'</body></html>',
            content_type='text/html'
        )
    create_message_r.raise_for_status()
    create_message = create_message_r.json()
    print('Create message: ')
    pprint(create_message)
    logger.info(f'Intro message sent: {create_message_r.status_code} - id: {create_message["id"]}')

    # Save the notification settings
    notification = DiscordBotNotification.create(
        user_id=session.user_id,
        game='apex',
        channel_id=channel_id,
        guild_id=channel_info['guild_id'],
        guild_name=guild_info['name'],
        channel_name=channel_info['name'],
        notification_data={
            'top3_only': request.args.get('only_top_3') == 'on'
        }
    )
    logger.info(f'Created {notification}')
    notification.save()

    return redirect(url_for('discord_bot.root'))


@discord_bot_blueprint.route('/delete_channel')
@require_authentication
@restrict_origin()
def delete_channel():
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

    notification = DiscordBotNotification.get(args['key'])
    logger.info(f'Deleting {notification}')
    notification.delete()

    return redirect(url_for('discord_bot.discord_bot'))


def _get_channel_and_guild_info(channel_id: str) -> Tuple[Dict, Dict]:
    logger.info(f'Getting channel info for {channel_id}')
    channel_info_r = discord_bot.get(
        CHANNEL_INFO % (channel_id,)
    )
    channel_info_r.raise_for_status()
    channel_info = channel_info_r.json()
    print('Channel info: ')
    pprint(channel_info)
    logger.info(f'Got channel info - name={channel_info["name"]}')
    logger.info(f'Getting guild info for {channel_info["guild_id"]}')
    guild_info_r = discord_bot.get(
        GUILD_INFO % (channel_info['guild_id'],)
    )
    guild_info_r.raise_for_status()
    guild_info = guild_info_r.json()
    print('Guild info: ')
    pprint(guild_info)
    logger.info(f'Got guild info - name={guild_info["name"]}')
    return channel_info, guild_info


def _create_channel(guild_id: str, channel_name: str) -> Optional[str]:
    logger.info(f'Creating channel {channel_name} in {guild_id}')
    create_channel = discord_bot.post(
        GUILD_LIST_CHANNELS % (guild_id,),
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
        CHANNEL_EDIT_PERMISSIONS % (channel_id, DISCORD_BOT_ID),
        json={
            'allow': SEND_MESSAGES | EMBED_LINKS | VIEW_CHANNEL,
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
