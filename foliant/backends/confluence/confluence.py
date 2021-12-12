import os
import shutil
import yaml

from getpass import getpass

from atlassian import Confluence
from requests.exceptions import HTTPError

from foliant.backends.base import BaseBackend
from foliant.contrib.combined_options import Options
from foliant.contrib.combined_options import val_type
from foliant.meta.generate import load_meta
from foliant.preprocessors import flatten
from foliant.preprocessors import unescapecode
from foliant.utils import output
from foliant.utils import spinner

from .constants import ATTACHMENTS_DIR_NAME
from .constants import CACHEDIR_NAME
from .constants import DEBUG_DIR_NAME
from .constants import ESCAPE_DIR_NAME
from .uploader import PageUploader

# disabling confluence logger because it litters up output
import atlassian.confluence

from unittest.mock import Mock
atlassian.confluence.log = Mock()


class Backend(BaseBackend):
    _flat_src_file_name = '__all__.md'

    targets = ('confluence')

    required_preprocessors_after = [
        'unescapecode',
        {
            'confluence_final': {
                'cachedir': CACHEDIR_NAME,
                'escapedir': ESCAPE_DIR_NAME
            }
        }
    ]

    defaults = {'mode': 'single',
                'toc': False,
                'pandoc_path': 'pandoc',
                'restore_comments': True,
                'resolve_if_changed': False,
                'notify_watchers': False,
                'test_run': False,
                'verify_ssl': True,
                'passfile': 'confluence_secrets.yml',
                'cloud': False}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._cachedir = (self.project_path / CACHEDIR_NAME).resolve()
        self._cachedir.mkdir(exist_ok=True)

        self._debug_dir = self._cachedir / DEBUG_DIR_NAME
        shutil.rmtree(self._debug_dir, ignore_errors=True)
        self._debug_dir.mkdir(exist_ok=True)

        self._flat_src_file_path = self._cachedir / self._flat_src_file_name
        self._attachments_dir = self._cachedir / ATTACHMENTS_DIR_NAME
        config = self.config.get('backend_config', {}).get('confluence', {})
        self.options = {**self.defaults, **config}
        self.options = Options(self.options, required=['host'])

        self.logger = self.logger.getChild('confluence')

        self.logger.debug(f'Backend inited: {self.__dict__}')

    def _get_options(self, *configs, fallback_title=None) -> Options:
        '''
        Get a list of dictionaries, all of which will be merged in one and
        transfered to an Options object with necessary checks.

        Returns the resulting Options object.
        '''
        options = {}
        if fallback_title:
            options['title'] = fallback_title
        for config in configs:
            options.update(config)
        options = Options(options,
                          validators={'host': val_type(str),
                                      'login': val_type(str),
                                      'password': val_type(str),
                                      'id': val_type([str, int]),
                                      'parent_id': val_type([str, int]),
                                      'title': val_type(str),
                                      'space_key': val_type(str),
                                      'pandoc_path': val_type(str),
                                      },
                          required=[('id',),
                                    ('space_key', 'title')])
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

    def _get_credentials(self, host: str) -> tuple:
        def get_password_for_login(login: str) -> str:
            if 'password' in self.options:
                return self.options['password']
            else:
                password = passdict.get(host.rstrip('/'), {}).get(login)
                if password:
                    return password
                else:
                    msg = '\n!!! User input required !!!\n'
                    msg += f"Please input password for {login}:\n"
                    return getpass(msg)
        self.logger.debug(f'Loading passfile {self.options["passfile"]}')
        if os.path.exists(self.options['passfile']):
            self.logger.debug(f'Found passfile at {self.options["passfile"]}')
            with open(self.options['passfile'], encoding='utf8') as f:
                passdict = yaml.load(f, yaml.Loader)
        else:
            passdict = {}
        if 'login' in self.options:
            login = self.options['login']
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

    def _build(self):
        '''
        Main method. Builds confluence XHTML document from flat md source and
        uploads it into the confluence server.
        '''
        host = self.options['host']
        credentials = self._get_credentials(host)
        self.logger.debug(f'Got credentials for host {host}: login {credentials[0]}, '
                          f'password {credentials[1]}')
        self._connect(host,
                      *credentials,
                      self.options['verify_ssl'])
        result = []
        if 'id' in self.options or ('title' in self.options and 'space_key' in self.options):
            self.logger.debug('Uploading flat project to confluence')
            output(f'Building main project', self.quiet)

            flatten.Preprocessor(
                self.context,
                self.logger,
                self.quiet,
                self.debug,
                {'flat_src_file_name': self._flat_src_file_name,
                 'keep_sources': True}
            ).apply()

            unescapecode.Preprocessor(
                self.context,
                self.logger,
                self.quiet,
                self.debug,
                {}
            ).apply()

            shutil.move(self.working_dir / self._flat_src_file_name,
                        self._flat_src_file_path)

            with open(self._flat_src_file_path, encoding='utf8') as f:
                md_source = f.read()

            options = self._get_options(self.options)

            self.logger.debug(f'Options: {options}')
            uploader = PageUploader(
                self._flat_src_file_path,
                options,
                self.con,
                self._cachedir,
                self._debug_dir,
                self._attachments_dir,
                self.logger
            )
            try:
                result.append(uploader.upload(md_source))
            except HTTPError as e:
                # reraising HTTPError with meaningful message
                raise HTTPError(e.response.text, e.response)

        self.logger.debug('Searching metadata for confluence properties')

        chapters = self.config['chapters']
        meta = load_meta(chapters, self.working_dir)
        for section in meta.iter_sections():

            if not isinstance(section.data.get('confluence'), dict):
                self.logger.debug(f'No "confluence" section in {section}), skipping.')
                continue

            self.logger.debug(f'Found "confluence" section in {section}), preparing to build.')
            # getting common options from foliant.yml and merging them with meta fields
            common_options = {}
            uncommon_options = ['title', 'id', 'space_key', 'parent_id', 'attachments']
            common_options = {k: v for k, v in self.options.items()
                              if k not in uncommon_options}
            try:
                options = self._get_options(common_options,
                                            section.data['confluence'],
                                            fallback_title=section.title)
            except Exception as e:
                # output(f'Skipping section {section}, wrong params: {e}', self.quiet)
                self.logger.debug(f'Skipping section {section}, wrong params: {e}')
                continue
            self.logger.debug(f'Building {section.chapter.filename}: {section.title}')
            output(f'Building {section.title}', self.quiet)
            md_source = section.get_source()

            self.logger.debug(f'Options: {options}')
            original_file = self.project_path / section.chapter.filename
            uploader = PageUploader(
                original_file,
                options,
                self.con,
                self._cachedir,
                self._debug_dir,
                self._attachments_dir,
                self.logger
            )
            try:
                result.append(uploader.upload(md_source))
            except HTTPError as e:
                # reraising HTTPError with meaningful message
                raise HTTPError(e.response.text, e.response)
        if result:
            return '\n' + '\n'.join(result)
        else:
            return 'nothing to upload'

    def make(self, target: str) -> str:
        with spinner(f'Making {target}', self.logger, self.quiet, self.debug):
            output('', self.quiet)  # empty line for better output
            try:
                if target == 'confluence':
                    return self._build()
                else:
                    raise ValueError(f'Confluence cannot make {target}')

            except Exception as exception:
                raise RuntimeError(f'Build failed: {exception}')
