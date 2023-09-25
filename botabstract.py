import apiclient
import config
import contentparser
import datetime
import dbm
import json
import logging
import re
import time

re_clear_mentions = re.compile(r'@\w+')


class BotAbstract:
    def __init__(self, identifier, cfg):
        # type: (str, config.Config) -> None
        self.identifier = identifier
        self.cfg = cfg

        self.logger = logging.getLogger(identifier)
        self.content_parser = contentparser.ContentParser()
        self.api = None
        self.users_db = None
        self.users = None
        self.status_db = None
        self.status = {}
        self.last_time_home_processing = 0
        self.last_time_notification_processing = 0
        self.registered_users = 0

    def create_api(self):
        logger_name = self.identifier + '.api'
        logger = logging.getLogger(logger_name)

        base_url = self.cfg.get_config().get(self.identifier, 'InstanceBaseUrl')
        api_key = self.cfg.get_evaluated(self.identifier, 'UserApiKey')
        persistent = self.cfg.get_config().getboolean(self.identifier, 'PersistentConnections', fallback=True)

        api = apiclient.ApiClient(logger=logger,
                                  persistent=persistent,
                                  base_url=base_url,
                                  api_key=api_key)
        return api

    def get_api(self):
        if self.api is None:
            self.api = self.create_api()
        return self.api

    def get_users_db_path(self):
        name = f'users.{self.identifier}.db'
        return name

    def load_users_db(self):
        self.users_db = dbm.open(self.get_users_db_path(), 'c')
        self.users = {}
        self.registered_users = 0

        self.logger.debug("Loading users db...")

        for k in self.users_db.keys():
            strk = str(k, 'utf-8')

            v = self.users_db[k]
            strv = str(v, 'utf-8')

            data = None
            try:
                data = json.loads(strv)
            except json.JSONDecodeError as e:
                pass

            if type(data) != dict:
                self.logger.error(f'Invalid user data {strk}: "{strv}", resetting')
                data = {}

            if data.get('boost'):
                self.registered_users += 1

            self.users[strk] = data

        self.logger.debug(f"Loading done, registered: {self.registered_users} / {len(self.users)}")

    def get_user_data(self, uri):
        if self.users_db is None or self.users is None:
            self.load_users_db()

        return self.users.get(uri, {})

    def save_user_data(self, uri, data):
        if type(data) != dict:
            raise Exception(f'Invalid user data ({type(data)})')

        if self.users_db is None or self.users is None:
            self.load_users_db()

        self.users[uri] = data

        ser_data = json.dumps(data)
        self.logger.debug(f'Saving user data {uri}: {ser_data}')
        self.users_db[uri] = ser_data

    def get_user_today_value(self):
        return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')

    def get_user_daily_use_count(self, user_data, use_identifier):
        today = self.get_user_today_value()
        use_data = user_data.get('use', {})
        if use_data.get('day') == today:
            count = use_data.get(use_identifier)
            if type(count) == int:
                return count
        return 0

    def set_user_daily_use_count(self, user_data, use_identifier, count):
        today = self.get_user_today_value()
        use_data = user_data.get('use', {})
        use_data['day'] = today
        use_data[use_identifier] = count
        user_data['use'] = use_data

    def get_status_db_path(self):
        name = f'status.{self.identifier}.db'
        return name

    def get_status_db(self):
        if self.status_db is None:
            self.status_db = dbm.open(self.get_status_db_path(), 'c')
        return self.status_db

    def get_status_value(self, key):
        if key in self.status:
            return self.status[key]
        self.status[key] = self.get_status_db().get(key)
        return self.status[key]

    def save_status_value(self, key, value):
        self.status[key] = value
        self.get_status_db()[key] = value

    def check_api_rate_limit(self):
        remaining = self.get_api().get_rate_limit_remaining()
        reset_date = self.get_api().get_rate_limit_reset_date()
        threshold = 50
        now = datetime.datetime.now(datetime.timezone.utc)
        if remaining is not None and reset_date and remaining < threshold and now < reset_date:
            self.logger.info(f'API rate limit almost reached ({remaining}), waiting {reset_date}')
            return False
        return True

    def process(self):
        pass

    def process_home(self):
        freq = self.cfg.get_config().getint(self.identifier, 'TimelineCheckFrequency')
        if time.time() > self.last_time_home_processing + freq:
            self.do_process_home()
            self.last_time_home_processing = time.time()

    def do_process_home(self):
        self.logger.debug("Processing home timeline...")

        last_home_status_id = self.get_status_value('last_home_id')
        if last_home_status_id:
            limit = 20
            query = {'min_id': last_home_status_id, 'limit': limit}
            while True:
                statuses = self.get_api().get_home_timeline(query)

                self.process_home_statuses(statuses)

                if len(statuses) < limit:
                    break

        else:
            limit = 10
            query = {'limit': limit}
            statuses = self.get_api().get_home_timeline(query)
            self.process_home_statuses(statuses)

    def process_home_statuses(self, statuses):
        last_status_id = None

        statuses.reverse()
        for status in statuses:
            self.process_home_status(status)
            last_status_id = status.get('id')

        if last_status_id:
            self.save_status_value('last_home_id', last_status_id)

    def process_home_status(self, status):
        self.logger.debug(f"Processing status {status.get('id')} ({status.get('account', {}).get('acct')})")

    def process_notifications(self):
        freq = self.cfg.get_config().getint(self.identifier, 'NotificationCheckFrequency')
        if time.time() > self.last_time_notification_processing + freq:
            self.do_process_notifications()
            self.last_time_notification_processing = time.time()

    def do_process_notifications(self):
        self.logger.debug("Processing notifications...")

        limit = 10
        query = {'limit': limit}
        while True:
            notifications = self.get_api().get_notifications(query)

            for n in notifications:
                self.process_notification(n)
                self.dismiss_notification(n)

            if len(notifications) < limit:
                break

    def process_notification(self, data):
        pass

    def dismiss_notification(self, data):
        notif_id = data['id']
        self.logger.info(f"Dismissing notification {notif_id} ({data.get('type')})")
        self.get_api().dismiss_notification(notif_id)

    def get_parent_status_safe(self, parent_status_id):
        try:
            return self.get_api().get_status(parent_status_id)
        except apiclient.StatusException as e:
            if e.get_status_code() in (401, 404):
                self.logger.warning(f"Failed to get parent status {parent_status_id} - {e}")
                return None
            raise e

    def check_user_daily_boost_count(self, uri, user_data):
        use = self.get_user_daily_use_count(user_data, 'boosts')
        boost_limit = self.cfg.get_config().getint(self.identifier, 'BoostLimit')
        if use >= boost_limit:
            self.logger.info(f"Boost limit reached {uri} - {use}/{boost_limit}")
            return -1
        return use

    def cancel_boost_parent(self, parent_status_id, user_uri):
        parent_status = self.get_parent_status_safe(parent_status_id)
        if not parent_status:
            return

        parent_user_uri = parent_status.get('account', {}).get('uri')
        if parent_user_uri != user_uri:
            return

        self.logger.info(f"Canceling boost {parent_status_id} (user {user_uri})")

        self.get_api().unreblog_status(parent_status_id)

    def register_command(self, user_uri, user_data, status):
        user_id = status.get('account', {}).get('id')
        if not user_id:
            return

        limit = self.cfg.get_config().getint(self.identifier, 'UserLimit')
        if self.registered_users > limit:
            self.logger.warning(f"User limit reached {limit}")
            return

        self.logger.info(f"Following user {user_uri}")
        self.get_api().follow_account(user_id)

        hashtags = []
        status_tags = status.get('tags', [])
        for tag in status_tags:
            tag_name = tag.get('name')
            if tag_name:
                hashtags.append(tag_name)

        user_data['boost'] = True
        user_data['hashtags'] = hashtags
        self.save_user_data(user_uri, user_data)
        self.registered_users += 1

    def stop_command(self, user_uri, user_data, status):
        user_id = status.get('account', {}).get('id')
        if not user_id:
            return

        self.logger.info(f"Unfollowing user {user_uri}")
        self.get_api().unfollow_account(user_id)

        user_data['boost'] = False
        self.save_user_data(user_uri, user_data)
        self.registered_users -= 1

    def has_status_hashtag(self, status, hashtags):
        status_tags = status.get('tags', [])
        if len(status_tags) > 0:
            if len(hashtags) == 0:
                return True  # empty list = any hashtags

            for tag in status_tags:
                tag_name = tag.get('name')
                if tag_name in hashtags:
                    return True

    def get_status_content(self, status):
        return self.content_parser.get_content_text(status.get('content'))

    def get_status_content_without_mentions(self, status):
        return re.sub(re_clear_mentions, '', self.get_status_content(status))

