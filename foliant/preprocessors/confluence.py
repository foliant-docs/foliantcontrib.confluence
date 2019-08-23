'''
Preprocessor for Foliant documentation authoring tool.
Removes section meta-data from the document and adds seeds.
'''
from shutil import copytree, rmtree

from foliant.preprocessors.base import BasePreprocessor


class Preprocessor(BasePreprocessor):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.logger = self.logger.getChild('meta')

        self.logger.debug(f'Preprocessor inited: {self.__dict__}')

    def apply(self):
        self.logger.info('Applying preprocessor confluence')

        cachedir = self.project_path / '.confluencecache/__folianttmp__'
        rmtree(cachedir, ignore_errors=True)
        copytree(self.working_dir, cachedir)

        self.logger.info('Preprocessor applied')
