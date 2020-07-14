import shutil
import os
import yaml

from pathlib import Path
from getpass import getpass

from atlassian import Confluence
from requests.exceptions import HTTPError

from foliant.utils import spinner, output
from foliant.backends.base import BaseBackend
from foliant.meta.generate import load_meta
from foliant.preprocessors import flatten, unescapecode
from foliant.preprocessors.utils.combined_options import (Options, val_type)

from .classes import Page
from .convert import (md_to_editor, process_images, confluence_unescape,
                      editor_to_storage, add_comments, add_toc, set_up_logger,
                      update_attachments, unique_name, crop_title)

# disabling confluence logger because it litters up output
from unittest.mock import Mock
import atlassian.confluence
atlassian.confluence.log = Mock()


CACHEDIR_NAME = '.confluencecache'
ATTACHMENTS_DIR_NAME = 'attachments'
ESCAPE_DIR_NAME = 'escaped'
DEBUG_DIR_NAME = 'debug'
REMOTE_ATTACHMENTS_DIR_NAME = 'remote_attachments'


class BadParamsException(Exception):
    pass


def get_content_id_by_title(con: Confluence,
                            title: str,
                            space_key: str,
                            test_run: bool):
    if not space_key:
        raise BadParamsException('You have to add space_key if you specify '
                                 'parent by title!')
    p = con.get_page_by_title(space_key, title)
    if p and 'id' in p:
        return p['id']
    elif test_run:
        return None
    else:
        raise BadParamsException(f'Cannot find parent with title {title}')


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
                'passfile': 'confluence_secrets.yml'}

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
        set_up_logger(self.logger)

    def backup_debug_info(self):
        '''Copy debug files from the cachedir to debug dir'''
        _, _, files = next(os.walk(self._cachedir))
        for file in files:
            new_name = unique_name(self._debug_dir, file)
            shutil.move(self._cachedir / file, self._debug_dir / new_name)

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

    def _connect(self, host: str, login: str, password: str) -> Confluence:
        """Connect to Confluence server and test connection"""
        self.logger.debug(f'Trying to connect to confluence server at {host}')
        host = host.rstrip('/')
        self.con = Confluence(host, login, password)
        try:
            res = self.con.get('rest/api/space')
        except UnicodeEncodeError:
            raise RuntimeError('Sorry, non-ACSII passwords are not supported')
        if isinstance(res, str) or 'statusCode' in res:
            raise RuntimeError(f'Cannot connect to {host}:\n{res}')

    def _upload(self,
                config: Options or dict,
                content: str,
                filename: str or Path):
        '''Upload one md-file to Confluence. Filename needed to fix the images'''
        title = config.get('title')
        parent_id = None
        if 'id' not in config:
            if 'parent_id' in config:
                parent_id = config['parent_id']
            elif 'parent_title' in config:
                self.logger.debug(
                    f'Trying to find parent id by space_key "{config.get("space_key")}"'
                    f' and title "{config["parent_title"]}"'
                )
                parent_id = get_content_id_by_title(self.con,
                                                    config['parent_title'],
                                                    config.get('space_key'),
                                                    config['test_run'])
                self.logger.debug(f'Found parent id: {parent_id}')

        page = Page(self.con,
                    config.get('space_key'),
                    title,
                    parent_id,
                    config.get('id'))

        if config.get('nohead'):
            content = crop_title(content)
        new_content = md_to_editor(content, self._cachedir, config['pandoc_path'])

        self.logger.debug('Converting HTML to Confluence storage format')
        new_content = editor_to_storage(self.con, new_content)
        with open(self._cachedir / '2_storage.html', 'w') as f:
            f.write(new_content)
        new_content, attachments = process_images(new_content,
                                                  Path(filename).parent,
                                                  self._attachments_dir)
        if not config['test_run']:
            update_attachments(page,
                               attachments,
                               self._cachedir / REMOTE_ATTACHMENTS_DIR_NAME)
        new_content = confluence_unescape(new_content, self._cachedir / ESCAPE_DIR_NAME)

        if config['toc']:
            new_content = add_toc(new_content)

        with open(self._cachedir / '3_unescaped_with_images.html', 'w') as f:
            f.write(new_content)

        if config['restore_comments']:
            new_content = add_comments(page,
                                       new_content,
                                       config['resolve_if_changed'])

        need_update = page.need_update(new_content, title)
        with open(self._cachedir / '4_to_upload.html', 'w') as f:
            f.write(new_content)
        if need_update:
            self.logger.debug('Ready to upload. Content saved for debugging to '
                              f'{self._cachedir / "to_upload.html"}')
            minor_edit = not config['notify_watchers']
            if not config['test_run']:
                page.upload_content(new_content, title, minor_edit)
        else:
            self.logger.debug(f'Page with id {page.id} and title "{page.title}"'
                              " hadn't changed. Skipping.")

        self.backup_debug_info()

        if config['test_run']:
            return 'TEST RUN ' + ("* " * need_update) + '{host}/pages/viewpage.action?pageId={id} ({title})'\
                .format(host=config["host"].rstrip('/'), id=page.id, title=page.title)
        else:
            return ("* " * need_update) + '{host}/pages/viewpage.action?pageId={id} ({title})'\
                .format(host=config["host"].rstrip('/'), id=page.id, title=page.title)

    def _get_credentials(self, host: str) -> tuple:
        def get_password_for_login(login: str) -> str:
            if 'password' in self.options:
                return self.options['password']
            else:
                password = passdict.get(host, {}).get(login)
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
                      *credentials)
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
            try:
                result.append(self._upload(options, md_source, self._flat_src_file_path))
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
            uncommon_options = ['title', 'id', 'space_key', 'parent_id']
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
            try:
                result.append(self._upload(options, md_source, original_file))
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
