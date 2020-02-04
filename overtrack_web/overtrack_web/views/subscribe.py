import logging
import os
from pprint import pprint
from typing import Optional, Tuple

import stripe
import time
from flask import Blueprint, Response, render_template, request, url_for
from werkzeug.utils import redirect

from overtrack_web.lib import metrics
from overtrack_web.lib.authentication import require_login
from overtrack_web.lib.decorators import restrict_origin
from overtrack_web.lib.paypal import PayPal
from overtrack_web.lib.session import session
from overtrack_models.orm.subscription_details import SubscriptionDetails

# default keys here are test/sandbox keys

STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY', 'pk_test_F567NgBmv1HXb8GWPtOoUQRz')
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_boLthxW5ni28yjidrmDHmNH3')
stripe.api_version = os.environ.get('STRIPE_API_VERSION', '2019-08-14')

PAYPAL_CLIENT_ID = os.environ.get('PAYPAL_CLIENT_ID', 'AbtR1E2mVIg_kXSpY071A798VVlgcIndAz5Hxm8PzWBAcsDykfm7SStIlJfS10b15pQVoOzTfKkvCsq8')
PAYPAL_CLIENT_SECRET = os.environ.get('PAYPAL_SECRET', 'EFPCvY4tYpaOIQKci8cJEpD4mwv9DESmqpcJpAeU590_ASpyhMeJ0JNQToTrHIriqJLCt9kksm54xNsb')

STRIPE_1_MONTHLY_PLAN = os.environ.get('STRIPE_MONTHLY_PLAN', 'plan_FhKrKMGDf5sb7Z')
STRIPE_6_MONTHLY_PLAN = os.environ.get('STRIPE_SIX_MONTHLY_PLAN', 'plan_FhKx6524k81dlz')
STRIPE_12_MONTHLY_PLAN = os.environ.get('STRIPE_YEARLY_PLAN', 'plan_FhKxcDNk8BbEGy')

if os.environ.get('PAYPAL_STRIPE_LIVE', 'false').lower() != 'true':
    # sandbox plans
    PAYPAL_1_MONTHLY_PLAN = os.environ.get('PAYPAL_MONTHLY_PLAN', 'P-60H31831T3281031VLVSMG3Y')
    PAYPAL_6_MONTHLY_PLAN = os.environ.get('PAYPAL_SIX_MONTHLY_PLAN', 'P-9VM324732B936170WLVSP2DI')
    PAYPAL_12_MONTHLY_PLAN = os.environ.get('PAYPAL_YEARLY_PLAN', 'P-4UC75129TL966731ALVTAJ3I')

    paypal_client = PayPal(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET)
else:
    PAYPAL_1_MONTHLY_PLAN = os.environ.get('PAYPAL_MONTHLY_PLAN', 'P-47G08335Y9035562LLVSQB6Y')
    PAYPAL_6_MONTHLY_PLAN = os.environ.get('PAYPAL_SIX_MONTHLY_PLAN', 'P-5AL222537P2933007LVSQCHA')
    PAYPAL_12_MONTHLY_PLAN = os.environ.get('PAYPAL_YEARLY_PLAN', 'P-4HK16427P0184862NLVSQCLQ')

    paypal_client = PayPal(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, sandbox=False)

logger = logging.getLogger(__name__)

subscribe_blueprint = Blueprint('subscribe', __name__)


@subscribe_blueprint.route('/')
@require_login
def subscribe():
    def make_stripe_checkout_session(plan_id: str):
        return stripe.checkout.Session.create(
            # TODO: reuse customer if they exist?
            payment_method_types=['card'],
            subscription_data={
                'items': [{
                    'plan': plan_id,
                }],
                'metadata': {
                    'user_id': session.user_id,
                    'username': session.username,
                    'battletag': session.user.battletag
                }
            },
            success_url=url_for('subscribe.subscribe', _external=True),
            cancel_url=url_for('subscribe.subscribe', _external=True),

            client_reference_id=f'{session.user.user_id}|{time.time()}',  # must be unique - append timestamp
        )

    show_sub_buttons = True
    unsub_button = None
    status_text = ''
    kwargs = {}

    session.user.refresh()
    print(session.user)
    print(session.user.subscription_active)
    print(session.user.subscription_type)
    print(session.user.stripe_subscription_id)
    if session.user.subscription_active:
        if session.user.subscription_type == 'v2.paypal':
            show_sub_buttons, unsub_button, status_text = check_paypal_subscription()
        elif session.user.subscription_type in ['stripe', 'v2.stripe']:
            show_sub_buttons, unsub_button, status_text = check_stripe_subscription()
        else:
            show_sub_buttons = False
            unsub_button = None
            status_text = '''
            <p>
                You appear to be subscribed to OverTrack through the Overwatch site.
                You can manage your subscription <a href="https://overtrack.gg/subscribe">there</a>.
            </p>
            '''

    if show_sub_buttons:
        kwargs.update(
            STRIPE_PUBLIC_KEY=STRIPE_PUBLIC_KEY,
            stripe_plan_session_ids=[
                make_stripe_checkout_session(STRIPE_1_MONTHLY_PLAN).id,
                make_stripe_checkout_session(STRIPE_6_MONTHLY_PLAN).id,
                make_stripe_checkout_session(STRIPE_12_MONTHLY_PLAN).id,
            ],

            PAYPAL_CLIENT_ID=PAYPAL_CLIENT_ID,
            paypal_plan_ids=[
                PAYPAL_1_MONTHLY_PLAN,
                PAYPAL_6_MONTHLY_PLAN,
                PAYPAL_12_MONTHLY_PLAN,
            ]
        )

    return render_template(
        'subscribe/subscribe.html',

        subscription_active=session.user.subscription_active,
        has_discord_role=session.user.discord_id is not None,

        show_sub_buttons=show_sub_buttons,
        unsub_button=unsub_button,
        status_text=status_text,
        **kwargs
    )


def check_paypal_subscription() -> Tuple[bool, Optional[str], str]:
    sub_id = session.user.paypal_subscr_id
    logger.info(f'Checking PayPal subscription {sub_id}')
    try:
        sub = paypal_client.get_subscription_details(sub_id)
    except:
        logger.exception(f'Failed to fetch PayPal subscription')
        return False, None, '''
        <p>
            An unknown error occurred checking your subscription status. Please be patient while this issue is investigated.
        </p>
        '''

    logger.info(f'Got subscription status {sub["status"]}')

    logger.info(f'Checking PayPal plan details {sub["plan_id"]}')
    try:
        plan = paypal_client.get_plan_details(sub['plan_id'])
    except:
        logger.exception('Failed to fetch PayPal plan details')
        plan_name = None
        plan_cost = None
        plan_period = None
    else:
        plan_name = plan['description']
        plan_cost = '$' + plan['billing_cycles'][0]['pricing_scheme']['fixed_price']['value']
        plan_period = f'{plan["billing_cycles"][0]["frequency"]["interval_count"]} {plan["billing_cycles"][0]["frequency"]["interval_unit"].lower()}'
        if plan['billing_cycles'][0]['frequency']['interval_count'] > 1:
            plan_period += 's'

    unsub_link = url_for('subscribe.paypal_cancel')

    if sub['status'] == 'ACTIVE':
        if plan_name:
            return False, unsub_link, f'''
            <p>
                You are currently subscribed to <code>{plan_name}</code> through PayPal, 
                which will bill you <code>{plan_cost}</code> 
                every <code>{plan_period}</code>. <br>
                Your internal PayPal subscription ID is <code>{sub_id}</code>.
            </p>
            '''
        else:
            return False, unsub_link, f'''
            <p>
                You are currently subscribed through PayPal. <br>
                Your internal PayPal subscription ID is <code>{sub_id}</code>.
            </p>
            '''

    elif sub['status'] == 'SUSPENDED':
        if plan_name:
            return False, unsub_link, f'''
            <p>
                Your subscription <code>{plan_name}</code> through PayPal is currently suspended. 
                You can either resolve this in PayPal, or cancel the subscription and create a new one. <br>
                Your internal PayPal subscription ID is <code>{sub_id}</code>.
            </p>
            '''
        else:
            return False, unsub_link, f'''
            <p>
                Your subscription through PayPal is currently suspended. 
                You can either resolve this in PayPal, or cancel the subscription and create a new one. <br>
                Your internal PayPal subscription ID is <code>{sub_id}</code>.
            </p>
            '''

    elif sub['status'] in ['CANCELLED', 'EXPIRED']:
        return True, None, ''

    elif sub['status'] in ['APPROVAL_PENDING', 'APPROVED']:
        logger.error(f'Got PayPal subscription in state {sub["status"]}')
        if plan_name:
            return False, unsub_link, f'''
            <p>
                Your subscription <code>{plan_name}</code> through PayPal is pending activation, and once activated
                will bill you <code>{plan_cost}</code> 
                every <code>{plan_period}</code>. <br>
                Your internal PayPal subscription ID is <code>{sub_id}</code>.
            </p>
            '''
        else:
            return False, unsub_link, f'''
            <p>
                Your subscription through PayPal is pending activation. <br>
                Your internal PayPal subscription ID is <code>{sub_id}</code>.
            </p>
            '''
    else:
        logger.error(f'Got PayPal subscription in state {sub["status"]}')
        return False, None, '<p>An unknown error occurred. Please be patient while this issue is investigated and resolved.</p>'


def check_stripe_subscription() -> Tuple[bool, Optional[str], str]:
    logger.info(f'Fetching Stripe subscription {session.user.stripe_subscription_id}')
    sub = stripe.Subscription.retrieve(session.user.stripe_subscription_id)
    logger.info(f'Got subscription with status: {sub.status}')

    print(sub)

    plan_name = f'OverTrack.gg {sub.plan.nickname or sub.plan.id}'

    unsub_link = url_for('subscribe.stripe_cancel')
    if sub.status == 'active':
        logger.info(f'Subscription cancel_at_period_end={sub.cancel_at_period_end}')
        if sub.cancel_at_period_end:
            return True, None, f'''
            <p>
                Your subscription has been canceled, and all sub-features will end at the end of the next billing period.
            </p>
            '''
        else:
            return False, unsub_link, f'''
            <p>
                You are currently subscribed to <code>{plan_name}</code> through Stripe (Credit Card), 
                which will bill you <code>${sub.plan.amount / 100}</code> 
                every <code>{sub.plan.interval_count} {sub.plan.interval}{"s" if sub.plan.interval_count > 1 else ""}</code>.
            </p>
            '''
    elif sub.status in ['past_due', 'unpaid']:
        return False, unsub_link, f'''
        <p>
            Your subscription is currently failing to complete - 
            please ensure that funds are available or cancel and recreate the subscription with a new billing method.
        </p>
        '''
    else:
        return True, None, ''


@subscribe_blueprint.route('/paypal_approved', methods=['POST'])
@require_login
@restrict_origin(whitelist=['apex.overtrack.gg'])
def paypal_approved():
    logger.info(f'Paypal subscription approved: {request.form}')

    try:
        sub = paypal_client.get_subscription_details(request.form['subscriptionID'])
    except:
        logger.exception('Failed to get PayPal subscription details')
        return Response(
            status=400,
            response='Subscription not found'
        )

    logger.info('Creating SubscriptionDetails record')
    SubscriptionDetails(
        user_id=session.user_id,
        version=2,
        type='paypal',
        subscription_id=request.form['subscriptionID'],
        full_data=request.form
    ).save()

    logger.info('Updating User model')
    # TODO: use set actions
    session.user.refresh()
    session.user.subscription_active = True
    session.user.subscription_type = 'v2.paypal'
    session.user.paypal_subscr_id = request.form['subscriptionID']
    session.user.paypal_payer_email = None
    session.user.paypal_payer_id = None
    session.user.paypal_subscr_date = None
    session.user.paypal_cancel_at_period_end = None

    plan_name = 'UNKNOWN'
    try:
        session.user.paypal_payer_email = sub['subscriber']['email_address']
        session.user.paypal_subscr_date = sub['create_time']
        session.user.paypal_cancel_at_period_end = not sub['auto_renewal']

        logger.info(f'Checking PayPal plan details')
        try:
            plan = paypal_client.get_plan_details(sub['plan_id'])
        except:
            logger.exception('Failed to fetch PayPal plan details')
        else:
            plan_name = plan['description']

    except:
        logger.exception('Failed to get PayPal subscription details')

    session.user.save()

    metrics.record('subscription.paypal.approved')
    metrics.event(
        'PayPal Subscription Created',
        f'User: {session.user_id} / {session.username}\n'
        f'Subscription ID: {session.user.paypal_subscr_id}\n'
        f'Payer Email: {session.user.paypal_payer_email}\n'
        f'Plan: {plan_name}',
        tags={
            'type': 'user-subscription'
        }
    )

    return Response(status=204)


@subscribe_blueprint.route('/paypal_cancel', methods=['POST'])
@require_login
@restrict_origin(whitelist=['apex.overtrack.gg'])
def paypal_cancel():
    session.user.refresh()
    logger.info(f'Canceling PayPal subscription {session.user.paypal_subscr_id}')

    paypal_client.cancel_subscription(session.user.paypal_subscr_id)

    logger.info('Updating SubscriptionDetails record')
    try:
        sub = SubscriptionDetails.subscription_id_index.get(session.user.paypal_subscr_id)
        sub.canceled_timestamp = time.time()
        sub.canceled_internally = True
        sub.save()
    except:
        logger.exception('Failed to update SubscriptionDetails for canceled subscription')

    metrics.record('subscription.paypal.canceled_internally')
    metrics.event(
        'PayPal Subscription Canceled',
        f'User: {session.user_id} / {session.username}\n'
        f'Subscription ID: {session.user.paypal_subscr_id}\n',
        tags={
            'type': 'user-subscription'
        }
    )

    return redirect(url_for('subscribe.subscribe'))


@subscribe_blueprint.route('/stripe_cancel', methods=['POST'])
@require_login
@restrict_origin(whitelist=['apex.overtrack.gg'])
def stripe_cancel():
    session.user.refresh()
    logger.info(f'Canceling Stripe subscription {session.user.stripe_subscription_id}')

    stripe.Subscription.modify(
        session.user.stripe_subscription_id,
        cancel_at_period_end=True
    )

    logger.info('Updating SubscriptionDetails record')
    try:
        sub = SubscriptionDetails.subscription_id_index.get(session.user.stripe_subscription_id)
        sub.canceled_timestamp = time.time()
        sub.canceled_internally = True
        sub.save()
    except:
        logger.exception('Failed to update SubscriptionDetails for canceled subscription')

    metrics.record('subscription.stripe.canceled_internally')
    metrics.event(
        'Stripe Subscription Canceled',
        f'User: {session.user_id} / {session.username}\n'
        f'Subscription ID: {session.user.stripe_subscription_id}\n',
        tags={
            'type': 'user-subscription'
        }
    )

    return redirect(url_for('subscribe.subscribe'))


def main() -> None:
    # sub = stripe.Subscription.retrieve('sub_FhpDwppGX8ujIg')
    #
    # print(sub)
    logging.basicConfig(level=logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True
    import http.client as http_client
    http_client.HTTPConnection.debuglevel = 1

    paypal_client = PayPal(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET)

    sub = paypal_client.get_subscription_details('I-1TJKASGV92Y9')
    pprint(sub)

    plan = paypal_client.get_plan_details(sub['plan_id'])
    pprint(plan)

    # try:
    #     sub = paypal_client.execute(PayPalGetSubscriptionDetails('I-B9DAGLLASSXX'))
    # except HttpError as e:
    #     pprint(e)


if __name__ == '__main__':
    main()
