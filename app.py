import botautosharetags
import config
import logging.config
import signal
import time

bot_type_mapping = {
    'AutoShareTags': botautosharetags.BotAutoShareTags
}

exit_flag = False


def interrupt_handler(signum, frame):
    global exit_flag
    exit_flag = True


class App:
    def __init__(self, config_path='config.ini', logging_config_path='logging.conf'):
        self.config_path = config_path
        self.logging_config_path = logging_config_path

        self.bots = {}
        self.logging_bootstrapped = False
        self.config = None

    def bootstrap_logging(self):
        if not self.logging_bootstrapped:
            logging.config.fileConfig(self.logging_config_path)
            self.logging_bootstrapped = True

    def get_logger(self, name=None):
        self.bootstrap_logging()
        return logging.getLogger(name)

    def get_config(self):
        if not self.config:
            self.config = config.Config(self.config_path)
        return self.config

    def create_bot(self, identifier):
        bot_type = self.get_config().get_config().get(identifier, 'Type')
        cls = bot_type_mapping.get(bot_type)
        if not cls:
            raise Exception(f"Invalid bot type '{bot_type}'")

        self.bootstrap_logging()
        return cls(identifier, self.get_config())

    def add_bot(self, identifier):
        if identifier not in self.bots:
            self.bots[identifier] = None

    def get_bot(self, identifier):
        bot = self.bots[identifier]
        if not bot:
            bot = self.create_bot(identifier)
            self.bots[identifier] = bot
        return bot

    def get_bot_identifiers(self):
        return self.bots.keys()

    def process_loop(self):
        signal.signal(signal.SIGINT, interrupt_handler)
        signal.signal(signal.SIGTERM, interrupt_handler)

        self.get_logger().info("Starting process loop...")

        while not exit_flag:
            self.process_bots()

            time.sleep(1)

        self.get_logger().info("Exit requested")

    def process_bots(self):
        for identifier in self.get_bot_identifiers():
            self.get_bot(identifier).process()
