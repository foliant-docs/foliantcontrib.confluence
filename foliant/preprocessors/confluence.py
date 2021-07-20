'''Preprocessor which imports content from Confluence on place of <confluence> tags'''

import os
import re
import yaml

from getpass import getpass
from pathlib import Path
from pathlib import PosixPath
from subprocess import PIPE
from subprocess import STDOUT
from subprocess import run

from atlassian import Confluence
from bs4 import BeautifulSoup
from bs4 import Tag

from foliant.contrib.combined_options import CombinedOptions
from foliant.preprocessors.confluence_final.process import SYNTAX_CONVERT
from foliant.preprocessors.utils.preprocessor_ext import BasePreprocessorExt
from foliant.utils import output

from foliant.backends.confluence.wrapper import Page

IMG_DIR = '_confluence_attachments'
DEBUG_FILENAME = 'import_debug.html'


def process(page: Page, filename: str or PosixPath) -> str:
    result = download_images(page, filename)
    result = cleanup(result)
    return result


def download_images(page: Page, filename: str or PosixPath) -> BeautifulSoup:
    '''
    Download page attachments into subdir `IMG_DIR` near the filename,
    replace all confluence image tags with classic <img> tags referencing
    images in the `IMG_DIR` subdir.

    :param page:     Page object to be processed
    :param filename: path to current markdown file

    :returns: string with page HTML source code, where images are referencing
              files in the local IMG_DIR subfolder.
    '''

    img_dir = Path(filename).parent / IMG_DIR
    if not img_dir.exists():
        img_dir.mkdir()
    page.download_all_attachments(img_dir)
    soup = BeautifulSoup(page.body, 'html.parser')
    for img in soup.find_all(re.compile('ac:image')):
        title = img.attrs.get('ac:title', '')
        child = next(img.children)
        if child.name == 'ri:attachment':
            image_path = f'{IMG_DIR}/{child.attrs["ri:filename"]}'
        elif child.name == 'ri:url':
            image_path = child.attrs['ri:value']
        else:
            continue
        tag = Tag(name='img', attrs={'alt': title, 'src': image_path})
        img.replace_with(tag)
    return soup


def cleanup(source: BeautifulSoup) -> str:
    result = unwrap_tags(source)
    result = transform_tags(result)
    result = remove_tags(result)
    return str(result)


def unwrap_tags(source: BeautifulSoup) -> BeautifulSoup:
    tags_to_unwrap = ['ac:inline-comment-marker', 'span']

    for tag_name in tags_to_unwrap:
        for tag in source.find_all(re.compile(tag_name)):
            tag.unwrap()
    return source


def transform_tags(source: BeautifulSoup) -> BeautifulSoup:
    result = transform_code_blocks(source)
    return result


def transform_code_blocks(source: BeautifulSoup) -> BeautifulSoup:
    lang_dict = {v: k for k, v in SYNTAX_CONVERT.items()}

    for tag in source.find_all(
        re.compile('ac:structured-macro'),
        attrs={'ac:name': "code"}
    ):
        lang = ''
        body = ''
        for child in tag.children:
            if child.name == 'ac:parameter' and child.attrs['ac:name'] == 'language':
                lang = lang_dict.get(child.text.lower(), '')
            elif child.name == 'ac:plain-text-body':
                body = child.text
        if body:
            new_tag = Tag(name='pre', attrs={'class': lang})
            code = Tag(name='code')
            code.insert(0, body)
            new_tag.insert(0, code)
            tag.replace_with(new_tag)
    return source


def remove_tags(source: BeautifulSoup) -> BeautifulSoup:
    '''
    Remove all tags which start with "ac:" and their content from source.

    :param source: string with HTML code to be cleaned up.

    :returns: string with confluence tags removed.
    '''
    tags_to_remove = ['ac:.*']
    for tag_name in tags_to_remove:
        for tag in source.find_all(re.compile(tag_name)):
            tag.decompose()
    return source


class Preprocessor(BasePreprocessorExt):
    defaults = {
        'pandoc_path': 'pandoc',
        'cachedir': '.confluencecache',
        'verify_ssl': True,
        'passfile': 'confluence_secrets.yml'
    }
    tags = ('confluence',)

    def _get_config(self, tag_options: dict = {}) -> CombinedOptions:
        '''
        Get merged config from (decreasing priority):

        - tag options,
        - preprocessir options,
        - backend options.
        '''
        def filter_uncommon(val: dict) -> dict:
            uncommon_options = ['title', 'id']
            return {k: v for k, v in val.items()
                    if k not in uncommon_options}
        backend_config = self.config.get('backend_config', {}).get('confluence', {})
        options = CombinedOptions(
            {
                'tag': tag_options,
                'config': filter_uncommon(self.options),
                'backend_config': filter_uncommon(backend_config)
            },
            priority=['tag', 'config', 'backend_config'],
            required=[('host', 'id',), ('host', 'title', 'space_key')]
        )
        return options

    def _connect(self, host: str, login: str, password: str, verify_ssl: bool) -> Confluence:
        """Connect to Confluence server and test connection"""
        self.logger.debug(f'Trying to connect to confluence server at {host}')
        host = host.rstrip('/')
        self.con = Confluence(host, login, password, verify_ssl=verify_ssl)
        try:
            res = self.con.get('rest/api/space')
        except UnicodeEncodeError:
            raise RuntimeError('Sorry, non-ACSII passwords are not supported')
        if isinstance(res, str) or 'statusCode' in res:
            raise RuntimeError(f'Cannot connect to {host}:\n{res}')

    def _get_credentials(self, host: str, config: CombinedOptions) -> tuple:
        def get_password_for_login(login: str) -> str:
            if 'password' in config:
                return config['password']
            else:
                password = passdict.get(host.rstrip('/'), {}).get(login)
                if password:
                    return password
                else:
                    msg = '\n!!! User input required !!!\n'
                    msg += f"Please input password for {login}:\n"
                    return getpass(msg)
        self.logger.debug(f'Loading passfile {config["passfile"]}')
        if os.path.exists(config['passfile']):
            self.logger.debug(f'Found passfile at {config["passfile"]}')
            with open(config['passfile'], encoding='utf8') as f:
                passdict = yaml.load(f, yaml.Loader)
        else:
            passdict = {}
        if 'login' in config:
            login = config['login']
            password = get_password_for_login(login)
        else:  # login not in self.options
            host_dict = passdict.get(host, {})
            if host_dict:
                # getting first login from passdict
                login = next(iter(host_dict.keys()))
            else:
                msg = '\n!!! User input required !!!\n'
                msg += f"Please input login for {host}:\n"
                login = input(msg)
            password = get_password_for_login(login)
        return login, password

    def _import_from_confluence(self, match):
        tag_options = self.get_options(match.group('options'))
        config = self._get_config(tag_options)
        cachedir = Path(config['cachedir'])
        if not cachedir.exists():
            cachedir.mkdir(parents=True)
        host = config['host']
        credentials = self._get_credentials(host, config)
        self.logger.debug(f'Got credentials for host {host}: login {credentials[0]}, '
                          f'password {credentials[1]}')
        self._connect(host,
                      *credentials,
                      config['verify_ssl'])
        page = Page(self.con,
                    config.get('space_key'),
                    config.get('title'),
                    None,
                    config.get('id'))
        body = process(page, self.current_filepath)
        debug_filepath = cachedir / DEBUG_FILENAME
        with open(debug_filepath, 'w') as f:
            f.write(body)
        return self._convert_to_markdown(debug_filepath, config['pandoc_path'])

    def _convert_to_markdown(self,
                             source_path: str or PosixPath,
                             pandoc_path: str = 'pandoc') -> str:
        '''Convert HTML to Markdown with Pandoc'''
        command = f'{pandoc_path} -f html -t gfm {source_path}'
        self.logger.debug('Converting HTML to MD with Pandoc, command:\n' + command)
        p = run(command, shell=True, check=True, stdout=PIPE, stderr=STDOUT)
        return p.stdout.decode()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.logger = self.logger.getChild('confluence')

        self.logger.debug(f'Preprocessor inited: {self.__dict__}')

    def apply(self):
        output('', self.quiet)  # empty line for better output

        self._process_tags_for_all_files(self._import_from_confluence)
        self.logger.info(f'Preprocessor applied')
