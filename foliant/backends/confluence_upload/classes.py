from pathlib import PosixPath
from confluence.client import Confluence
from confluence.models.content import ContentType


class PageNotAssignedError(Exception):
    pass


class Page:

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
        self._get_info()

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
            content = self._con.get_content_by_id(self._id, expand=['version', 'body.storage'])
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

    def get_body(self):
        if self.exists:
            content = self._con.get_content_by_id(self._id, expand=('body.storage',))
            return content.body.storage
        else:
            raise PageNotAssignedError

    def delete_all_attachments(self):
        if self.exists:
            res = self._con._get(f'content/{self.id}/child/attachment', {}, []).json()['results']
            for att in res:
                self._con._delete(f'content/{att["id"]}', {})

    def upload_attachment(self, filename: str or PosixPath):
        if not self.exists:
            raise PageNotAssignedError
        return self._con.add_attachment(self._id, filename)

    def upload_content(self, new_content: str, title: str = None):
        if self.exists:  # TODO: catch tons of possible errors here

            return self._con.update_content(content_id=self._id,
                                            content_type=ContentType.PAGE,
                                            new_version=self.version + 1,
                                            new_content=new_content,
                                            new_title=title or self.title)
        else:
            content = self._con.create_content(content_type=ContentType.PAGE,
                                               title=title or self.title,
                                               space_key=self._space,
                                               content=new_content,
                                               parent_content_id=self.parent_id)
            self._update_properties(content)
            return content
