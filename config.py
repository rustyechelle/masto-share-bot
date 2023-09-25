import configparser
import os


class Config:
    def __init__(self, path):
        self.path = path

        self.config = None

    def create_config(self):
        config = configparser.ConfigParser()
        config.read(self.path)
        return config

    def get_config(self):
        if self.config is None:
            self.config = self.create_config()
        return self.config

    def get_evaluated(self, section, option):
        value = self.get_config().get(section, option)

        env_prefix = 'env:'
        if value.startswith(env_prefix):
            value = os.environ.get(value[len(env_prefix):])

        return value
