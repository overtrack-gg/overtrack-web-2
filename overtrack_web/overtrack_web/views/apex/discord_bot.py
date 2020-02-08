import base64
import json
import logging
import os
from collections import defaultdict
from functools import lru_cache
from pprint import pprint
from typing import Optional, Union, Tuple, Dict, List

import jwt
import requests
import requests_oauthlib
import time
from flask import Blueprint, Response, redirect, render_template, request, url_for, jsonify, Request
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

USER_INFO = 'https://discordapp.com/api/users/@me'
USER_LIST_GUILDS = 'https://discordapp.com/api/users/%s/guilds'
GUILD_INFO = 'https://discordapp.com/api/guilds/%s'
GUILD_LIST_CHANNELS = 'https://discordapp.com/api/guilds/%s/channels'
GUILD_GET_GUILD_MEMBER = 'https://discordapp.com/api/guilds/%s/members/%s'
CHANNEL_INFO = 'https://discordapp.com/api/channels/%s'
CHANNEL_EDIT_PERMISSIONS = 'https://discordapp.com/api/channels/%s/permissions/%s'
CHANNEL_CREATE_MESSAGE = 'https://discordapp.com/api/channels/%s/messages'
CHANNEL_GET_MESSAGE = 'https://discordapp.com/api/channels/%s/messages/%s'

# https://discordapp.com/developers/docs/topics/permissions#permissions-bitwise-permission-flags
VIEW_CHANNEL = 0x00000400
READ_MESSAGE_HISTORY = 0x00010000
SEND_MESSAGES = 0x00000800
MANAGE_ROLES = 0x10000000
MANAGE_CHANNELS = 0x00000010
EMBED_LINKS = 0x00004000
ADD_REACTIONS = 0x00000040
USE_EXTERNAL_EMOJIS = 0x00040000
TEXT_CHANNEL = 0

logger = logging.getLogger(__name__)

discord_bot = requests.Session()
discord_bot.headers.update({
    'Authorization': f'Bot {DISCORD_BOT_TOKEN}'
})

logger.info(f'Caching DiscordBotNotifications')
t0 = time.perf_counter()
notification_cache = defaultdict(list)
q = DiscordBotNotification.scan()
for dbn in q:
    notification_cache[dbn.guild_id].append(dbn)
logger.info(f'Done - took {(time.perf_counter() - t0) * 1000:.2f}ms to scan {q.total_count} items')

discord_bot_blueprint = Blueprint('apex.discord_bot', __name__)

request: Request = request


@discord_bot_blueprint.context_processor
def context_processor():
    return {
        'game_name': 'apex'
    }


@discord_bot_blueprint.route('/')
@require_login
def root():
    notifications = []
    n: DiscordBotNotification
    for n in DiscordBotNotification.user_id_index.query(session.user_id):
        channel_info, guild_info = _get_channel_and_guild_info(n.channel_id)
        if not channel_info or not guild_info:
            logger.info(f'Could not get channel info for {n} - ignoring')
            continue
        if n.announce_message_id:
            if not check_message_exists(n.channel_id, n.announce_message_id):
                logger.info(f'Could not get announce message for {n} - ignoring')
                continue

        update_notification(n, guild_info, channel_info)
        notifications.append({
            'guild_name': n.guild_name,
            'channel_name': n.channel_name,
            'args': _make_signed_payload(
                type="delete",
                key=n.key
            )
        })

    return render_template(
        'discord_bot/discord_bot.html',

        notifications=notifications,
        delete_integration=url_for(discord_bot_blueprint.name + '.delete_integration'),

        authorize_bot=url_for(discord_bot_blueprint.name + '.authorize_bot'),
        authorize_list_servers=url_for(discord_bot_blueprint.name + '.authorize_list_servers'),
    )


@discord_bot_blueprint.route('/authorize_bot')
@require_authentication
@restrict_origin()
def authorize_bot():
    # Generate a bot oauth request as per https://discordapp.com/developers/docs/topics/oauth2#advanced-bot-authorization
    # Specifically we want redirect_uri to redirect back to us and want to specify permissions
    oauth = requests_oauthlib.OAuth2Session(
        CLIENT_ID,
        redirect_uri=url_for(discord_bot_blueprint.name + '.bot_authorized', _external=True),
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
        oauth = requests_oauthlib.OAuth2Session(
            CLIENT_ID,
            redirect_uri=request.base_url
        )
        token = oauth.fetch_token(
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

    r = oauth.get(
        USER_INFO
    )
    r.raise_for_status()
    discord_user = r.json()
    logger.info(f'{discord_user["username"]}#{discord_user["discriminator"]} ({discord_user["id"]}) ')

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
                'args': _make_signed_payload(
                    type='existing_channel',
                    channel_id=channel['id'],
                    discord_user_id=discord_user['id'],
                )
            })

    # Also provide `create_channel_payload` for creating a new channel
    return render_template(
        'discord_bot/channel_add.html',

        add_to_channel=url_for(discord_bot_blueprint.name + '.add_to_channel'),
        channels=channel_group,

        allow_create_channel=int(request.args['permissions']) & MANAGE_CHANNELS,
        create_channel_args=_make_signed_payload(
            type='create_channel',
            guild_id=request.args['guild_id'],
            create_channel=True,
            discord_user_id=discord_user['id'],
        ),
        server_name=token['guild']['name'],
        server_icon='https://cdn.discordapp.com/icons/{id}/{icon}.webp?'.format(
            id=token['guild']['id'],
            icon=token['guild']['icon']
        )
    )


@discord_bot_blueprint.route('/add_to_channel', methods=['POST'])
@require_authentication
@restrict_origin()
def add_to_channel():
    logger.info(f'Got add_to_channel with form {request.form}')

    if 'create_args' not in request.form and 'existing_args' not in request.form:
        return redirect(url_for(discord_bot_blueprint.name + '.root'))

    # Decode JWT `payload`
    # This ensures that the arguments (channel_id for existing channel, guild_id for creating channel) comes from the actual ouath'd user
    logger.info(f'Decoding JWT payload')
    try:
        args = jwt.decode(
            # try get create_args first, as this is on the "create" button
            # fall back to existing_args which is always present, but should only be used if "add" button was used
            request.form.get('create_args', request.form.get('existing_args')),
            HMAC_KEY,
            algorithms=['HS256']
        )['args']
    except InvalidTokenError as e:
        logger.error(f'Failed to decode JWT token')
        return Response(
            json.dumps({
                'error': f'Invalid token'
            }),
            status=403
        )
    logger.info(f'JWT payload: {args}')

    if args['type'] == 'existing_channel':
        # using an existing channel - attempt to add SEND_MESSAGE permission for ourselves... don't mind if this errors
        channel_id = args['channel_id']
        logger.info(f'Using existing channel {channel_id} to post games')
        logger.info(f'Checking for post permission')
        added_post_permission = _add_post_permission(channel_id)
    elif args['type'] == 'create_channel':
        # creating a new channel - create this channel with SEND_MESSAGE for ourselves and view only for everyone else
        logger.info(f'Creating new channel {request.form["channel_name"]} to post games to')
        channel_id = _create_channel(
            args['guild_id'],
            request.form['channel_name'],
            restrict_posting=request.form.get('restrict_post_messages', '') == 'on'
        )
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
        logger.error(f'Can\'t handle add_to_channel request - unknown type {args["type"]}')
        return Response(
            json.dumps({
                'error': 'Unknown integration type'
            }),
            status=400
        )

    # Get the channel and guild name
    # This is used simply for recording in the database, so we can have channel names in the delete list
    channel_info, guild_info = _get_channel_and_guild_info(channel_id)

    parent_key = args.get('parent_key')
    logger.info(f'Creating new discord bot (parent={parent_key})')

    # Try to send the greetings message
    logger.info(f'Sending intro message')
    message = f'OverTrack is now posting <@{args["discord_user_id"]}>\'s Apex Legends games to this channel!\n\n'
    if parent_key is not None:
        message += f'Permission was granted because <@{args["discord_user_id"]}> has permissions to post messages in this channel.\n'
    message += f'To stop posting <@{args["discord_user_id"]}>\'s games here a channel admin can delete this message, ' \
               f'or <@{args["discord_user_id"]}> can remove their integration.\n'

    create_message_r = discord_bot.post(
        CHANNEL_CREATE_MESSAGE % (channel_id,),
        json={
            'content': message
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
        discord_user_id=args['discord_user_id'],
        announce_message_id=create_message['id'],

        game='apex',

        channel_id=channel_id,
        guild_id=channel_info['guild_id'],
        guild_name=guild_info['name'],
        channel_name=channel_info['name'],

        notification_data={
            'top3_only': request.args.get('only_top_3') == 'on'
        },

        is_parent=parent_key is None,
        autoapprove_children=parent_key is None,
        parent_key=parent_key,

    )
    logger.info(f'Created {notification}')
    notification_cache[notification.guild_id].append(notification)
    notification.save()

    return redirect(url_for(discord_bot_blueprint.name + '.root'))


@discord_bot_blueprint.route('/delete_integration', methods=['POST'])
@require_authentication
@restrict_origin()
def delete_integration():
    logger.info(f'Decoding JWT payload')
    try:
        args = jwt.decode(
            request.form.get('args', ''),
            HMAC_KEY,
            algorithms=['HS256']
        )['args']
    except InvalidTokenError as e:
        logger.error(f'Failed to decode JWT token')
        return Response(
            json.dumps({
                'error': f'Invalid token'
            }),
            status=403
        )
    logger.info(f'JWT payload: {args}')

    if args['type'] != 'delete':
        logger.error(f'Can\'t handle delete_integration request - unknown type {args["type"]}')
        return Response(
            json.dumps({
                'error': 'Unknown request type'
            }),
            status=400
        )

    notification = DiscordBotNotification.get(args['key'])
    logger.info(f'Deleting {notification}')
    notification.delete()

    return redirect(url_for(discord_bot_blueprint.name + '.root'))


@discord_bot_blueprint.route('/authorize_list_servers')
@require_authentication
def authorize_list_servers():
    oauth = requests_oauthlib.OAuth2Session(
        CLIENT_ID,
        redirect_uri=url_for(discord_bot_blueprint.name + '.add_to_existing', _external=True),
        scope=['guilds'],
    )
    authorisation_url, state = oauth.authorization_url(AUTHORISE_URL)
    logger.info(f'Got OAUTH authorisation url: {authorisation_url}')

    return redirect(authorisation_url)


@discord_bot_blueprint.route('/add_to_existing')
@require_authentication
def add_to_existing():
    logger.info(f'Fetching OAUTH token from {request.url} for {session.user}')
    try:
        oauth = requests_oauthlib.OAuth2Session(
            CLIENT_ID,
            redirect_uri=request.base_url
        )
        token = oauth.fetch_token(
            TOKEN_URL,
            client_secret=CLIENT_SECRET,
            authorization_response=request.url.replace('http://', 'https://')
        )
    except OAuth2Error as e:
        logger.error(f'OAuth verification failed')
        return Response(
            json.dumps({
                'error': f'OAuth verification failed: {e}'
            }),
            status=403
        )
    print('Token:')
    pprint(token)

    r = oauth.get(
        USER_INFO
    )
    r.raise_for_status()
    discord_user = r.json()
    logger.info(f'{discord_user["username"]}#{discord_user["discriminator"]} ({discord_user["id"]}) ')

    # Check what servers the user is in
    r = oauth.get(
        USER_LIST_GUILDS % ('@me', )
    )
    r.raise_for_status()
    guilds = r.json()
    logger.info(f'User is in {len(guilds)} guilds')

    allowed_servers = []
    for membership in guilds:
        existing_notification: DiscordBotNotification
        for existing_notification in notification_cache[membership['id']]:
            if not existing_notification.autoapprove_children:
                logger.warning(f'Found matching {existing_notification}, but autoapprove_children is False, not including')
                continue
            if not check_message_exists(existing_notification.channel_id, existing_notification.announce_message_id):
                logger.warning(f'Found matching {existing_notification}, but announce message could not be retreived, not including')
                continue

            logger.info(
                f'Found mutual channel {existing_notification.guild_name} > '
                f'#{existing_notification.channel_name} ({existing_notification.channel_id})'
            )
            print('Guild membership:')
            pprint(membership)

            channel_info, guild_info = _get_channel_and_guild_info(existing_notification.channel_id)
            if not channel_info or not guild_info:
                continue

            assert guild_info['id'] == existing_notification.guild_id

            update_notification(existing_notification, guild_info, channel_info)

            guild_member = _get_guild_member(existing_notification.guild_id, discord_user['id'])
            if not guild_member:
                continue

            # guild-level permissions is already computed by User.list_guilds, so we just need to compute channel overrides

            permissions = compute_permissions(membership['permissions'], guild_member, channel_info)
            if guild_info['owner_id'] == guild_member['user']['id']:
                logger.info('User is owner - vibe check passed')
            elif not permissions & SEND_MESSAGES:
                logger.info(f'User does not have SEND_MESSAGES permissions (permissions={permissions:x})')
                continue

            logger.info(f'User has SEND_MESSAGES permission (permissions={permissions:x})')
            allowed_servers.append({
                'name': f'{existing_notification.guild_name} #{existing_notification.channel_name}',
                'args': _make_signed_payload(
                    type='existing_channel',
                    channel_id=existing_notification.channel_id,
                    discord_user_id=discord_user['id'],
                    parent_key=existing_notification.key,
                ),
            })

    return render_template(
        'discord_bot/channel_add.html',

        add_to_channel=url_for(discord_bot_blueprint.name + '.add_to_channel'),
        channels=allowed_servers,

        allow_create_channel=False,
    )


def update_notification(existing_notification: DiscordBotNotification, guild_info: Dict, channel_info: Dict) -> None:
    if guild_info['name'] != existing_notification.guild_name or channel_info['name'] != existing_notification.channel_name:
        logger.info(f'Updating {existing_notification} guild_name={guild_info["name"]}, channel_name={channel_info["name"]}')
        existing_notification.refresh()
        existing_notification.guild_name = guild_info['name']
        existing_notification.channel_name = channel_info['name']
        existing_notification.save()


def compute_permissions(base_permissions: int, guild_member: Dict, channel: Dict) -> int:
    logger.info(f'Checking user permissions in #{channel["name"]}')

    allow = 0
    deny = 0

    permission_overwrites = {
        overwrite['id']: overwrite
        for overwrite in channel['permission_overwrites']
    }

    # check in order @everyone permissions, channel role permissions, user specific permissions
    for role in [channel['guild_id']] + guild_member['roles'] + [guild_member['user']['id']]:
        overwrite = permission_overwrites.get(role)
        if overwrite:
            allow |= overwrite['allow']
            deny |= overwrite['deny']

    return (base_permissions & ~deny) | allow


def check_message_exists(channel_id: str, message_id: Optional[str]) -> bool:
    if not message_id:
        return False
    r = discord_bot.get(
        CHANNEL_GET_MESSAGE % (channel_id, message_id)
    )
    if r.status_code in [403, 404]:
        logger.warning(f'Message {message_id} got status {r.status_code} - message appears missing')
        return False
    r.raise_for_status()
    print('Get message')
    pprint(r.json())
    return True


def _get_channel_and_guild_info(channel_id: str) -> Tuple[Optional[Dict], Optional[Dict]]:
    logger.info(f'Getting channel info for {channel_id}')
    channel_info_r = discord_bot.get(
        CHANNEL_INFO % (channel_id,)
    )
    if channel_info_r.status_code in [404, 403]:
        logger.warning(f'Got {channel_info_r.status_code} getting channel info')
        return None, None
    channel_info_r.raise_for_status()
    channel_info = channel_info_r.json()
    print('Channel info: ')
    pprint(channel_info)
    logger.info(f'Got channel info for #{channel_info["name"]} ({channel_id})')

    logger.info(f'Getting guild info for {channel_info["guild_id"]}')
    guild_info_r = discord_bot.get(
        GUILD_INFO % (channel_info['guild_id'],)
    )
    guild_info_r.raise_for_status()
    if channel_info_r.status_code in [404, 403]:
        logger.warning(f'Got {guild_info_r.status_code} getting guild info')
        return None, None
    guild_info = guild_info_r.json()
    print('Guild info: ')
    print_guild_info = dict(guild_info)
    print_guild_info['emojis'] = '...'
    print_guild_info['roles'] = [(r['id'], r['name'], r['permissions']) for r in print_guild_info['roles']]
    pprint(print_guild_info)
    logger.info(f'Got guild info for guild {guild_info["name"]} ({guild_info["id"]})')
    return channel_info, guild_info


def _get_guild_member(guild_id: str, user_id: str) -> Optional[Dict]:
    r = discord_bot.get(
        GUILD_GET_GUILD_MEMBER % (guild_id, user_id)
    )
    if r.status_code in [404, 403]:
        logger.warning(
            f'Ignoring guild - got {r.status_code} getting channel info'
        )
        return None
    r.raise_for_status()
    guild_member = r.json()
    print('Guild member: ')
    pprint(guild_member)
    return guild_member


def _create_channel(guild_id: str, channel_name: str, restrict_posting: bool) -> Optional[str]:
    logger.info(f'Creating channel {channel_name} in {guild_id}')
    permission_overwrites = [
        {
            'id': DISCORD_BOT_ID,
            'type': 'member',
            'allow': SEND_MESSAGES | VIEW_CHANNEL | READ_MESSAGE_HISTORY,
            'deny': 0
        }
    ]
    if restrict_posting:
        permission_overwrites.append({
            'id': guild_id,
            'type': 'role',
            'allow': VIEW_CHANNEL | ADD_REACTIONS | USE_EXTERNAL_EMOJIS | READ_MESSAGE_HISTORY,
            'deny': SEND_MESSAGES
        })
    create_channel = discord_bot.post(
        GUILD_LIST_CHANNELS % (guild_id,),
        json={
            'name': channel_name,
            'type': TEXT_CHANNEL,
            'topic': 'Apex Legends Games | OverTrack.gg',
            'permission_overwrites': permission_overwrites
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
    logger.info(f'Adding SEND_MESSAGES permission for {DISCORD_BOT_ID} to post to #{channel_id}')
    edit_permisions = discord_bot.put(
        CHANNEL_EDIT_PERMISSIONS % (channel_id, DISCORD_BOT_ID),
        json={
            'allow': SEND_MESSAGES | EMBED_LINKS | VIEW_CHANNEL,
            'type': 'member'
        }
    )
    print(edit_permisions.status_code)
    pprint(edit_permisions.content)
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
