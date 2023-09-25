import datetime
import http.client
import json
import logging
import urllib.parse


class StatusException(Exception):
    def get_status_code(self):
        return self.args[1].status

    def get_response_json_object(self):
        value = self.args[2]
        if type(value) == dict:
            return value
        return {}


class UnexpectedResponseException(Exception):
    pass


class ApiClient:
    def __init__(self, logger, base_url, api_key, persistent=None):
        self.logger = logger  # type: logging.Logger
        self.base_url = base_url
        self.api_key = api_key
        self.persistent = persistent

        self.conn = None
        self.rate_limit_remaining = None
        self.rate_limit_reset_date = None

    def create_conn(self):
        o = urllib.parse.urlparse(self.base_url)
        c = http.client.HTTPSConnection(o.netloc)
        return c

    def get_conn(self):
        if self.conn is None:
            self.conn = self.create_conn()
        return self.conn

    def get_home_timeline(self, params=None):
        path = '/api/v1/timelines/home'
        r, data = self.request('GET', path, params)
        self.check_response_status(r, data)
        return self.get_check_response_json_list(r, data)

    def get_status(self, status_id):
        path = f'/api/v1/statuses/{int(status_id)}'
        r, data = self.request('GET', path)
        self.check_response_status(r, data)
        return self.get_check_response_json_dict(r, data)

    def reblog_status(self, status_id):
        path = f'/api/v1/statuses/{int(status_id)}/reblog'
        r, data = self.request('POST', path)
        self.check_response_status(r, data)

    def unreblog_status(self, status_id):
        path = f'/api/v1/statuses/{int(status_id)}/unreblog'
        r, data = self.request('POST', path)
        self.check_response_status(r, data)

    def delete_status(self, status_id):
        path = f'/api/v1/statuses/{int(status_id)}'
        r, data = self.request('DELETE', path)
        self.check_response_status(r, data)

    def get_notifications(self, params=None):
        path = '/api/v1/notifications'
        r, data = self.request('GET', path, params)
        self.check_response_status(r, data)
        return self.get_check_response_json_list(r, data)

    def dismiss_notification(self, notification_id):
        path = f'/api/v1/notifications/{int(notification_id)}/dismiss'
        r, data = self.request('POST', path)
        self.check_response_status(r, data)

    def follow_account(self, account_id):
        path = f'/api/v1/accounts/{int(account_id)}/follow'
        r, data = self.request('POST', path)
        self.check_response_status(r, data)

    def unfollow_account(self, account_id):
        path = f'/api/v1/accounts/{int(account_id)}/unfollow'
        r, data = self.request('POST', path)
        self.check_response_status(r, data)


    def check_response_status(self, response, data_bytes):
        if response.status != 200:
            raise StatusException(f'Invalid response status', response, self.get_response_json_safe(data_bytes))

    def get_check_response_json(self, response, data_bytes):
        ct = response.getheader('content-type')  # type: str
        if not ct or ct.lower().find('application/json') == -1 or ct.lower().find('utf-8') == -1:
            raise UnexpectedResponseException(f'Unexpected content-type ({ct})')

        if type(data_bytes) != bytes or len(data_bytes) == 0:
            raise UnexpectedResponseException(f'Empty response data')

        try:
            content = str(data_bytes, 'utf-8')
        except UnicodeDecodeError as e:
            raise UnexpectedResponseException(f'Invalid utf-8 response', data_bytes) from e

        try:
            data = json.loads(content)
        except json.decoder.JSONDecodeError as e:
            raise UnexpectedResponseException(f'Failed to decode json response', content) from e

        return data

    def get_response_json_safe(self, data_bytes):
        if type(data_bytes) == bytes and data_bytes != b'':
            try:
                content = str(data_bytes, 'utf-8')
                return json.loads(content)
            except Exception:
                pass

        return None

    def get_check_response_json_dict(self, response, data_bytes):
        data = self.get_check_response_json(response, data_bytes)
        if type(data) != dict:
            raise UnexpectedResponseException(f'Response is not an object ({type(data)})')

        return data

    def get_check_response_json_list(self, response, data_bytes):
        data = self.get_check_response_json(response, data_bytes)
        if type(data) != list:
            raise UnexpectedResponseException(f'Response is not a list ({type(data)})')

        return data

    def request(self, method, path, query=None, body=None, headers=None):
        final_path = path
        if query is not None:
            final_path += '?' + urllib.parse.urlencode(query)

        final_headers = {'Authorization': 'Bearer ' + self.api_key}
        if headers is not None:
            final_headers.update(headers)

        json_body = None
        if body is not None:
            json_body = json.dumps(body)
            headers['Content-Type'] = 'application/json'

        self.logger.debug(f'REQUEST {method} {final_path}')
        # self.logger.debug(f'{final_headers}')

        c = None
        try:
            c = self.get_conn()
            c.request(method, final_path, json_body, final_headers)
            r = c.getresponse()
            self.logger.debug(f'RESPONSE "{r.reason}" ({r.status})')

            data = r.read()

            # self.logger.debug(f'headers: {r.getheaders()}')
            # self.logger.debug(f'body: "{data}"')

            self.handle_rate_limit(r)

            return r, data
        finally:
            if not self.persistent and c is not None:
                c.close()

    def handle_rate_limit(self, response):
        # type: (http.client.HTTPResponse) -> None

        limit = get_value_int(response.getheader('x-ratelimit-limit'))
        remaining = get_value_int(response.getheader('x-ratelimit-remaining'))
        reset = response.getheader('x-ratelimit-reset')

        # self.logger.debug(f'rate limit {remaining}/{limit} - {reset}')

        if remaining is not None:
            if remaining < 5:
                self.logger.warning(f'API RATE LIMIT ALERT ({remaining}/{limit} - {reset}')

            self.rate_limit_remaining = remaining

        if reset:
            self.rate_limit_reset_date = get_rate_limit_date(reset)


    def get_rate_limit_remaining(self):
        return self.rate_limit_remaining

    def get_rate_limit_reset_date(self):
        return self.rate_limit_reset_date


def get_value_int(value):
    if value is not None:
        try:
            return int(value)
        except (ValueError, TypeError):
            pass
    return None


def get_rate_limit_date(value):
    # type: (str) -> datetime.datetime | None
    if value is not None:
        try:
            # "Z" not supported in python 3.10
            if value.endswith('Z'):
                value = value[:-1] + '+00:00'
            return datetime.datetime.fromisoformat(value)
        except ValueError:
            pass
    return None
