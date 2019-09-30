import os
from pathlib import PosixPath, Path
from urllib.parse import urlparse
from atlassian import Confluence
from bs4 import BeautifulSoup

from .extracter import extract


class PageNotAssignedError(Exception):
    pass


class SpaceNotFoundError(Exception):
    pass


class PageNotFoundError(Exception):
    pass


class HTMLResponseError(Exception):
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
            space = self._con.get_space(self.space)
            if isinstance(space, str):
                if space.startswith('No space found'):
                    raise SpaceNotFoundError(f'Space with key "{self.space}" does not exist'
                                             f' or you have insufficient privileges:\n'
                                             f'{space}')
                else:
                    raise HTMLResponseError(f'Cannot get space with key "{self.space}":\n'
                                            f'{space}')
        if self.parent_id:
            p = self._con.get_page_by_id(self.parent_id)
            if isinstance(p, str) or 'statusCode' in p:
                raise PageNotFoundError(f'Cannot access parent page with id {self.parent_id}:'
                                        f'\n{p}')

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
    def body(self):
        return self._body

    @property
    def full_body(self):
        return self._before + self.body + self._after

    @property
    def id(self):
        return self._id

    @property
    def parent_id(self):
        return self._parent_id

    def generate_new_body(self, new_content: str) -> str:
        '''
        Construct a new body of the page by surrounding `new_content` with static
        content from the page, and opening/closing foliant tags.
        If there was no static content — just return the `new_content`.
        '''
        MACRO = '''<p>
  <ac:structured-macro ac:macro-id="0" ac:name="anchor" ac:schema-version="1">
    <ac:parameter ac:name="">{name}</ac:parameter>
  </ac:structured-macro>
</p>'''
        if self._before or self._after:
            result = self._before + MACRO.format(name="foliant_start")
            result += new_content + MACRO.format(name="foliant_end") + self._after
        else:
            result = new_content
        return result

    def _get_info(self):
        if self._id:
            # ID supplied. Trying to get page by ID

            page = self._con.get_page_by_id(self._id, expand='body.storage')
            if isinstance(page, str) or 'statusCode' in page:
                raise PageNotFoundError(f'Cannot access page with id {self.parent_id}:'
                                        f'\n{page}')
            self._update_properties(page)
        else:
            # Page is defined by space and title. Searching for it:
            page = self._con.get_page_by_title(self._space, self._title)
            if page:
                page = self._con.get_page_by_id(page['id'], expand='body.storage')
                self._update_properties(page)
            else:
                self._content = self._id = None

    def _update_properties(self, content: dict):
        self._content = content
        self._id = content['id']
        self._before, self._body, self._after = extract(content['body']['storage']['value'])
        if self.title is None:
            self._title = content['title']

    def download_all_attachments(self, dest: PosixPath or str) -> dict:
        '''
        Download all attachments into the `dest` dir. Return a dictionary
        with key = downloaded attachment filename; value = (its id, full path).
        '''
        if not self.exists:
            return {}

        result = {}
        atts = self._con.get_attachments_from_content(self.id)
        # base = atts['_links']['base']
        for att in atts['results']:
            try:
                url = att['_links']['download'] + '&download=true'
                filename = os.path.basename(urlparse(url).path)
                filepath = (Path(dest) / filename).resolve()
                r = self._con.request(path=url)
            except KeyError:
                continue
            if r.status_code != 200:
                continue
            with open(filepath, 'wb') as f:
                f.write(r.content)
            result[filename] = (att['id'], filepath)
        return result

    def delete_attachment(self, att_id: int):
        '''
        Delete an attachment with `att_id`if page exists.
        If not — do nothing.
        '''
        if self.exists:
            res = self._con.request(method='DELETE',
                                    path=f'rest/api/content/{att_id}')
            if str(res.status_code)[0] != '2':
                raise RuntimeError(f"Can't delete an attachment {att_id} on page {self.id}:"
                                   f"\n{res.text}")

    def delete_all_attachments(self):
        '''
        Delete all attachments from the page if page exists.
        If not — do nothing.
        '''
        if self.exists:
            attachments = self._con.get_attachments_from_content(self.id)['results']
            for att in attachments:
                self.delete_attachment(att['id'])

    def upload_attachment(self, filename: str or PosixPath):
        if not self.exists:
            raise PageNotAssignedError
        res = self._con.attach_file(filename, page_id=self._id)
        if isinstance(res, str) or 'statusCode' in res:
            raise RuntimeError(f'Cannot access page with id {self.parent_id}:'
                               f'\n{res}')
        return res

    def create_empty_page(self):
        '''Create an empty page'''
        if self.exists:
            return
        else:
            self.upload_content('', self.title)

    def need_update(self, new_content: str, new_title: str or None = None):
        '''Check it page content and title differs from new_content'''
        # Method doesn't work right now. Maybe remove in future
        if not self.exists:
            return True

        # comparing content with bs4 prettify to get rid of insignificant
        # formatting differences
        result = True
        old = BeautifulSoup(self.body.strip(), 'html.parser')
        new = BeautifulSoup(new_content.strip(), 'html.parser')
        result = old.prettify() != new.prettify()
        # result = not\
        #     self._con.is_page_content_is_already_updated(self.id, new_content)
        if not result:
            title = new_title or self.title
            result = self.content['title'] != title
        return result

    def upload_content(self,
                       new_content: str,
                       title: str = None,
                       minor_edit: bool = True):
        if self.exists:
            # space at the end to force-update page
            body = self.generate_new_body(new_content)
            content = self._con.update_page(page_id=self._id,
                                            body=body,
                                            title=title or self.title,
                                            minor_edit=minor_edit)
        else:
            content = self._con.create_page(type='page',
                                            title=title or self.title,
                                            space=self._space,
                                            body=new_content,
                                            parent_id=self.parent_id,
                                            representation='storage')
        if isinstance(content, str) or 'statusCode' in content:
            raise RuntimeError(f"Can't create or update page:\n {content}")
        self._update_properties(content)

        return content

    def get_resolved_comment_ids(self) -> list:
        if not self.exists:
            return []
        resolved_ids = set()
        res = self._con.get_page_by_id(self.id, expand='children.comment.extensions.resolution,children.comment.extensions.inlineProperties')
        for comment in res['children']['comment']['results']:
            if 'inlineProperties' not in comment['extensions']:
                continue  # it's a regular comment
            if comment['extensions']['resolution']['status'] == 'resolved':
                resolved_ids.update((comment['extensions']['inlineProperties']['markerRef'],))
        return resolved_ids
