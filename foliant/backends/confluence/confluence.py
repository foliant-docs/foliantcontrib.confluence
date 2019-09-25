from pathlib import Path
from getpass import getpass

from atlassian import Confluence

from foliant.utils import spinner, output
from foliant.backends.base import BaseBackend
from foliant.meta_commands.generate import generate_meta
from foliant.cli.meta.utils import get_processed
from foliant.preprocessors.utils.combined_options import (Options, val_type,
                                                          validate_in)

from .classes import Page
from .convert import (md_to_editor, process_images, confluence_unescape,
                      editor_to_storage, add_comments, add_toc, set_up_logger,
                      update_attachments)

# disabling confluence logger because it litters up output
from unittest.mock import Mock
import atlassian.confluence
atlassian.confluence.log = Mock()


SINGLE_MODE = 'single'
MULTIPLE_MODE = 'multiple'
CACHEDIR_NAME = '.confluencecache'
ATTACHMENTS_DIR_NAME = 'attachments'
ESCAPE_DIR_NAME = 'escaped'


class BadParamsException(Exception):
    pass


class Backend(BaseBackend):
    _flat_src_file_name = '__all__.md'

    targets = ('confluence')

    required_preprocessors_after = [{'confluence': {'cachedir': CACHEDIR_NAME,
                                                    'escapedir': ESCAPE_DIR_NAME}}]

    defaults = {'mode': 'single',
                'toc': False,
                'pandoc_path': 'pandoc',
                'restore_comments': True,
                'resolve_if_changed': False}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._flat_src_file_path = self.working_dir / self._flat_src_file_name
        self._cachedir = self.project_path / CACHEDIR_NAME
        self._cachedir.mkdir(exist_ok=True)
        self._attachments_dir = self._cachedir / ATTACHMENTS_DIR_NAME
        config = self.config.get('backend_config', {}).get('confluence', {})
        self.options = {**self.defaults, **config}

        # in single mode we use flat file, in multiple mode — working_dir
        if self.options['mode'] == 'single':
            self.required_preprocessors_after.\
                append({'flatten': {'flat_src_file_name': self._flat_src_file_name}})

        self.logger = self.logger.getChild('confluence')

        self.logger.debug(f'Backend inited: {self.__dict__}')
        set_up_logger(self.logger)

    def _get_options(self, config: dict) -> Options:
        '''
        Update backend options from foliant.yml with `config` dictionary,
        create an Options object with the necessary checks and return it.
        '''
        modes = [SINGLE_MODE, MULTIPLE_MODE]
        options = {**self.options, **config}
        options = Options(options,
                          validators={'host': val_type(str),
                                      'login': val_type(str),
                                      'password': val_type(str),
                                      'id': val_type([str, int]),
                                      'parent_id': val_type([str, int]),
                                      'title': val_type(str),
                                      'space_key': val_type(str),
                                      'pandoc_path': val_type(str),
                                      'mode': validate_in(modes), },
                          required=[('host', 'id',),
                                    ('host', 'title', 'space_key')])
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
        page = Page(self.con,
                    config.get('space_key'),
                    title,
                    config.get('parent_id'),
                    config.get('id'))

        new_content = md_to_editor(content, self._cachedir, config['pandoc_path'])

        self.logger.debug('Converting HTML to Confluence storage format')
        new_content = editor_to_storage(self.con, new_content)
        new_content, attachments = process_images(new_content,
                                                  Path(filename).parent,
                                                  self._attachments_dir)
        update_attachments(page, attachments, title)
        new_content = confluence_unescape(new_content, self._cachedir / ESCAPE_DIR_NAME)

        if config['toc']:
            new_content = add_toc(new_content)

        if config['restore_comments']:
            new_content = add_comments(page,
                                       new_content,
                                       config['resolve_if_changed'])

        need_update = page.need_update(new_content, title)
        if need_update:
            self.logger.debug(f'Content to update:\n\n{new_content}')
            page.upload_content(new_content, title)
        else:
            self.logger.debug(f'Page with id {page.id} and title "{page.title}"'
                              " hadn't changed. Skipping.")

        return ("* " * need_update) + '{host}/pages/viewpage.action?pageId={id} ({title})'\
            .format(host=config["host"].rstrip('/'), id=page.id, title=page.title)

    def _build(self):
        '''
        Main method. Builds confluence XHTML document from flat md source and
        uploads it into the confluence server.
        '''
        self._connect(self.options['host'],
                      self.options['login'],
                      self.options['password'])
        result = []
        if self.options['mode'] == SINGLE_MODE:
            self.logger.debug('Backernd runs in SINGLE mode')
            with open(self._flat_src_file_path, encoding='utf8') as f:
                md_source = f.read()
                # just to run the checks:
                options = self._get_options({})

                self.logger.debug(f'Options: {options}')
            result.append(self._upload(options, md_source, self._flat_src_file_path))
        elif self.options['mode'] == MULTIPLE_MODE:
            self.logger.debug('Backernd runs in MULTIPLE mode')
            meta = generate_meta(self.context, self.logger)
            for chapter in meta:

                if not chapter.yfm.get('confluence', False):
                    self.logger.debug(f'Skipping {chapter.name})')
                    continue

                self.logger.debug(f'Building {chapter.name}')
                output(f'Building {chapter.name}', self.quiet)
                md_source = get_processed(chapter, self.working_dir)
                options = self._get_options(chapter.yfm)

                self.logger.debug(f'Options: {options}')
                original_file = self.project_path / self.config['src_dir'] /\
                    chapter.name
                result.append(self._upload(options, md_source, original_file))
        if result:
            return '\n' + '\n'.join(result)
        else:
            return 'nothing to upload'

    def make(self, target: str) -> str:
        with spinner(f'Making {target}', self.logger, self.quiet, self.debug):
            output('', self.quiet)  # empty line for better output
            try:
                Options(self.options, required=['host'])
                if "login" not in self.options:
                    msg = f"Please input login for {self.options['host']}:\n"
                    msg = '\n!!! User input required !!!\n' + msg
                    self.options['login'] = input(msg)
                if "password" not in self.options:
                    msg = f"Please input password for {self.options['login']}:\n"
                    msg = '\n!!! User input required !!!\n' + msg
                    self.options['password'] = getpass(msg)
                if target == 'confluence':
                    return self._build()
                else:
                    raise ValueError(f'Confluence cannot make {target}')

            except Exception as exception:
                raise type(exception)(f'Build failed: {exception}')
