'''
Technical preprocessor which prepares markdown files for being transfered to the
Confluence backend.
'''

import shutil
from hashlib import md5

from foliant.preprocessors.utils.preprocessor_ext import BasePreprocessorExt
from foliant.meta.generate import load_meta

from .process import process_code_blocks, process_task_lists


# global logger. After Peprocessor init will be overridden with preprocessor logger


class Preprocessor(BasePreprocessorExt):
    defaults = {'cachedir': '.confluencecache',
                'escapedir': 'escaped'}
    tags = ('raw_confluence',)

    def _process_content(self, content: str) -> str:
        processed = self._process_code_blocks(content)
        processed = process_task_lists(processed)

        return processed

    def _process_code_blocks(self, content: str) -> str:
        config = self.backend_config.get('codeblocks', {})
        chapter = None
        if self.current_filename in self.config.get('chapters', []):
            chapter = self.meta.get_chapter(self.current_filepath)
        return process_code_blocks(content, config, chapter)

    def _escape(self, match) -> str:
        contents = match.group('body')
        filename = md5(contents.encode()).hexdigest()
        self.logger.debug(f'saving following escaped conluence code to hash {filename}:'
                          f'\n{contents}')
        with open(self._escaped_dir / filename, 'w') as f:
            f.write(contents)
        return f"[confluence_escaped hash=%{filename}%]"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.backend_config = self.config.get('backend_config', {}).get('confluence', {})
        self.meta = load_meta(self.config.get('chapters', []), self.working_dir)

        self._escaped_dir = self.project_path / self.options['cachedir'] / self.options['escapedir']
        shutil.rmtree(self._escaped_dir, ignore_errors=True)
        self._escaped_dir.mkdir(parents=True)

        self.logger = self.logger.getChild('confluence_final')

        self.logger.debug(f'Preprocessor inited: {self.__dict__}')

    def apply(self):
        self._process_all_files(
            self._process_content,
            log_msg="Processing formatting structures"
        )
        self._process_tags_for_all_files(
            self._escape,
            log_msg="processing raw_confluence tags"
        )
        self.logger.info(f'Preprocessor applied')
