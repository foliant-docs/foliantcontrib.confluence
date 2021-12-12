import os
import re
import shutil

from atlassian import Confluence
from foliant.contrib.combined_options import Options
from pathlib import Path
from pathlib import PosixPath

from .constants import ESCAPE_DIR_NAME
from .constants import REMOTE_ATTACHMENTS_DIR_NAME
from .convert import add_comments
from .convert import add_toc
from .convert import copy_with_unique_name
from .convert import crop_title
from .convert import editor_to_storage
from .convert import md_to_editor
from .convert import post_process_ac_image
from .convert import post_process_ac_link
from .convert import process_images
from .convert import unformat
from .convert import set_up_logger
from .convert import unique_name
from .wrapper import Page


class BadParamsException(Exception):
    pass


class AttachmentManager:
    def __init__(
        self,
        store_dir: PosixPath,
        logger
    ):
        self.dir = store_dir
        self.logger = logger
        self.registry = {}
        self.cleanup()

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir()

    def add_attachment(self, file_path: str or PosixPath) -> PosixPath or None:
        abs_path = str(Path(file_path).resolve())
        self.logger.debug(f'Adding attachment: {abs_path}')

        if abs_path in self.registry:
            self.logger.debug(f'Attachment found in registry, returning {self.registry[abs_path]}')
            return self.registry[abs_path]
        else:
            new_path = copy_with_unique_name(self.dir, file_path)
            if new_path:
                self.registry[abs_path] = new_path
            self.logger.debug(f'Copied to attachments dir, returning {new_path}')
            return new_path  # may be None

    @property
    def attachments(self):
        return list(self.registry.values())


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
        self.attachment_manager = AttachmentManager(attachments_dir, logger)
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
        new_content = process_images(new_content,
                                     self.md_file_path.parent,
                                     self.attachment_manager)

        new_content = self.confluence_unescape(new_content, self.attachment_manager)
        # attachments.extend(new_attachments)

        for att in self.config.get('attachments', []):
            att_path = self.attachment_manager.add_attachment(att)
            if not att_path:
                self.logger.warning(f'Attachment {att} does not exist, skipping')
            # else:
            #     attachments.append(att_path)

        if not self.config['test_run']:
            self.page.update_attachments(
                self.attachment_manager.attachments,
                self.cachedir / REMOTE_ATTACHMENTS_DIR_NAME
            )

        if self.config['toc']:
            new_content = add_toc(new_content)

        with open(self.cachedir / '3_unescaped_with_images.html', 'w') as f:
            f.write(new_content)

        if self.config['restore_comments']:
            new_content = add_comments(self.page,
                                       new_content,
                                       self.config['resolve_if_changed'])

        if self.config['cloud']:
            new_content = unformat(new_content)
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
            return 'TEST RUN ' + ("* " * need_update) + '{url} ({title})'\
                .format(url=self.page.url, title=self.page.title)
        else:
            return ("* " * need_update) + '{url} ({title})'\
                .format(url=self.page.url, title=self.page.title)

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
        return parent_id

    def confluence_unescape(self, source: str, attachment_manager: AttachmentManager) -> str:
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
                result = self.post_process_escaped_content(escaped_content, attachment_manager)
                # attachments.extend(new_attachments)
                return result
        # attachments = []
        escape_dir = self.cachedir / ESCAPE_DIR_NAME
        pattern = re.compile(r"\[confluence_escaped hash=\%(?P<hash>.+?)\%\]")
        return pattern.sub(_sub, source)

    def post_process_escaped_content(self, escaped_content: str, attachment_manager: AttachmentManager):
        if escaped_content.lstrip().startswith('<ac:image'):
            return post_process_ac_image(escaped_content, self.md_file_path, attachment_manager)

        elif escaped_content.lstrip().startswith('<ac:link'):
            return post_process_ac_link(escaped_content, self.md_file_path, attachment_manager)
            # if attachments and not self.config['test_run']:
            #     self.page.update_attachments(attachments,
            #                                  self.cachedir / REMOTE_ATTACHMENTS_DIR_NAME)
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
