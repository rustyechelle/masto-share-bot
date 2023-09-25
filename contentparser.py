# coding=utf-8

from html.parser import HTMLParser


class ContentParser(HTMLParser):

    def __init__(self, **kwargs):
        self.t = ''
        super().__init__(**kwargs)

    def handle_endtag(self, tag):
        if tag.lower() in ('p', 'div', 'br', 'h1', 'h2', 'h3'):
            self.t += '\n'

    def handle_data(self, data):
        self.t += data

    def get_content_text(self, content):
        self.reset()
        self.t = ''
        self.feed(content)
        return self.t

