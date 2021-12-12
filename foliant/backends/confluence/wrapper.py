'''Wrapper module for a Confluence page'''

import os
import shutil

from filecmp import cmp
from hashlib import md5
from logging import getLogger
from pathlib import Path
from pathlib import PosixPath
from urllib.parse import urlparse

from atlassian import Confluence
from bs4 import BeautifulSoup

from .extracter import extract

logger = getLogger('flt.confluence.wrapper')


class PageNotAssignedError(Exception):
    pass


class SpaceNotFoundError(Exception):
    pass


class PageNotFoundError(Exception):
    pass


class HTMLResponseError(Exception):
    pass


HASH_PROPERTY_KEY = 'foliant_hash'


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
        self._check_params()

        self._url = None
        self._properties = {}
        self._get_info()

    def _check_params(self):
        '''
        Check param values:
        - Space exists;
        - Parent exists.
        '''
        if self.id:
            # if id is stated, space and parent_id are ignored, no need to check
            return
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

    @property
    def url(self):
        return self._url

    @property
    def properties(self):
        return self._properties

    def generate_new_body(self, new_content: str) -> str:
        '''
        Construct a new body of the page by surrounding `new_content` with static
        content from the page, and opening/closing foliant tags.
        # If there was no static content — just return the `new_content`.
        '''
        MACRO = ('<ac:structured-macro ac:macro-id="0" ac:name="anchor" '
                 'ac:schema-version="1"><ac:parameter ac:name="">{name}'
                 '</ac:parameter></ac:structured-macro>')
        # if self._before or self._after:
        result = self._before + MACRO.format(name="foliant_start")
        result += new_content + MACRO.format(name="foliant_end") + self._after
        # else:
            # result = new_content
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
                self._before = self._after = self._body = ''

    def _update_properties(self, content: dict):
        self._content = content
        self._id = content['id']
        self._before, self._body, self._after = extract(content['body']['storage']['value'])
        for pp in self._con.get_page_properties(self._id).get('results', []):
            self._properties[pp['key']] = pp['value']
        if '_links' in self._content:
            self._url = self._content['_links']['base'] + self._content['_links']['webui']
        if self.title is None:
            self._title = content['title']

    def _calculate_hash(self, content: str, title: str) -> str:
        _hash = md5(content.encode())
        _hash.update(title.encode())
        return _hash.hexdigest()

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

    def update_attachments(self,
                           attachments: list,
                           cache_dir: PosixPath or str):
        '''
        Upload a list of attachments into page. Only changed attachments will
        be updated. If page doesn't exist yet, an empty one will be created.

        `page` — a Page object to which attachments will be uploaded.
        `attachments` — a list of attachments PosixPaths.
        `cache_dir` — temporary dir where old attachments will be downloaded to
                      for comparison.
        '''
        if attachments:
            # we can only upload attachments to existing page
            if not self.exists:
                logger.debug('Page does not exist. Creating an empty one '
                             'to upload attachments')
                self.create_empty_page()
            cache_dir = Path(cache_dir)
            shutil.rmtree(cache_dir, ignore_errors=True)
            cache_dir.mkdir(exist_ok=True)
            remote_dict = self.download_all_attachments(cache_dir)
            for att in attachments:
                if att.name in remote_dict:
                    att_id, att_path = remote_dict[att.name]
                    if cmp(att, att_path):  # attachment not changed
                        logger.debug(f"Attachment {att.name} hadn't changed, skipping")
                        continue
                logger.debug(f"Attachment {att.name} CHANGED, reuploading")
                # not sure if it's needed, we can update images without deleting
                # page.delete_attachment(att_id)
                self.upload_attachment(att)

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

        if HASH_PROPERTY_KEY not in self.properties:
            return True

        content_hash = self._calculate_hash(new_content, new_title)
        return content_hash != self.properties[HASH_PROPERTY_KEY]

    def upload_content(self,
                       new_content: str,
                       title: str = None,
                       minor_edit: bool = True):
        body = self.generate_new_body(new_content)
        if self.exists:
            content = self._con.update_page(page_id=self._id,
                                            body=body,
                                            title=title or self.title,
                                            minor_edit=minor_edit)
        else:
            logger
            logger.debug(f'''create_page(type='page',
                                         title={title or self.title},
                                         space={self._space},
                                         body={body[:100]}...,
                                         parent_id={self.parent_id},
                                         representation='storage')' ''')
            content = self._con.create_page(type='page',
                                            title=title or self.title,
                                            space=self._space,
                                            body=body,
                                            parent_id=self.parent_id,
                                            representation='storage')
        if isinstance(content, str) or 'statusCode' in content:
            raise RuntimeError(f"Can't create or update page:\n {content}")
        self._update_properties(content)
        self.update_hash(new_content, title)

        return content

    def update_hash(self, content: str, title: str) -> dict:
        if HASH_PROPERTY_KEY in self.properties:
            self._con.delete_page_property(self._id, HASH_PROPERTY_KEY)
        data = {
            'key': HASH_PROPERTY_KEY,
            'value': self._calculate_hash(content, title)
        }
        result = self._con.set_page_property(self._id, data)
        if isinstance(result, str) or 'statusCode' in result:
            raise RuntimeError(f"Can't update page property:\n {result}")
        self._properties[HASH_PROPERTY_KEY] = data['value']

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
