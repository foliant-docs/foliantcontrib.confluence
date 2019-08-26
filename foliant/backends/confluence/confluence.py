import shutil
import re
import os

from subprocess import run, PIPE, STDOUT
from pathlib import Path, PosixPath
from getpass import getpass

from atlassian import Confluence

from foliant.utils import spinner, output
from foliant.backends.base import BaseBackend
from foliant.meta_commands.generate import generate_meta
from foliant.cli.meta.utils import get_processed
from foliant.preprocessors.utils.combined_options import (Options, val_type,
                                                          validate_in)
from .classes import Page
from .ref_diff import find_place, cut_out_tag_fragment, fix_refs, add_ref


SINGLE_MODE = 'single'
MULTIPLE_MODE = 'multiple'


class BadParamsException(Exception):
    pass


def unique_name(dest_dir: str or PosixPath, old_name: str) -> str:
    """
    Check if file with old_name exists in dest_dir. If it does —
    add incremental numbers until it doesn't.
    """
    counter = 1
    dest_path = Path(dest_dir)
    name = old_name
    while (dest_path / name).exists():
        counter += 1
        name = f'_{counter}'.join(os.path.splitext(old_name))
    return name


def editor_to_storage(con: Confluence, source: str):
    """
    Convert source string from confluence editor format to storage format
    and return it
    """
    data = {"value": source, "representation": "editor"}
    res = con.post('rest/api/contentbody/convert/storage', data=data)
    if res and 'value' in res:
        return res['value']
    else:
        raise RuntimeError('Cannot convert editor to storage. Got response:'
                           f'\n{res}')


def add_toc(source: str) -> str:
    """Add table of contents to the beginning of the page source"""
    result = '<ac:structured-macro ac:macro-id="1" '\
        'ac:name="toc" ac:schema-version="1"/>\n' + source
    return result


class Backend(BaseBackend):
    _flat_src_file_name = '__all__.md'

    targets = ('confluence')

    required_preprocessors_after = []

    defaults = {'mode': 'single',
                'toc': False, }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._flat_src_file_path = self.working_dir / self._flat_src_file_name
        self._cachedir = self.project_path / '.confluencecache'
        self._attachments_dir = self._cachedir / 'attachments'
        config = self.config.get('backend_config', {}).get('confluence', {})
        self.options = {**self.defaults, **config}

        # in single mode we use flat file, in multiple mode — working_dir
        if self.options['mode'] == 'single':
            self.required_preprocessors_after.\
                append({'flatten': {'flat_src_file_name': self._flat_src_file_name}})

        self.logger = self.logger.getChild('confluence')

        self.logger.debug(f'Backend inited: {self.__dict__}')

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

    def _prepare_cache_dir(self):
        """
        Create the cache dir (if it doesn't exist), cleanup the
        attachments dir or create it if it doesn't exist.
        """
        self.logger.debug(f'Creating and cleaning up cahce dir {self._cachedir}')
        self._cachedir.mkdir(exist_ok=True)

        # cleaning attachments
        shutil.rmtree(self._attachments_dir, ignore_errors=True)
        self._attachments_dir.mkdir()

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

    def _md_to_editor(self, con: Confluence, source: str):
        """
        Convert md source string to HTML with Pandoc, fix pandoc image tags,
        for confluence doesn't understand <figure> and <figcaption> tags.

        Return the resulting HTML string.
        """
        def _sub_image(match):
            """
            Convert image with pandoc <figcaption> tag into classic html image
            with caption in alt=""
            """
            image_caption = match.group('caption')
            image_path = match.group('path')
            result = f'<img src="{image_path}" alt="{image_caption}">'
            self.logger.debug(f'\nold: {match.group(0)}\nnew: {result}')
            return result
        md_source = self._cachedir / 'to_convert.md'
        converted = self._cachedir / 'converted.html'
        with open(md_source, 'w') as f:
            f.write(source)
        pandoc = self.options.get('pandoc_path', 'pandoc')
        command = f'{pandoc} {md_source} -f markdown -t html -o {converted}'

        self.logger.debug('Converting MD to HTML with Pandoc, command:\n' +
                          command)
        run(command, shell=True, check=True, stdout=PIPE, stderr=STDOUT)

        with open(converted) as f:
            result = f.read()

        self.logger.debug('Fixing pandoc image captions.')

        image_pattern = re.compile(r'<figure>\s*<img src="(?P<path>.+?)" +(?:alt=".*?")?.+?>(?:<figcaption>(?P<caption>.*?)</figcaption>)\s*</figure>')
        return image_pattern.sub(_sub_image, result)

    def process_images(self, source: str, filename: str or Path) -> str:
        """
        Copy local images to cache dir with unique names, replace their HTML
        definitions with confluence definitions
        """

        def _sub(image):
            image_caption = image.group('caption')
            image_path = image.group('path')

            # leave external images as is
            if image_path.startswith('http'):
                return image.group(0)

            image_path = Path(filename).parent / image_path

            self.logger.debug(f'Found image: {image.group(0)}')

            new_name = unique_name(self._attachments_dir,
                                   os.path.split(image_path)[1])
            new_path = self._attachments_dir / new_name

            self.logger.debug(f'Copying image into: {new_path}')
            shutil.copy(image_path, new_path)
            attachments.append(new_path)

            img_ref = f'<ac:image ac:title="{image_caption}"><ri:attachment ri:filename="{new_name}"/></ac:image>'

            self.logger.debug(f'Converted image ref: {img_ref}')
            return img_ref

        image_pattern = re.compile(r'<img src="(?P<path>.+?)" +(?:alt="(?P<caption>.*?)")?.+?>')
        attachments = []

        self.logger.debug('Processing images')

        return image_pattern.sub(_sub, source), attachments

    def add_comments(self, page: Page, new_content: str):
        '''
        Restore inline comments which were added to the page by users into
        the new_content.
        '''
        def collect_refs(source: str):
            refs = []
            open_refs = []
            while True:
                ref_s = re.search('<ac:inline-comment-marker\s+ac:ref="(.+?)">',
                                  source)
                ref_e = re.search('</ac:inline-comment-marker>', source)
                if (ref_s is None) and (ref_e is None):
                    break
                if (ref_s is not None) and (ref_s.start() < ref_e.start()):
                    self.logger.debug(f'Found comment: {ref_s.group(0)}')
                    open_refs.append((ref_s.group(1), ref_s.start()))
                    source = source[:ref_s.start()] +\
                        source[ref_s.end():]
                else:
                    refs.append((*open_refs.pop(), ref_e.start()))
                    source = source[:ref_e.start()] +\
                        source[ref_e.end():]
            return refs, source

        def restore_refs(refs: list, text: str) -> str:
            if not refs:
                return text
            result = ''
            for i in range(len(refs)):
                if i == 0:
                    result = text[:refs[i][1]]
                else:
                    result += text[refs[i - 1][2]:refs[i][1]]
                inner = text[refs[i][1]:refs[i][2]]
                result += add_ref(ref_id=refs[i][0], text=inner)
            result += text[refs[i][2]:]
            return result

        self.logger.debug('Restoring inline comments.')
        if not page.exists:
            return new_content

        self.logger.debug('Collecting comments from the old page.')
        refs, old_content = collect_refs(page.body)
        new_refs = []
        for ref in refs:
            span = find_place(old_content, new_content, ref[1], ref[2])
            span = cut_out_tag_fragment(new_content, *span)
            new_refs.append((ref[0], *span))
        new_refs = fix_refs(new_refs)
        return restore_refs(new_refs, new_content)

    def _upload(self,
                config: Options or dict,
                content: str,
                filename: str or Path):
        '''Upload one md-file to Confluence. Filename needed to fix the images'''
        id_ = config.get('id')
        space_key = config.get('space_key')
        title = config.get('title')
        parent_id = config.get('parent_id')
        page = Page(self.con, space_key, title, parent_id, id_)

        new_content = self._md_to_editor(self.con, content)

        self.logger.debug('Converting HTML to Confluence storage format')
        new_content = editor_to_storage(self.con, new_content)
        new_content, attachments = self.process_images(new_content, filename)
        new_content = self.add_comments(page, new_content)

        if config['toc']:
            new_content = add_toc(new_content)

        if attachments:
            # we can only upload attachments to existing page
            if not page.exists:
                self.logger.debug('Page does not exist. Creating an empty one '
                                  'to upload attachments')
                page.create_empty_page(title)
            else:
                self.logger.debug('Removing old attachments and adding new')
                page.delete_all_attachments()
            for img in attachments:
                page.upload_attachment(img)

        self.logger.debug(f'Content to update:\n\n{new_content}')
        page.upload_content(new_content, title)

        return '{host}/pages/viewpage.action?pageId={id} ({title})'\
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
                # folianttmp = self._cachedir / '__folianttmp__'
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
        with spinner(f'Making {target}\n', self.logger, self.quiet, self.debug):
            try:
                Options(self.options, required=['host'])
                self._prepare_cache_dir()
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
