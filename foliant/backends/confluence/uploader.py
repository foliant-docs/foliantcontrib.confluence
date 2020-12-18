import re
import os
import shutil
from pathlib import Path, PosixPath
from atlassian import Confluence
from foliant.preprocessors.utils.combined_options import Options

from .wrapper import Page
from .convert import (md_to_editor, process_images, post_process_ac_image,
                      editor_to_storage, add_comments, add_toc, set_up_logger,
                      unique_name, crop_title)
from .constants import REMOTE_ATTACHMENTS_DIR_NAME, ESCAPE_DIR_NAME


class BadParamsException(Exception):
    pass


class PageUploader:
    def __init__(
        self,
        md_file_path: str or PosixPath,
        config: Options,
        con: Confluence,
        cachedir: PosixPath,
        debug_dir: PosixPath,
        attachments_dir: PosixPath,
        logger
    ):
        self.md_file_path = Path(md_file_path)
        self.config = config
        self.con = con
        self.cachedir = cachedir
        self.debug_dir = debug_dir
        self.attachments_dir = attachments_dir
        self.logger = logger

        self.page = None
        set_up_logger(logger)

    def upload(self, content: str):
        title = self.config.get('title')
        parent_id = self._get_parent_id()

        self.page = Page(self.con,
                         self.config.get('space_key'),
                         title,
                         parent_id,
                         self.config.get('id'))

        new_content = content
        if self.config.get('nohead'):
            new_content = crop_title(new_content)
        new_content = md_to_editor(new_content, self.cachedir, self.config['pandoc_path'])

        self.logger.debug('Converting HTML to Confluence storage format')
        new_content = editor_to_storage(self.con, new_content)
        with open(self.cachedir / '2_storage.html', 'w') as f:
            f.write(new_content)
        new_content, attachments = process_images(new_content,
                                                  self.md_file_path.parent,
                                                  self.attachments_dir)
        if not self.config['test_run']:
            self.page.update_attachments(
                attachments,
                self.cachedir / REMOTE_ATTACHMENTS_DIR_NAME
            )
        new_content = self.confluence_unescape(new_content)

        if self.config['toc']:
            new_content = add_toc(new_content)

        with open(self.cachedir / '3_unescaped_with_images.html', 'w') as f:
            f.write(new_content)

        if self.config['restore_comments']:
            new_content = add_comments(self.page,
                                       new_content,
                                       self.config['resolve_if_changed'])

        need_update = self.page.need_update(new_content, title)
        with open(self.cachedir / '4_to_upload.html', 'w') as f:
            f.write(new_content)
        if need_update:
            self.logger.debug('Ready to upload. Content saved for debugging to '
                              f'{self.cachedir / "to_upload.html"}')
            minor_edit = not self.config['notify_watchers']
            if not self.config['test_run']:
                self.page.upload_content(new_content, title, minor_edit)
        else:
            self.logger.debug(f'Page with id {self.page.id} and title "{self.page.title}"'
                              " hadn't changed. Skipping.")

        self.backup_debug_info()

        if self.config['test_run']:
            return 'TEST RUN ' + ("* " * need_update) + '{host}/pages/viewpage.action?pageId={id} ({title})'\
                .format(host=self.config["host"].rstrip('/'), id=self.page.id, title=self.page.title)
        else:
            return ("* " * need_update) + '{host}/pages/viewpage.action?pageId={id} ({title})'\
                .format(host=self.config["host"].rstrip('/'), id=self.page.id, title=self.page.title)

    def _get_parent_id(self):
        parent_id = None
        if 'id' not in self.config:
            if 'parent_id' in self.config:
                parent_id = self.config['parent_id']
            elif 'parent_title' in self.config:
                self.logger.debug(
                    f'Trying to find parent id by space_key "{self.config.get("space_key")}"'
                    f' and title "{self.config["parent_title"]}"'
                )
                parent_id = get_content_id_by_title(self.con,
                                                    self.config['parent_title'],
                                                    self.config.get('space_key'),
                                                    self.config['test_run'])
                self.logger.debug(f'Found parent id: {parent_id}')

    def confluence_unescape(self, source: str) -> str:
        '''
        Unescape bits of raw confluene code, escaped by confluence_final preprocessor.

        `source` — source string, potentially containing escaped raw confluence code;
        # `escape_dir` — a directory, containing saved original escaped code.

        Returns a modified source string with all escaped raw confluence code restored.
        '''

        def _sub(match):
            filename = match.group('hash')
            self.logger.debug(f'Restoring escaped confluence code with hash {filename}')
            filepath = Path(escape_dir) / filename
            with open(filepath) as f:
                escaped_content = f.read()
                return self.post_process_escaped_content(escaped_content)
        escape_dir = self.cachedir / ESCAPE_DIR_NAME
        pattern = re.compile(r"\[confluence_escaped hash=\%(?P<hash>.+?)\%\]")
        return pattern.sub(_sub, source)

    def post_process_escaped_content(self, escaped_content: str):
        if escaped_content.lstrip().startswith('<ac:image'):
            result, attachments = post_process_ac_image(escaped_content, self.md_file_path, self.attachments_dir)
            if attachments and not self.config['test_run']:
                self.page.update_attachments(attachments,
                                             self.cachedir / REMOTE_ATTACHMENTS_DIR_NAME)
            return result
        else:
            return escaped_content

    def backup_debug_info(self):
        '''Copy debug files from the cachedir to debug dir'''
        _, _, files = next(os.walk(self.cachedir))
        for file in files:
            new_name = unique_name(self.debug_dir, file)
            shutil.move(self.cachedir / file, self.debug_dir / new_name)


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
