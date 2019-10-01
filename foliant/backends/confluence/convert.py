import re
import os
import shutil

from filecmp import cmp
from pathlib import PosixPath, Path
from subprocess import run, PIPE, STDOUT

from atlassian import Confluence

from .classes import Page
from .ref_diff import restore_refs

logger = None


def fix_pandoc_images(source: str) -> str:
    def _sub_image(match):
        """
        Convert image with pandoc <figcaption> tag into classic html image
        with caption in alt=""
        """
        image_caption = match.group('caption')
        image_path = match.group('path')
        result = f'<img src="{image_path}" alt="{image_caption}">'
        logger.debug(f'\nold: {match.group(0)}\nnew: {result}')
        return result

    image_pattern = re.compile(r'<figure>\s*<img src="(?P<path>.+?)" +(?:alt=".*?")?.+?>(?:<figcaption>(?P<caption>.*?)</figcaption>)\s*</figure>')
    return image_pattern.sub(_sub_image, source)


def md_to_editor(source: str, temp_dir: PosixPath, pandoc_path: str = 'pandoc'):
        """
        Convert md source string to HTML with Pandoc, fix pandoc image tags,
        for confluence doesn't understand <figure> and <figcaption> tags.

        Return the resulting HTML string.

        Parameters:

        source — md-source to be converted;
        temp_dir — directory for temporary files;
        pandoc_path — custom path to pandoc binary.
        """

        md_source = temp_dir / 'to_convert.md'
        converted = temp_dir / 'converted.html'
        with open(md_source, 'w') as f:
            f.write(source)
        command = f'{pandoc_path} {md_source} -f markdown -t html -o {converted}'

        logger.debug('Converting MD to HTML with Pandoc, command:\n' + command)
        run(command, shell=True, check=True, stdout=PIPE, stderr=STDOUT)

        with open(converted) as f:
            result = f.read()

        logger.debug('Fixing pandoc image captions.')

        result = fix_pandoc_images(result)
        return result


def unique_name(dest_dir: str or PosixPath, old_name: str) -> str:
    """
    Check if file with old_name exists in dest_dir. If it does —
    add incremental numbers until it doesn't.
    """
    counter = 1
    dest_path = Path(dest_dir)
    name = old_name
    while (dest_path / name).exists():
        counter += 1
        name = f'_{counter}'.join(os.path.splitext(old_name))
    return name


def process_images(source: str,
                   rel_dir: str or Path,
                   target_dir: str or Path) -> str:
    """
    Cleanup target_dir. Copy local images to `target_dir` with unique names, replace their HTML
    definitions in `source` with confluence definitions.

    `source` — string with HTML source code to search images in;
    `rel_dir` — path relative to which image paths are determined.

    Returns a tuple: (new_source, attachments)

    new_source — a modified source with correct image paths
    """

    def _sub(image):
        image_caption = image.group('caption')
        image_path = image.group('path')

        # leave external images as is
        if image_path.startswith('http'):
            return image.group(0)

        image_path = Path(rel_dir) / image_path

        logger.debug(f'Found image: {image.group(0)}')

        new_name = unique_name(target_dir, image_path.name)
        new_path = Path(target_dir) / new_name

        logger.debug(f'Copying image into: {new_path}')
        shutil.copy(image_path, new_path)
        attachments.append(new_path)

        img_ref = f'<ac:image ac:title="{image_caption}"><ri:attachment ri:filename="{new_name}"/></ac:image>'

        logger.debug(f'Converted image ref: {img_ref}')
        return img_ref

    # cleaning up target dir
    shutil.rmtree(target_dir, ignore_errors=True)
    Path(target_dir).mkdir()

    image_pattern = re.compile(r'<img src="(?P<path>.+?)" +(?:alt="(?P<caption>.*?)")?.+?>')
    attachments = []

    logger.debug('Processing images')

    return image_pattern.sub(_sub, source), attachments


def confluence_unescape(source: str, escape_dir: str or PosixPath) -> str:
    '''
    Unescape bits of raw confluene code, escaped by confluence preprocessor.

    `source` — source string, potentially containing escaped raw confluence code;
    `escape_dir` — a directory, containing saved original escaped code.

    Returns a modified source string with all escaped raw confluence code restored.
    '''

    def _sub(match):
        filename = match.group('hash')
        logger.debug(f'Restoring escaped confluence code with hash {filename}')
        filepath = Path(escape_dir) / filename
        with open(filepath) as f:
            return f.read()
    pattern = re.compile("\[confluence_escaped hash=\%(?P<hash>.+?)\%\]")
    return pattern.sub(_sub, source)


def editor_to_storage(con: Confluence, source: str) -> str:
    """
    Convert source string from confluence editor format to storage format
    and return it. This method required a confluence connection.

    `con` — a Confluence connection;
    `source` — original source in editor format.

    Returns a converted source in storage format.
    """
    data = {"value": source, "representation": "editor"}
    res = con.post('rest/api/contentbody/convert/storage', data=data)
    if res and 'value' in res:
        return res['value']
    else:
        raise RuntimeError('Cannot convert editor to storage. Got response:'
                           f'\n{res}')


def add_comments(page: Page, new_content: str, resolve_changed: bool = False):
    '''
    Restore inline comments from the current `page` source into the new_content.

    `page` — Page object of edited page;
    `new_content` — source XHTML in which comments are needed to be restored;
    `resolve_changed` — if True — only the unchanged comments will be added.
    '''
    logger.debug('Restoring inline comments.')
    if not page.exists:
        return new_content

    resolved = page.get_resolved_comment_ids()
    logger.debug(f'Got list of resolved comments in the text:\n{resolved}')

    return restore_refs(page.body,
                        new_content,
                        resolved,
                        logger,
                        resolve_changed)


def add_toc(source: str) -> str:
    """Add table of contents to the beginning of the page source"""
    result = '<ac:structured-macro ac:macro-id="1" '\
        'ac:name="toc" ac:schema-version="1"/>\n' + source
    return result


def update_attachments(page: Page,
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
        if not page.exists:
            logger.debug('Page does not exist. Creating an empty one '
                         'to upload attachments')
            page.create_empty_page()
        cache_dir = Path(cache_dir)
        shutil.rmtree(cache_dir, ignore_errors=True)
        cache_dir.mkdir(exist_ok=True)
        remote_dict = page.download_all_attachments(cache_dir)
        for att in attachments:
            if att.name in remote_dict:
                att_id, att_path = remote_dict[att.name]
                if cmp(att, att_path):  # attachment not changed
                    logger.debug(f"Attachment {att.name} hadn't changed, skipping")
                    continue
            logger.debug(f"Attachment {att.name} CHANGED, reuploading")
            # not sure if it's needed, we can update images without deleting
            # page.delete_attachment(att_id)
            page.upload_attachment(att)


def set_up_logger(logger_):
    '''Set up a global logger for functions in this module'''
    global logger
    logger = logger_
