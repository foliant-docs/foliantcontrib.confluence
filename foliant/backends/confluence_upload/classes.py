from pathlib import PosixPath
from confluence.client import Confluence
from confluence.models.content import ContentType
from confluence.exceptions.resourcenotfound import ConfluenceResourceNotFound
from confluence.exceptions.permissionerror import ConfluencePermissionError


class PageNotAssignedError(Exception):
    pass


class Page:
    '''Wrapper class for a Confluence page'''

    def __init__(self,
                 connection: Confluence,
                 space: str or None = None,
                 title: str or None = None,
                 parent_id: int or None = None,
                 id_: int or None = None):
        self._con = connection
        self._space = space
        self._parent_id = parent_id
        if (title is None or space is None) and id_ is None:
            raise RuntimeError('Must specify either title&space or id of the article')
        self._title = title
        self._id = id_
        self._check_params()
        self._get_info()

    def _check_params(self):
        '''
        Check param values:
        - Space exists;
        - Parent exists.
        '''
        if self.space:
            try:
                self._con.get_space(self.space)
            except ConfluenceResourceNotFound:
                raise RuntimeError(f'Space with name "{self.space}" does not exist'
                                   ' or you have insufficient privileges')
        if self.parent_id:
            try:
                self._con.get_content_by_id(self.parent_id)
            except ConfluenceResourceNotFound:
                raise RuntimeError(f'Parent page with id "{self.parent_id}" does not exist'
                                   ' or you have insufficient privileges')

    @property
    def exists(self):
        return self._content is not None

    @property
    def title(self):
        return self._title

    @property
    def space(self):
        return self._space

    @property
    def version(self):
        return self._version

    @property
    def content(self):
        return self._content

    @property
    def id(self):
        return self._id

    @property
    def parent_id(self):
        return self._parent_id

    def _get_info(self):
        if self._id:
            try:
                content = self._con.get_content_by_id(self._id, expand=['version', 'body.storage'])
            except ConfluenceResourceNotFound as e:
                # foliant can't reraise this error because it requires
                # additional parameters, so we reraise it as runtime error
                raise RuntimeError(str(e))
            self._update_properties(content)
        else:
            try:
                content = next(self._con.get_content(space_key=self._space,
                                                     title=self._title,
                                                     expand=['version', 'body.storage']))
                self._update_properties(content)
            except StopIteration:  # page not created yet
                self._content = self._version = self._id = None

    def _update_properties(self, content):
        self._content = content
        self._version = content.version.number
        self._id = content.id
        if self.title is None:
            self._title = content.title

    def delete_all_attachments(self):
        try:
            if self.exists:
                res = self._con._get(f'content/{self.id}/child/attachment', {}, []).json()['results']
                for att in res:
                    self._con._delete(f'content/{att["id"]}', {})
        except ConfluencePermissionError:
            raise RuntimeError(f"Don't have permissions to delete attachments on page {self.id}")

    def upload_attachment(self, filename: str or PosixPath):
        if not self.exists:
            raise PageNotAssignedError
        try:
            res = self._con.add_attachment(self._id, filename)
            return res
        except ConfluencePermissionError:
            raise RuntimeError(f"Don't have permissions to add attachments on page {self.id}")

    def upload_content(self, new_content: str, title: str = None):
        if self.exists:
            try:
                res = self._con.update_content(content_id=self._id,
                                               content_type=ContentType.PAGE,
                                               new_version=self.version + 1,
                                               new_content=new_content,
                                               new_title=title or self.title)
                return res
            except ConfluencePermissionError:
                raise RuntimeError(f"Don't have permissions to edit page {self.id}")

        else:
            try:
                content = self._con.create_content(content_type=ContentType.PAGE,
                                                   title=title or self.title,
                                                   space_key=self._space,
                                                   content=new_content,
                                                   parent_content_id=self.parent_id)
                self._update_properties(content)
                return content
            except ConfluencePermissionError:
                raise RuntimeError(f"Don't have permissions to create content in space {self._space}")
