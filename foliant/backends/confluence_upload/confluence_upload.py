import shutil
import re
import os

from subprocess import run, PIPE, STDOUT
from pathlib import Path, PosixPath

from confluence.client import Confluence

from foliant.utils import spinner
from foliant.backends.base import BaseBackend
from .classes import Page
from .ref_diff import find_place, cut_out_tag_fragment, fix_refs, add_ref


def unique_name(dest_dir: str or PosixPath, old_name: str) -> str:
    """
    Checks if file with old_name exists in dest_dir, if it does:
    adds incremental numbers until it doesn't.
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
    return con._post('contentbody/convert/storage', {}, data).json()['value']


class Backend(BaseBackend):
    _flat_src_file_name = '__all__.md'

    targets = ('confluence')

    required_preprocessors_after = {
        'flatten': {
            'flat_src_file_name': _flat_src_file_name
        }
    },

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._flat_src_file_path = self.working_dir / self._flat_src_file_name
        self._confluence_config = self.config.get('backend_config', {}).get('confluence_upload', {})
        self._cachedir = self.project_path / '.confluencecache'
        self._attachments_dir = self._cachedir / 'attachments'

        self.logger = self.logger.getChild('confluence_upload')

        self.logger.debug(f'Backend inited: {self.__dict__}')

    def _prepare_cache_dir(self):
        """Create a clean cache dir (old one is destroyed)"""
        shutil.rmtree(self._cachedir, ignore_errors=True)  # cleaning docs
        self._cachedir.mkdir()
        self._attachments_dir.mkdir()

    def _connect(self, host: str, login: str, password: str) -> Confluence:
        """Convert source Markdown string into Confluence html and return it"""
        self.con = Confluence(host.rstrip('/'), (login, password))

    def _md_to_editor(self, con: Confluence, source: str):
        """convert md source string to confluence editor format and return it"""
        def _sub_image(match):
            image_caption = match.group('caption')
            image_path = match.group('path')
            return f'<img src="{image_path}" alt="{image_caption}">'
        md_source = self._cachedir / '__all__.md'
        converted = self._cachedir / 'converted.html'
        with open(md_source, 'w') as f:
            f.write(source)
        command = f'pandoc {md_source} -f markdown -t html -o {converted}'

        run(command, shell=True, check=True, stdout=PIPE, stderr=STDOUT)

        with open(converted) as f:
            result = f.read()

        # fixing images
        image_pattern = re.compile(r'<img src="(?P<path>.+?)" +(?:alt=".*?")?.+?>(?:<figcaption>(?P<caption>.*?)</figcaption>)')
        return image_pattern.sub(_sub_image, result)
        # data = {'wiki': source}
        # return con._post(path='/rest/tinymce/1/markdownxhtmlconverter', data=data, params={}).text
        # return markdown(source)

    def process_images(self, source: str) -> str:
        """
        Copy local images to cache dir with unique names, replace their MD
        definitions with confluence definitions
        """

        def _sub(image):
            image_caption = image.group('caption')
            image_path = image.group('path')

            # leave external images as is
            if image_path.startswith('http'):
                return image.group(0)

            new_name = unique_name(self._attachments_dir,
                                   os.path.split(image_path)[1])
            new_path = self._attachments_dir / new_name
            shutil.copy(image_path, new_path)
            attachments.append(new_path)

            img_ref = f'<ac:image ac:title="{image_caption}"><ri:attachment ri:filename="{new_name}"/></ac:image>'
            return img_ref
        # image_pattern = re.compile(r'\!\[(?P<caption>.*)\]\((?P<path>((?!:\/\/).)+)\)')
        image_pattern = re.compile(r'<img src="(?P<path>.+?)" +(?:alt="(?P<caption>.*?)")?.+?>')
        attachments = []
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
        if not page.exists:
            return new_content
        refs, old_content = collect_refs(page.content.body.storage)
        new_refs = []
        for ref in refs:
            span = find_place(old_content, new_content, ref[1], ref[2])
            span = cut_out_tag_fragment(new_content, *span)
            new_refs.append((ref[0], *span))
        new_refs = fix_refs(new_refs)
        return restore_refs(new_refs, new_content)

    def _upload_article(self,
                        source: str,
                        id_: int or None = None,
                        space_key: str or None = None,
                        title: str or None = None,
                        parent_id: int or None = None):
        '''Upload one article'''
        page = Page(self.con, space_key, title, parent_id, id_)

        new_content = self._md_to_editor(self.con, source)
        new_content = editor_to_storage(self.con, new_content)
        new_content, attachments = self.process_images(new_content)
        new_content = self.add_comments(page, new_content)
        self.logger.debug(f'Content to update:\n\n{new_content}')
        page.upload_content(new_content, title)
        page.delete_all_attachments()
        for img in attachments:
            page.upload_attachment(img)
        return page.id

    def _build_and_upload(self):
        '''
        Main method. Builds confluence XHTML document from flat md source and
        uploads it into the confluence server
        '''
        config = self._confluence_config
        self._connect(config['host'],
                      config['login'],
                      config['password'])
        with open(self._flat_src_file_path, encoding='utf8') as f:
            md_source = f.read()
        id_ = config.get('id')
        space_key = config.get('space_key')
        title = config.get('title')
        parent_id = config.get('parent_id')
        id_ = self._upload_article(md_source, id_, space_key, title, parent_id)

        return '{host}/pages/viewpage.action?pageId={id}'\
            .format(host=config["host"].rstrip('/'), id=id_)

    def make(self, target: str) -> str:
        with spinner(f'Making {target}', self.logger, self.quiet, self.debug):
            try:
                self._prepare_cache_dir()
                if target == 'confluence':
                    return self._build_and_upload()
                else:
                    raise ValueError(f'Confluence cannot make {target}')

            except Exception as exception:
                raise type(exception)(f'Build failed: {exception}')
