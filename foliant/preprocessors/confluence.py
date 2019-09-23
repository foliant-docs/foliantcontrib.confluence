import shutil
from hashlib import md5

from foliant.preprocessors.utils.preprocessor_ext import BasePreprocessorExt


class Preprocessor(BasePreprocessorExt):
    defaults = {'cachedir': '.confluencecache',
                'escapedir': 'escaped'}
    tags = ('raw_confluence',)

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

        self._escaped_dir = self.project_path / self.options['cachedir'] / self.options['escapedir']
        shutil.rmtree(self._escaped_dir, ignore_errors=True)
        self._escaped_dir.mkdir(parents=True)

        self.logger = self.logger.getChild('confluence')

        self.logger.debug(f'Preprocessor inited: {self.__dict__}')

    def apply(self):
        self._process_tags_for_all_files(self._escape)
        self.logger.info(f'Preprocessor applied')
