import botabstract
import re

re_register_command = re.compile(r'\bboost\b')
re_stop_command = re.compile(r'\bstop\b')
re_cancel_command = re.compile(r'\bcancel\b')


class BotAutoShareTags(botabstract.BotAbstract):

    def process(self):
        if self.check_api_rate_limit():
            self.process_notifications()
            self.process_home()

    def process_notification(self, data):
        if data.get('type') != 'mention':
            return False

        status = data.get('status', {})
        parent_status_id = status.get('in_reply_to_id', None)
        text = self.get_status_content_without_mentions(status)

        user_uri = status.get('account', {}).get('uri')
        if type(user_uri) != str:
            return False

        user_data = self.get_user_data(user_uri)
        if user_data.get('blocked', False):
            return False

        if re_register_command.search(text):
            self.register_command(user_uri, user_data, status)
        elif re_stop_command.search(text):
            self.stop_command(user_uri, user_data, status)
        elif parent_status_id:
            if re_cancel_command.search(text):
                self.cancel_boost_parent(parent_status_id, user_uri)
            else:
                self.boost_parent(parent_status_id, user_uri, user_data)

    def boost_parent(self, parent_status_id, user_uri, user_data):

        use = self.check_user_daily_boost_count(user_uri, user_data)
        if use == -1:
            return

        parent_status = self.get_parent_status_safe(parent_status_id)
        if not parent_status:
            return

        # this bot is intended to increase public/indexable content on an instance
        # so boost only public posts in this bot
        if parent_status.get('visibility') != 'public':
            return

        parent_user_uri = parent_status.get('account', {}).get('uri')
        if parent_user_uri != user_uri:
            return

        self.logger.info(f"Boosting status {parent_status_id} (user {user_uri})")

        # no need to check if already reblogged: if already reblogged, does nothing and no error
        self.get_api().reblog_status(parent_status_id)

        use += 1
        self.set_user_daily_use_count(user_data, 'boosts', use)
        self.save_user_data(user_uri, user_data)

    def process_home_status(self, status):
        super().process_home_status(status)

        if status.get('visibility') != 'public':
            return

        status_id = status.get('id')
        user_uri = status.get('account', {}).get('uri')
        if type(user_uri) != str or not status_id:
            return

        user_data = self.get_user_data(user_uri)
        if user_data.get('blocked', False) or not user_data.get('boost', False):
            return

        if not self.has_status_hashtag(status, user_data.get('hashtags')):
            return

        use = self.check_user_daily_boost_count(user_uri, user_data)
        if use == -1:
            return

        self.logger.info(f"Boosting home status {status_id} (user {user_uri})")

        self.get_api().reblog_status(status_id)

        use += 1
        self.set_user_daily_use_count(user_data, 'boosts', use)
        self.save_user_data(user_uri, user_data)

