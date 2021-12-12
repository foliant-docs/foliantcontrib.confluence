import os
import re
import shutil

from pathlib import Path
from pathlib import PosixPath
from subprocess import PIPE
from subprocess import STDOUT
from subprocess import run

from atlassian import Confluence
from bs4 import BeautifulSoup
from bs4 import NavigableString
from bs4 import CData

from .ref_diff import restore_refs
from .wrapper import Page

logger = None


def crop_title(source: str) -> str:
    """
    Crop out the first title from the source if it starts with it.

    :param source: source string to be processed.

    :returns: source string with the first title removed
    """
    result = source.lstrip()
    if re.match('^#{1,6} .+', result):  # starts with a title
        if '\n' in result:
            return result[result.index('\n') + 1:]
        else:
            return ''
    else:
        return source


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

    md_source = temp_dir / '0_markdown.md'
    converted = temp_dir / '1_editor.html'
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


def copy_with_unique_name(dest_dir: str or PosixPath, file_path: str or PosixPath) -> PosixPath:
    """
    Copy file_path file to dest_dir with unique name. Return path to copied file.
    Returns None if file_path doesn't exist.
    """
    if not os.path.exists(file_path):
        logger.debug(f'{file_path} does not exist, skipping')
        return
    new_name = unique_name(dest_dir, Path(file_path).name)
    new_path = Path(dest_dir) / new_name

    logger.debug(f'Copying file {file_path} to: {new_path}')
    shutil.copy(file_path, new_path)
    return new_path


def process_images(source: str,
                   rel_dir: str or Path,
                   attachment_manager) -> str:
    """
    Cleanup target_dir. Copy local images to `target_dir` with unique names, replace their HTML
    definitions in `source` with confluence definitions.

    `source` — string with HTML source code to search images in;
    `rel_dir` — path relative to which image paths are determined.
    `attachment_manager` — AttachmentManager object.

    Returns a tuple: (new_source, attachments)

    new_source — a modified source with correct image paths
    """

    def _sub(match):
        image = BeautifulSoup(match.group(0), 'html.parser').find('img')
        attrs = dict(image.attrs)
        image_path = attrs.pop('src')

        # leave external images as is
        if image_path.startswith('http'):
            return match.group(0)

        image_path = Path(rel_dir) / image_path

        logger.debug(f'Found image: {image}')

        new_path = attachment_manager.add_attachment(image_path)
        if not new_path:
            logger.warning(f'Image {image_path} does not exist! Skipping')
            return match.group(0)

        # attachments.append(new_path)

        attrs = ' '.join(f'{k.replace("_", ":")}="{v}"' for k, v in attrs.items())
        img_ref = f'<ac:image {attrs}><ri:attachment ri:filename="{new_path.name}"/></ac:image>'

        logger.debug(f'Converted image ref: {img_ref}')
        return img_ref

    # # cleaning up target dir
    # shutil.rmtree(target_dir, ignore_errors=True)
    # Path(target_dir).mkdir()

    image_pattern = re.compile(r'<img(?:\s*[A-Za-z_:][0-9A-Za-z_:\-\.]*=".+?"\s*)+/?\s*>')
    # attachments = []

    logger.debug('Processing images')

    return image_pattern.sub(_sub, source)  # , attachments


def post_process_ac_image(escaped_content, parent_filename, attachment_manager):
    if not escaped_content.strip().startswith('<ac:image'):
        return escaped_content

    logger.debug(f'Parsing confluence image: {escaped_content}')
    root = BeautifulSoup(escaped_content, 'html.parser')
    ac_image = root.find('ac:image')
    if not ac_image:
        logger.debug(f'ac:image tag not found, returning content as is')
        return escaped_content

    ri_attachment = ac_image.find('ri:attachment')
    if not ri_attachment:
        logger.debug(f'ri:attachment tag not found, returning content as is')
        return escaped_content

    src = ri_attachment.get('ri:filename')
    if not src:
        logger.debug(f'ri:filename attribute is not present, returning content as is')
        return escaped_content

    src = Path(src)

    if not src.exists():
        logger.debug(f'{src} does not exist, returning content as is')
        return escaped_content

    new_path = attachment_manager.add_attachment(src)

    ri_attachment.attrs['ri:filename'] = new_path.name
    return str(root)


def post_process_ac_link(escaped_content, parent_filename, attachment_manager):
    if not escaped_content.strip().startswith('<ac:link'):
        return escaped_content

    logger.debug(f'Parsing confluence link: {escaped_content}')
    root = BeautifulSoup(escaped_content, 'html.parser')
    ac_link = root.find('ac:link')
    if not ac_link:
        logger.debug(f'ac:link tag not found, returning content as is')
        return escaped_content

    ri_attachment = ac_link.find('ri:attachment')
    if not ri_attachment:
        logger.debug(f'ri:attachment tag not found, returning content as is')
        return escaped_content

    src = ri_attachment.get('ri:filename')
    if not src:
        logger.debug(f'ri:filename attribute is not present, returning content as is')
        return escaped_content

    src = Path(src)

    if not src.exists():
        logger.debug(f'{src} does not exist, returning content as is')
        return escaped_content

    new_path = attachment_manager.add_attachment(src)

    ri_attachment.attrs['ri:filename'] = new_path.name
    return str(root)


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
    pattern = re.compile(r"\[confluence_escaped hash=\%(?P<hash>.+?)\%\]")
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


def unformat(source: str):
    """remove whitespaces around HTML tags"""
    p = re.compile(r'^\n|(\n\s*)+$')
    bs = BeautifulSoup(source, 'html.parser')
    to_replace = [s for s in bs.strings if not isinstance(s, CData) and p.search(s)]
    for s in to_replace:
        new_string = p.sub('', s)
        s.replace_with(NavigableString(new_string))
    return str(bs)


def set_up_logger(logger_):
    '''Set up a global logger for functions in this module'''
    global logger
    logger = logger_
