from typing import Dict

import requests
import time
from requests.auth import HTTPBasicAuth
from stripe.http_client import requests


class PayPal:

    def __init__(self, client_id: str, client_secret: str, sandbox: bool = True):
        self.client_id = client_id
        self.client_secret = client_secret
        if sandbox:
            self.endpoint = 'https://api.sandbox.paypal.com'
        else:
            self.endpoint = 'https://api.paypal.com'

        self.session = requests.Session()

        self._refresh_token()

    def _refresh_token(self) -> None:
        r = self.session.post(
            self.endpoint + '/v1/oauth2/token',
            auth=HTTPBasicAuth(self.client_id, self.client_secret),
            data={'grant_type': 'client_credentials'}
        )
        r.raise_for_status()

        json = r.json()
        self.token = json['access_token']
        self.token_expiry = time.time() - (json['expires_in'] + 30)

    def _check_token(self) -> None:
        if time.time() > self.token_expiry:
            self._refresh_token()

    def _make_request(self, path: str, verb: str = 'GET') -> Dict:
        self._check_token()
        r = self.session.request(verb, self.endpoint + path, headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.token
        })
        r.raise_for_status()
        if r.status_code == 200:
            return r.json()
        else:
            return {}

    def get_subscription_details(self, subscription_id: str) -> Dict:
        return self._make_request(f'/v1/billing/subscriptions/{subscription_id}')

    def cancel_subscription(self, subscription_id: str) -> Dict:
        return self._make_request(f'/v1/billing/subscriptions/{subscription_id}/cancel', verb='POST')

    def get_plan_details(self, plan_id: str) -> Dict:
        return self._make_request(f'/v1/billing/plans/{plan_id}')
